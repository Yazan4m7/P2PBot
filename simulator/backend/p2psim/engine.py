from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any

from sqlalchemy import func, or_, select

from .clock import VirtualClock, utcnow, aware
from .config import SimulatorSettings
from .database import Database
from .domain import (
    AdStatus,
    CreateOrderRequest,
    FaultKind,
    OrderStatus,
    PaymentCheck,
    SendCashStatus,
    SimulationStatus,
    SimulatorError,
    TERMINAL_ORDER_STATUSES,
    VerifyCashStatus,
)
from .models import (
    AdRow,
    AdminActionRow,
    BalanceRow,
    ChatMessageRow,
    DisputeRow,
    DomainEventRow,
    FaultRow,
    IdempotencyRow,
    LedgerEntryRow,
    MerchantProfileRow,
    MerchantRow,
    OrderEventRow,
    OrderRow,
    PaymentEvidenceRow,
    PaymentMethodRow,
    PriceTickRow,
    ReservationRow,
    ScheduledEventRow,
    SimulationRow,
)
from .random_source import DeterministicRandom
from .state_machine import assert_transition

D = Decimal
BOT = "BOT"

PROFILE_CONFIGS: dict[str, dict[str, Any]] = {
    "FAST": {"release_delay": 20, "payment_delay": 20, "cancel_p": 0.01, "dispute_p": 0.01, "false_paid_p": 0.0, "wrong_payment_p": 0.0, "ghost_p": 0.0, "volatile": False},
    "SLOW": {"release_delay": 420, "payment_delay": 360, "cancel_p": 0.02, "dispute_p": 0.02, "false_paid_p": 0.0, "wrong_payment_p": 0.0, "ghost_p": 0.0, "volatile": False},
    "CANCELLER": {"release_delay": 90, "payment_delay": 90, "cancel_p": 0.45, "dispute_p": 0.03, "false_paid_p": 0.0, "wrong_payment_p": 0.0, "ghost_p": 0.03, "volatile": False},
    "GHOST": {"release_delay": 600, "payment_delay": 600, "cancel_p": 0.02, "dispute_p": 0.02, "false_paid_p": 0.0, "wrong_payment_p": 0.0, "ghost_p": 0.65, "volatile": False},
    "MISMATCH": {"release_delay": 80, "payment_delay": 60, "cancel_p": 0.01, "dispute_p": 0.05, "false_paid_p": 0.05, "wrong_payment_p": 0.45, "ghost_p": 0.01, "volatile": False},
    "DISPUTE": {"release_delay": 120, "payment_delay": 120, "cancel_p": 0.01, "dispute_p": 0.45, "false_paid_p": 0.05, "wrong_payment_p": 0.05, "ghost_p": 0.02, "volatile": False},
    "VOLATILE": {"release_delay": 60, "payment_delay": 60, "cancel_p": 0.04, "dispute_p": 0.02, "false_paid_p": 0.0, "wrong_payment_p": 0.02, "ghost_p": 0.01, "volatile": True},
}

PROFILE_SEQUENCE = ["FAST", "FAST", "SLOW", "CANCELLER", "GHOST", "MISMATCH", "DISPUTE", "VOLATILE", "FAST", "SLOW", "FAST", "VOLATILE"]


class SimulatorEngine:
    def __init__(self, db: Database, settings: SimulatorSettings):
        self.db = db
        self.settings = settings
        self.db.create_schema()
        self.simulation_id = self._ensure_simulation()
        self.clock = VirtualClock(db, self.simulation_id)

    def _config_snapshot(self, seed: int) -> dict[str, Any]:
        return {
            "seed": seed,
            "asset": self.settings.default_asset,
            "fiat": self.settings.default_fiat,
            "initial_reference_price": self.settings.initial_reference_price,
            "payment_timeout_seconds": self.settings.payment_timeout_seconds,
        }

    def _ensure_simulation(self) -> str:
        with self.db.session() as session:
            row = session.scalars(select(SimulationRow).order_by(SimulationRow.created_at.desc())).first()
            if row is not None:
                return row.id
        return self.reset(seed=self.settings.seed)["simulation_id"]

    def reset(self, *, seed: int | None = None) -> dict[str, Any]:
        seed = self.settings.seed if seed is None else int(seed)
        sim_id = f"SIM-{seed}-{uuid.uuid4().hex[:8]}"
        config = self._config_snapshot(seed)
        config_json = json.dumps(config, sort_keys=True)
        config_hash = hashlib.sha256(config_json.encode()).hexdigest()
        start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.db.drop_schema()
        self.db.create_schema()
        with self.db.session() as session:
            session.add(SimulationRow(
                id=sim_id,
                seed=seed,
                status=SimulationStatus.ACTIVE.value,
                config_json=config_json,
                config_hash=config_hash,
                created_at=utcnow(),
                base_simulated_at=start,
                base_real_at=utcnow(),
                speed=self.settings.default_speed,
                market_tick_index=0,
                market_frozen=False,
                regime="NORMAL",
            ))
            session.commit()
        self.simulation_id = sim_id
        self.clock = VirtualClock(self.db, sim_id)
        self._seed_reference_data()
        self._seed_profiles()
        self._seed_identities_and_balances()
        self._record_price_tick(D(str(self.settings.initial_reference_price)), "NORMAL", tick_index=0)
        self._seed_ads()
        self._emit("SIMULATION_RESET", sim_id, {"seed": seed, "config_hash": config_hash})
        return self.status()

    def status(self) -> dict[str, Any]:
        with self.db.session() as session:
            row = session.get(SimulationRow, self.simulation_id)
            assert row is not None
            return {
                "simulation_id": row.id,
                "seed": row.seed,
                "status": row.status,
                "simulated_time": self.clock.now().isoformat(),
                "speed": row.speed,
                "market_frozen": row.market_frozen,
                "regime": row.regime,
                "config_hash": row.config_hash,
            }

    def export_replay(self) -> dict[str, Any]:
        with self.db.session() as session:
            sim = session.get(SimulationRow, self.simulation_id)
            assert sim is not None
            events = session.scalars(select(DomainEventRow).where(DomainEventRow.simulation_id == self.simulation_id).order_by(DomainEventRow.id)).all()
            return {"simulation": self.status(), "config": json.loads(sim.config_json), "events": [self._domain_event_dict(x) for x in events]}

    def pause(self) -> dict[str, Any]:
        self.clock.pause(); self._admin("PAUSE", {}); return self.status()

    def resume(self) -> dict[str, Any]:
        self.clock.resume(); self._admin("RESUME", {}); return self.status()

    def set_speed(self, speed: float) -> dict[str, Any]:
        self.clock.set_speed(speed); self._admin("SET_SPEED", {"speed": speed}); return self.status()

    def advance(self, seconds: float) -> dict[str, Any]:
        now = self.clock.advance(seconds)
        self._admin("ADVANCE_TIME", {"seconds": seconds, "now": now.isoformat()})
        processed = self.run_due_events()
        return {**self.status(), "processed_events": processed}

    def _seed_reference_data(self) -> None:
        with self.db.session() as session:
            session.add_all([
                PaymentMethodRow(identifier="CliQ", display_name="CliQ", fiat="JOD", enabled=True),
                PaymentMethodRow(identifier="BankJordan", display_name="Bank Transfer", fiat="JOD", enabled=True),
                PaymentMethodRow(identifier="ZainCash", display_name="Zain Cash", fiat="JOD", enabled=True),
            ])
            session.commit()

    def _seed_profiles(self) -> None:
        with self.db.session() as session:
            for name, config in PROFILE_CONFIGS.items():
                session.merge(MerchantProfileRow(name=name, version=1, config_json=json.dumps(config, sort_keys=True)))
            session.commit()

    def _seed_identities_and_balances(self) -> None:
        seed = self._seed(); rng = DeterministicRandom(seed); now = self.clock.now()
        with self.db.session() as session:
            self._set_balance(session, BOT, "JOD", D("50000"), D("0"), now)
            self._set_balance(session, BOT, "USDT", D("50000"), D("0"), now)
            for idx, profile in enumerate(PROFILE_SEQUENCE, start=1):
                local = rng.stream(f"merchant:{idx}")
                merchant_no = f"M{idx:04d}"
                methods = ["CliQ", "BankJordan"] if idx % 3 else ["CliQ", "ZainCash"]
                completion = max(72.0, min(99.9, 98.8 - (idx % 5) * 0.65 - (3.0 if profile in {"CANCELLER", "GHOST"} else 0)))
                count = 80 + int(local.random() * 2500)
                release = PROFILE_CONFIGS[profile]["release_delay"] + int(local.random() * 45)
                buy_offset = [-28, -18, -8, 0, 8, 16, 24, -22, -12, 5, 12, 20][idx - 1]
                sell_offset = [18, 10, 5, -3, -12, -20, 24, 15, 8, -8, -16, 28][idx - 1]
                session.add(MerchantRow(
                    merchant_no=merchant_no,
                    simulation_id=self.simulation_id,
                    nickname=f"JordanMerchant{idx:02d}",
                    merchant_type="MERCHANT" if idx % 4 else "PRO",
                    verified=True,
                    completion_rate_pct=completion,
                    order_count=count,
                    avg_release_seconds=float(release),
                    profile_name=profile,
                    profile_version=1,
                    online=True,
                    buy_offset_bps=float(buy_offset),
                    sell_offset_bps=float(sell_offset),
                    payment_methods_json=json.dumps(methods),
                    created_at=now,
                ))
                self._set_balance(session, f"merchant:{merchant_no}", "USDT", D(str(5000 + idx * 700)), D("0"), now)
                self._set_balance(session, f"merchant:{merchant_no}", "JOD", D(str(12000 + idx * 2000)), D("0"), now)
            session.commit()

    def _set_balance(self, session, account_id: str, currency: str, owned: Decimal, reserved: Decimal, now: datetime) -> None:
        session.add(BalanceRow(simulation_id=self.simulation_id, account_id=account_id, currency=currency, owned=owned, reserved=reserved, updated_at=now))

    def _seed_ads(self) -> None:
        with self.db.session() as session:
            merchants = session.scalars(select(MerchantRow).where(MerchantRow.simulation_id == self.simulation_id).order_by(MerchantRow.merchant_no)).all()
        for merchant in merchants:
            self._create_or_refresh_ad(merchant.merchant_no, "BUY")
            self._create_or_refresh_ad(merchant.merchant_no, "SELL")

    def _seed(self) -> int:
        with self.db.session() as session:
            sim = session.get(SimulationRow, self.simulation_id); assert sim is not None; return sim.seed

    def reference_price(self) -> Decimal:
        with self.db.session() as session:
            row = session.scalars(select(PriceTickRow).where(PriceTickRow.simulation_id == self.simulation_id).order_by(PriceTickRow.tick_index.desc())).first()
            return D(str(row.price)) if row else D(str(self.settings.initial_reference_price))

    def set_reference_price(self, price: Decimal) -> dict[str, Any]:
        if price <= 0: raise SimulatorError("INVALID_PRICE", "price must be positive")
        with self.db.session() as session:
            sim = session.get(SimulationRow, self.simulation_id); assert sim is not None; sim.market_tick_index += 1; idx = sim.market_tick_index; session.commit()
        self._record_price_tick(price, "MANUAL", tick_index=idx); self._reprice_all_ads(); self._admin("SET_REFERENCE_PRICE", {"price": str(price)})
        return {"price": str(price), "tick_index": idx}

    def price_shock(self, pct: Decimal) -> dict[str, Any]:
        new_price = self.reference_price() * (D("1") + pct / D("100"))
        with self.db.session() as session:
            sim = session.get(SimulationRow, self.simulation_id); assert sim is not None; sim.regime = "SHOCK"; sim.market_tick_index += 1; idx = sim.market_tick_index; session.commit()
        self._record_price_tick(new_price, "SHOCK", tick_index=idx); self._reprice_all_ads(); self._admin("PRICE_SHOCK", {"pct": str(pct), "price": str(new_price)})
        return {"price": str(new_price), "pct": str(pct)}

    def freeze_market(self, frozen: bool) -> dict[str, Any]:
        with self.db.session() as session:
            sim = session.get(SimulationRow, self.simulation_id); assert sim is not None; sim.market_frozen = bool(frozen); session.commit()
        self._admin("FREEZE_MARKET", {"frozen": bool(frozen)}); return self.status()

    def market_tick(self) -> dict[str, Any]:
        with self.db.session() as session:
            sim = session.get(SimulationRow, self.simulation_id); assert sim is not None
            if sim.market_frozen: return {"frozen": True, "price": str(self.reference_price()), "tick_index": sim.market_tick_index}
            sim.market_tick_index += 1; idx = sim.market_tick_index; regime = sim.regime; session.commit()
        rng = DeterministicRandom(self._seed()).stream(f"market:{idx}")
        volatility = {"TIGHT": 0.00008, "NORMAL": 0.00022, "WIDE": 0.00055, "SHOCK": 0.0012, "ONE_SIDED": 0.0004}.get(regime, 0.00022)
        movement = D(str((rng.random() - 0.5) * 2 * volatility))
        new_price = max(D("0.001"), self.reference_price() * (D("1") + movement))
        self._record_price_tick(new_price, regime, tick_index=idx); self._reprice_all_ads(); self._emit("MARKET_TICK", str(idx), {"price": str(new_price), "regime": regime})
        return {"price": str(new_price), "tick_index": idx, "regime": regime}

    def set_regime(self, regime: str) -> dict[str, Any]:
        regime = regime.upper()
        if regime not in {"NORMAL", "TIGHT", "WIDE", "SHOCK", "ONE_SIDED"}: raise SimulatorError("INVALID_REGIME", regime)
        with self.db.session() as session:
            sim = session.get(SimulationRow, self.simulation_id); assert sim is not None; sim.regime = regime; session.commit()
        self._admin("SET_REGIME", {"regime": regime}); return self.status()

    def _record_price_tick(self, price: Decimal, regime: str, *, tick_index: int) -> None:
        with self.db.session() as session:
            session.add(PriceTickRow(simulation_id=self.simulation_id, asset=self.settings.default_asset, fiat=self.settings.default_fiat, price=price.quantize(D("0.0000000001")), regime=regime, tick_index=tick_index, observed_at=self.clock.now())); session.commit()

    def price_history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(PriceTickRow).where(PriceTickRow.simulation_id == self.simulation_id).order_by(PriceTickRow.tick_index.desc()).limit(limit)).all()
            return [{"tick_index": r.tick_index, "price": str(r.price), "regime": r.regime, "observed_at": r.observed_at.isoformat()} for r in rows]

    def _create_or_refresh_ad(self, merchant_no: str, side: str) -> None:
        side = side.upper()
        with self.db.session() as session:
            m = session.get(MerchantRow, merchant_no)
            if m is None: raise SimulatorError("MERCHANT_NOT_FOUND", merchant_no, status_code=404)
            price = self._merchant_price(m, side); methods = json.loads(m.payment_methods_json); ad_no = f"AD-{merchant_no}-{side}"; existing = session.get(AdRow, ad_no); now = self.clock.now(); total = D("3000") + D(str(int(merchant_no[1:]) * 150))
            if existing is None:
                existing = AdRow(ad_no=ad_no, simulation_id=self.simulation_id, merchant_no=merchant_no, trade_type=side, asset=self.settings.default_asset, fiat=self.settings.default_fiat, price=price, total_asset=total, min_fiat=D("20"), max_fiat=D("1500"), payment_methods_json=json.dumps(methods), status=AdStatus.ACTIVE.value, created_at=now, updated_at=now); session.add(existing)
            else:
                existing.price = price; existing.updated_at = now
                if existing.status == AdStatus.EXHAUSTED.value and self._ad_available_asset(session, existing) > 0: existing.status = AdStatus.ACTIVE.value
            session.commit()

    def _merchant_price(self, merchant: MerchantRow, side: str) -> Decimal:
        ref = self.reference_price(); bps = merchant.buy_offset_bps if side == "BUY" else merchant.sell_offset_bps
        return (ref * (D("1") + D(str(bps)) / D("10000"))).quantize(D("0.0001"))

    def _reprice_all_ads(self) -> None:
        with self.db.session() as session:
            rows = session.scalars(select(AdRow).where(AdRow.simulation_id == self.simulation_id, AdRow.status.in_([AdStatus.ACTIVE.value, AdStatus.PAUSED.value]))).all()
            merchants = {m.merchant_no: m for m in session.scalars(select(MerchantRow).where(MerchantRow.simulation_id == self.simulation_id)).all()}; now = self.clock.now()
            for ad in rows: ad.price = self._merchant_price(merchants[ad.merchant_no], ad.trade_type); ad.updated_at = now
            session.commit()
        self._emit("ADS_REPRICED", None, {"reference_price": str(self.reference_price())})

    def _ad_available_asset(self, session, ad: AdRow) -> Decimal:
        reserved = session.scalar(select(func.coalesce(func.sum(ReservationRow.amount), 0)).where(ReservationRow.simulation_id == self.simulation_id, ReservationRow.status == "ACTIVE", ReservationRow.currency == ad.asset, ReservationRow.account_id == (f"merchant:{ad.merchant_no}" if ad.trade_type == "BUY" else BOT), ReservationRow.order_no.in_(select(OrderRow.order_no).where(OrderRow.ad_no == ad.ad_no)))) or D("0")
        return max(D("0"), D(str(ad.total_asset)) - D(str(reserved)))

    def public_ads(self, *, fiat: str, asset: str, trade_type: str, limit: int, payment_methods: list[str]) -> dict[str, Any]:
        trade_type = trade_type.upper()
        if trade_type not in {"BUY", "SELL"}: raise SimulatorError("INVALID_TRADE_TYPE", trade_type)
        if not 1 <= limit <= 20: raise SimulatorError("INVALID_LIMIT", "limit must be between 1 and 20")
        requested = {m.upper() for m in payment_methods}
        with self.db.session() as session:
            rows = session.scalars(select(AdRow).where(AdRow.simulation_id == self.simulation_id, AdRow.status == AdStatus.ACTIVE.value, AdRow.fiat == fiat.upper(), AdRow.asset == asset.upper(), AdRow.trade_type == trade_type)).all()
            merchants = {m.merchant_no: m for m in session.scalars(select(MerchantRow).where(MerchantRow.simulation_id == self.simulation_id)).all()}; items = []
            for ad in rows:
                merchant = merchants[ad.merchant_no]
                if not merchant.online: continue
                methods = json.loads(ad.payment_methods_json)
                if requested and not (requested & {x.upper() for x in methods}): continue
                available = self._ad_available_asset(session, ad)
                if available <= 0: continue
                items.append({"adv": {"adNo": ad.ad_no, "price": str(ad.price), "surplusAmount": str(available.quantize(D("0.000001"), rounding=ROUND_DOWN)), "minSingleTransAmount": str(ad.min_fiat), "maxSingleTransAmount": str(ad.max_fiat), "tradeMethods": [{"identifier": x, "tradeMethodName": x} for x in methods]}, "advertiser": {"merchantNo": merchant.merchant_no, "nickName": merchant.nickname, "monthFinishRate": merchant.completion_rate_pct / 100, "monthOrderCount": merchant.order_count, "avgReleaseTimeOfLatest30day": merchant.avg_release_seconds, "userType": merchant.merchant_type}})
            items.sort(key=lambda x: D(x["adv"]["price"]), reverse=(trade_type == "SELL")); return {"success": True, "data": items[:limit]}

    def trade_methods(self, fiat: str) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(PaymentMethodRow).where(PaymentMethodRow.fiat == fiat.upper(), PaymentMethodRow.enabled.is_(True)).order_by(PaymentMethodRow.identifier)).all(); return [{"identifier": r.identifier, "tradeMethodName": r.display_name} for r in rows]

    def pause_ad(self, ad_no: str, paused: bool = True) -> dict[str, Any]:
        with self.db.session() as session:
            ad = self._ad(session, ad_no); ad.status = AdStatus.PAUSED.value if paused else AdStatus.ACTIVE.value; ad.updated_at = self.clock.now(); session.commit()
        self._admin("PAUSE_AD" if paused else "ACTIVATE_AD", {"ad_no": ad_no}); return self.ad_detail(ad_no)

    def close_ad(self, ad_no: str) -> dict[str, Any]:
        with self.db.session() as session:
            ad = self._ad(session, ad_no); ad.status = AdStatus.CLOSED.value; ad.updated_at = self.clock.now(); session.commit()
        self._admin("CLOSE_AD", {"ad_no": ad_no}); return self.ad_detail(ad_no)

    def reprice_ad(self, ad_no: str, price: Decimal) -> dict[str, Any]:
        if price <= 0: raise SimulatorError("INVALID_PRICE", "price must be positive")
        with self.db.session() as session:
            ad = self._ad(session, ad_no); ad.price = price; ad.updated_at = self.clock.now(); session.commit()
        self._admin("REPRICE_AD", {"ad_no": ad_no, "price": str(price)}); return self.ad_detail(ad_no)

    def replenish_ad(self, ad_no: str, asset_amount: Decimal) -> dict[str, Any]:
        if asset_amount <= 0: raise SimulatorError("INVALID_AMOUNT", "replenishment must be positive")
        with self.db.session() as session:
            ad = self._ad(session, ad_no); ad.total_asset = D(str(ad.total_asset)) + asset_amount
            if ad.status == AdStatus.EXHAUSTED.value: ad.status = AdStatus.ACTIVE.value
            ad.updated_at = self.clock.now(); session.commit()
        self._admin("REPLENISH_AD", {"ad_no": ad_no, "asset_amount": str(asset_amount)}); return self.ad_detail(ad_no)

    def ad_detail(self, ad_no: str) -> dict[str, Any]:
        with self.db.session() as session: return self._ad_dict(session, self._ad(session, ad_no))

    def list_ads_admin(self) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(AdRow).where(AdRow.simulation_id == self.simulation_id).order_by(AdRow.ad_no)).all(); return [self._ad_dict(session, r) for r in rows]

    def _ad_dict(self, session, ad: AdRow) -> dict[str, Any]:
        return {"ad_no": ad.ad_no, "merchant_no": ad.merchant_no, "trade_type": ad.trade_type, "asset": ad.asset, "fiat": ad.fiat, "price": str(ad.price), "available_asset": str(self._ad_available_asset(session, ad)), "min_fiat": str(ad.min_fiat), "max_fiat": str(ad.max_fiat), "payment_methods": json.loads(ad.payment_methods_json), "status": ad.status, "updated_at": ad.updated_at.isoformat()}

    def balances(self, account_id: str = BOT) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(BalanceRow).where(BalanceRow.simulation_id == self.simulation_id, BalanceRow.account_id == account_id).order_by(BalanceRow.currency)).all(); return [self._balance_dict(r) for r in rows]

    @staticmethod
    def _balance_dict(row: BalanceRow) -> dict[str, Any]:
        owned = D(str(row.owned)); reserved = D(str(row.reserved)); return {"account_id": row.account_id, "currency": row.currency, "owned": str(owned), "reserved": str(reserved), "available": str(owned - reserved)}

    def _balance(self, session, account: str, currency: str) -> BalanceRow:
        row = session.scalars(select(BalanceRow).where(BalanceRow.simulation_id == self.simulation_id, BalanceRow.account_id == account, BalanceRow.currency == currency)).one_or_none()
        if row is None: raise SimulatorError("BALANCE_NOT_FOUND", f"{account}/{currency}", status_code=404)
        return row

    def _reserve(self, session, *, order_no: str, account: str, currency: str, amount: Decimal, kind: str) -> ReservationRow:
        if amount <= 0: raise SimulatorError("INVALID_RESERVATION", "amount must be positive")
        balance = self._balance(session, account, currency); available = D(str(balance.owned)) - D(str(balance.reserved))
        if available < amount: raise SimulatorError("INSUFFICIENT_BALANCE", f"{account} has {available} {currency}", status_code=409)
        balance.reserved = D(str(balance.reserved)) + amount; balance.updated_at = self.clock.now()
        reservation = ReservationRow(simulation_id=self.simulation_id, order_no=order_no, account_id=account, currency=currency, amount=amount, kind=kind, status="ACTIVE", created_at=self.clock.now()); session.add(reservation); return reservation

    def _release_reservations(self, session, order_no: str) -> None:
        rows = session.scalars(select(ReservationRow).where(ReservationRow.order_no == order_no, ReservationRow.status == "ACTIVE")).all()
        for r in rows:
            balance = self._balance(session, r.account_id, r.currency); balance.reserved = D(str(balance.reserved)) - D(str(r.amount))
            if D(str(balance.reserved)) < 0: raise SimulatorError("RESERVATION_INVARIANT", "reserved balance became negative", status_code=500)
            balance.updated_at = self.clock.now(); r.status = "RELEASED"; r.consumed_at = self.clock.now()

    def _transfer_reserved(self, session, *, order_no: str, kind: str, from_account: str, to_account: str, currency: str, amount: Decimal, entry_type: str) -> None:
        key = f"{order_no}:{entry_type}"
        if session.scalars(select(LedgerEntryRow).where(LedgerEntryRow.idempotency_key == key)).one_or_none() is not None: return
        reservation = session.scalars(select(ReservationRow).where(ReservationRow.order_no == order_no, ReservationRow.kind == kind)).one_or_none()
        if reservation is None or reservation.status != "ACTIVE": raise SimulatorError("RESERVATION_NOT_ACTIVE", f"{order_no}/{kind}", status_code=409)
        if reservation.account_id != from_account or reservation.currency != currency or D(str(reservation.amount)) != amount: raise SimulatorError("RESERVATION_MISMATCH", f"{order_no}/{kind}", status_code=500)
        source = self._balance(session, from_account, currency); target = self._balance(session, to_account, currency)
        if D(str(source.owned)) < amount or D(str(source.reserved)) < amount: raise SimulatorError("SETTLEMENT_INVARIANT", "source balance/reservation insufficient", status_code=500)
        source.owned = D(str(source.owned)) - amount; source.reserved = D(str(source.reserved)) - amount; target.owned = D(str(target.owned)) + amount; source.updated_at = target.updated_at = self.clock.now(); reservation.status = "CONSUMED"; reservation.consumed_at = self.clock.now()
        session.add(LedgerEntryRow(simulation_id=self.simulation_id, idempotency_key=key, order_no=order_no, currency=currency, amount=amount, from_account=from_account, to_account=to_account, entry_type=entry_type, created_at=self.clock.now()))

    def reconcile_balances(self) -> dict[str, Any]:
        with self.db.session() as session:
            reservations = session.scalars(select(ReservationRow).where(ReservationRow.simulation_id == self.simulation_id, ReservationRow.status == "ACTIVE")).all(); expected: dict[tuple[str, str], Decimal] = {}
            for r in reservations: expected[(r.account_id, r.currency)] = expected.get((r.account_id, r.currency), D("0")) + D(str(r.amount))
            mismatches = []
            for bal in session.scalars(select(BalanceRow).where(BalanceRow.simulation_id == self.simulation_id)).all():
                exp = expected.get((bal.account_id, bal.currency), D("0"))
                if D(str(bal.reserved)) != exp or D(str(bal.owned)) < D("0") or D(str(bal.reserved)) < D("0") or D(str(bal.owned)) < D(str(bal.reserved)): mismatches.append({**self._balance_dict(bal), "expected_reserved": str(exp)})
            return {"ok": not mismatches, "mismatches": mismatches}

    def create_order(self, req: CreateOrderRequest) -> dict[str, Any]:
        if not req.idempotency_key: raise SimulatorError("IDEMPOTENCY_REQUIRED", "idempotency key is required")
        idem_key = f"CREATE:{req.idempotency_key}"
        with self.db.session() as session:
            idem = session.get(IdempotencyRow, idem_key)
            if idem and idem.entity_id:
                order = session.get(OrderRow, idem.entity_id)
                if order: return self._order_dict(session, order)
            ad = self._ad(session, req.ad_no)
            if ad.status != AdStatus.ACTIVE.value: raise SimulatorError("AD_NOT_ACTIVE", req.ad_no, status_code=409)
            if req.expected_price is not None and D(str(ad.price)) != req.expected_price: raise SimulatorError("PRICE_CHANGED", f"current price is {ad.price}", status_code=409)
            methods = {x.upper() for x in json.loads(ad.payment_methods_json)}
            if req.payment_method.upper() not in methods: raise SimulatorError("PAYMENT_METHOD_NOT_SUPPORTED", req.payment_method)
            if (req.fiat_amount is None) == (req.asset_amount is None): raise SimulatorError("AMOUNT_REQUIRED", "provide exactly one of fiat_amount or asset_amount")
            price = D(str(ad.price)); asset_amount = req.asset_amount if req.asset_amount is not None else (req.fiat_amount / price); asset_amount = asset_amount.quantize(D("0.000001"), rounding=ROUND_DOWN); fiat_amount = req.fiat_amount if req.fiat_amount is not None else (asset_amount * price); fiat_amount = fiat_amount.quantize(D("0.001"), rounding=ROUND_DOWN)
            if fiat_amount < D(str(ad.min_fiat)): raise SimulatorError("AMOUNT_BELOW_MIN", str(ad.min_fiat), status_code=409)
            if fiat_amount > D(str(ad.max_fiat)): raise SimulatorError("AMOUNT_ABOVE_MAX", str(ad.max_fiat), status_code=409)
            available = self._ad_available_asset(session, ad)
            if asset_amount > available: raise SimulatorError("INSUFFICIENT_AD_LIQUIDITY", str(available), status_code=409)
            merchant = session.get(MerchantRow, ad.merchant_no); assert merchant is not None; order_no = f"SIMO-{uuid.uuid4().hex[:16].upper()}"; buyer, seller = ((BOT, f"merchant:{ad.merchant_no}") if ad.trade_type == "BUY" else (f"merchant:{ad.merchant_no}", BOT)); now = self.clock.now()
            order = OrderRow(order_no=order_no, simulation_id=self.simulation_id, ad_no=ad.ad_no, bot_trade_id=req.bot_trade_id, side=ad.trade_type, buyer_account=buyer, seller_account=seller, merchant_no=ad.merchant_no, merchant_profile=merchant.profile_name, asset=ad.asset, fiat=ad.fiat, asset_amount=asset_amount, fiat_amount=fiat_amount, unit_price=price, payment_method=req.payment_method, status=OrderStatus.CREATED.value, created_at=now, updated_at=now, payment_deadline=now + timedelta(seconds=self.settings.payment_timeout_seconds)); session.add(order); session.flush()
            self._reserve(session, order_no=order_no, account=seller, currency=ad.asset, amount=asset_amount, kind="ASSET"); self._reserve(session, order_no=order_no, account=buyer, currency=ad.fiat, amount=fiat_amount, kind="FIAT"); session.add(IdempotencyRow(key=idem_key, simulation_id=self.simulation_id, operation="CREATE_ORDER", entity_id=order_no, created_at=now)); self._transition(session, order, OrderStatus.AWAITING_PAYMENT, actor="SYSTEM", event_type="ORDER_CREATED", payload={"ad_no": ad.ad_no}); session.add(ScheduledEventRow(simulation_id=self.simulation_id, event_type="ORDER_EXPIRE", entity_id=order_no, payload_json="{}", due_at=order.payment_deadline, status="PENDING"))
            if order.side == "SELL": session.add(ScheduledEventRow(simulation_id=self.simulation_id, event_type="COUNTERPARTY_BUYER_ACT", entity_id=order_no, payload_json="{}", due_at=now + timedelta(seconds=PROFILE_CONFIGS[merchant.profile_name]["payment_delay"]), status="PENDING"))
            session.commit(); self._emit("ORDER_CREATED", order_no, {"side": order.side, "ad_no": order.ad_no, "bot_trade_id": req.bot_trade_id}, correlation_id=req.bot_trade_id); return self._order_dict(session, order)

    def get_order(self, order_no: str) -> dict[str, Any]:
        with self.db.session() as session: return self._order_dict(session, self._order(session, order_no))

    def list_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(OrderRow).where(OrderRow.simulation_id == self.simulation_id).order_by(OrderRow.created_at.desc()).limit(limit)).all(); return [self._order_dict(session, r) for r in rows]

    def send_cash(self, order_no: str, *, idempotency_key: str, scenario: str = "SUCCESS") -> dict[str, Any]:
        scenario = scenario.upper()
        if scenario not in {x.value for x in SendCashStatus}: raise SimulatorError("INVALID_PAYMENT_SCENARIO", scenario)
        idem_key = f"SEND_CASH:{order_no}:{idempotency_key}"
        with self.db.session() as session:
            idem = session.get(IdempotencyRow, idem_key); order = self._order(session, order_no)
            if order.side != "BUY": raise SimulatorError("WRONG_ORDER_SIDE", "send-cash is for bot BUY flow", status_code=409)
            if idem and idem.response_json: return json.loads(idem.response_json)
            if OrderStatus(order.status) in TERMINAL_ORDER_STATUSES: raise SimulatorError("ORDER_TERMINAL", order.status, status_code=409)
            status = SendCashStatus(scenario); order.outgoing_payment_status = status.value; order.updated_at = self.clock.now()
            if status in {SendCashStatus.SUCCESS, SendCashStatus.UNKNOWN_AFTER_TIMEOUT}:
                self._transfer_reserved(session, order_no=order_no, kind="FIAT", from_account=BOT, to_account=f"merchant:{order.merchant_no}", currency=order.fiat, amount=D(str(order.fiat_amount)), entry_type="FIAT_PAYMENT")
                if order.status == OrderStatus.AWAITING_PAYMENT.value: self._transition(session, order, OrderStatus.PAYMENT_INITIATED, actor="BOT", event_type="SEND_CASH_PLACEHOLDER", payload={"result": status.value})
            elif status == SendCashStatus.PENDING:
                if order.status == OrderStatus.AWAITING_PAYMENT.value: self._transition(session, order, OrderStatus.PAYMENT_INITIATED, actor="BOT", event_type="SEND_CASH_PLACEHOLDER", payload={"result": status.value})
                session.add(ScheduledEventRow(simulation_id=self.simulation_id, event_type="OUTGOING_PAYMENT_CONFIRM", entity_id=order_no, payload_json="{}", due_at=self.clock.now() + timedelta(seconds=30), status="PENDING"))
            result = {"order_no": order_no, "status": status.value}; session.add(IdempotencyRow(key=idem_key, simulation_id=self.simulation_id, operation="SEND_CASH", entity_id=order_no, response_json=json.dumps(result), created_at=self.clock.now())); session.commit(); self._emit("PAYMENT_PLACEHOLDER", order_no, result, correlation_id=order.bot_trade_id); return result

    def mark_paid(self, order_no: str, *, idempotency_key: str, actor: str = "BOT") -> dict[str, Any]:
        idem_key = f"MARK_PAID:{order_no}:{idempotency_key}"
        with self.db.session() as session:
            idem = session.get(IdempotencyRow, idem_key); order = self._order(session, order_no)
            if idem: return self._order_dict(session, order)
            if order.side == "BUY" and order.outgoing_payment_status not in {SendCashStatus.SUCCESS.value, SendCashStatus.UNKNOWN_AFTER_TIMEOUT.value}: raise SimulatorError("PAYMENT_NOT_SENT", "send-cash placeholder has not confirmed payment", status_code=409)
            if order.status == OrderStatus.BUYER_MARKED_PAID.value: return self._order_dict(session, order)
            if order.status not in {OrderStatus.AWAITING_PAYMENT.value, OrderStatus.PAYMENT_INITIATED.value}: raise SimulatorError("MARK_PAID_NOT_ALLOWED", order.status, status_code=409)
            if self.clock.now() > aware(order.payment_deadline): raise SimulatorError("PAYMENT_DEADLINE_PASSED", order.payment_deadline.isoformat(), status_code=409)
            self._transition(session, order, OrderStatus.BUYER_MARKED_PAID, actor=actor, event_type="BUYER_MARKED_PAID"); session.add(IdempotencyRow(key=idem_key, simulation_id=self.simulation_id, operation="MARK_PAID", entity_id=order_no, created_at=self.clock.now()))
            if order.side == "BUY": session.add(ScheduledEventRow(simulation_id=self.simulation_id, event_type="COUNTERPARTY_SELLER_ACT", entity_id=order_no, payload_json="{}", due_at=self.clock.now() + timedelta(seconds=PROFILE_CONFIGS[order.merchant_profile]["release_delay"]), status="PENDING"))
            session.commit(); self._emit("BUYER_MARKED_PAID", order_no, {"actor": actor}, correlation_id=order.bot_trade_id); return self._order_dict(session, order)

    def verify_cash(self, order_no: str) -> dict[str, Any]:
        with self.db.session() as session:
            order = self._order(session, order_no)
            if order.side != "SELL": raise SimulatorError("WRONG_ORDER_SIDE", "verify-cash is for bot SELL flow", status_code=409)
            result = self._verify_cash_session(session, order); order.incoming_verification_status = result.status.value
            if result.status == VerifyCashStatus.VERIFIED and order.status in {OrderStatus.BUYER_MARKED_PAID.value, OrderStatus.PAYMENT_EVIDENCE_PENDING.value}:
                if order.status == OrderStatus.BUYER_MARKED_PAID.value: self._transition(session, order, OrderStatus.PAYMENT_EVIDENCE_PENDING, actor="BOT", event_type="VERIFY_CASH_STARTED")
                self._transition(session, order, OrderStatus.PAYMENT_VERIFIED, actor="BOT", event_type="PAYMENT_VERIFIED"); self._transition(session, order, OrderStatus.AWAITING_RELEASE, actor="SYSTEM", event_type="AWAITING_RELEASE")
            elif result.status in {VerifyCashStatus.MISMATCH, VerifyCashStatus.AMBIGUOUS} and order.status not in {OrderStatus.DISPUTE_OPENED.value, OrderStatus.MANUAL_INTERVENTION.value}:
                if order.status in {OrderStatus.BUYER_MARKED_PAID.value, OrderStatus.PAYMENT_EVIDENCE_PENDING.value}:
                    if order.status == OrderStatus.BUYER_MARKED_PAID.value: self._transition(session, order, OrderStatus.PAYMENT_EVIDENCE_PENDING, actor="BOT", event_type="VERIFY_CASH_STARTED")
                    self._transition(session, order, OrderStatus.MANUAL_INTERVENTION, actor="SYSTEM", event_type="PAYMENT_MISMATCH", payload={"reasons": list(result.reasons)})
            session.commit(); self._emit("PAYMENT_CHECK", order_no, {"status": result.status.value, "reasons": list(result.reasons)}, correlation_id=order.bot_trade_id); return {"order_no": order_no, "status": result.status.value, "reasons": list(result.reasons)}

    def _verify_cash_session(self, session, order: OrderRow) -> PaymentCheck:
        rows = session.scalars(select(PaymentEvidenceRow).where(PaymentEvidenceRow.order_no == order.order_no).order_by(PaymentEvidenceRow.id)).all(); matching = []; mismatch_reasons: list[str] = []
        for r in rows:
            reasons = []
            if r.status not in {"BOOKED", "COMPLETED", "SUCCESS", "CREDITED"}: reasons.append("payment_not_final")
            if r.currency != order.fiat: reasons.append("currency_mismatch")
            if D(str(r.amount)) != D(str(order.fiat_amount)): reasons.append("amount_mismatch")
            expected_name = self._merchant_nickname(session, order.merchant_no)
            if r.counterparty and r.counterparty != expected_name: reasons.append("counterparty_mismatch")
            if reasons: mismatch_reasons.extend(reasons)
            else: matching.append(r)
        if len(matching) > 1: return PaymentCheck(VerifyCashStatus.AMBIGUOUS, ("duplicate_matching_evidence",))
        if len(matching) == 1: return PaymentCheck(VerifyCashStatus.VERIFIED, ())
        if rows and mismatch_reasons: return PaymentCheck(VerifyCashStatus.MISMATCH, tuple(dict.fromkeys(mismatch_reasons)))
        return PaymentCheck(VerifyCashStatus.WAITING, ("payment_not_confirmed",))

    def release(self, order_no: str, *, idempotency_key: str, actor: str = "BOT") -> dict[str, Any]:
        idem_key = f"RELEASE:{order_no}:{idempotency_key}"
        with self.db.session() as session:
            idem = session.get(IdempotencyRow, idem_key); order = self._order(session, order_no)
            if idem: return self._order_dict(session, order)
            if order.status in {OrderStatus.CRYPTO_RELEASED.value, OrderStatus.COMPLETED.value}: return self._order_dict(session, order)
            if order.side == "SELL" and order.status != OrderStatus.AWAITING_RELEASE.value: raise SimulatorError("RELEASE_REQUIRES_VERIFIED_PAYMENT", order.status, status_code=409)
            if order.side == "BUY" and actor != "COUNTERPARTY": raise SimulatorError("RELEASE_ACTOR_INVALID", "merchant counterparty releases BUY orders", status_code=409)
            if order.side == "BUY" and order.status not in {OrderStatus.BUYER_MARKED_PAID.value, OrderStatus.AWAITING_RELEASE.value}: raise SimulatorError("RELEASE_NOT_ALLOWED", order.status, status_code=409)
            if order.side == "BUY" and order.status == OrderStatus.BUYER_MARKED_PAID.value: self._transition(session, order, OrderStatus.AWAITING_RELEASE, actor="SYSTEM", event_type="AWAITING_RELEASE")
            self._transfer_reserved(session, order_no=order_no, kind="ASSET", from_account=order.seller_account, to_account=order.buyer_account, currency=order.asset, amount=D(str(order.asset_amount)), entry_type="ASSET_RELEASE")
            fiat_res = session.scalars(select(ReservationRow).where(ReservationRow.order_no == order_no, ReservationRow.kind == "FIAT")).one_or_none()
            if fiat_res and fiat_res.status == "ACTIVE":
                if order.side == "SELL": self._transfer_reserved(session, order_no=order_no, kind="FIAT", from_account=order.buyer_account, to_account=order.seller_account, currency=order.fiat, amount=D(str(order.fiat_amount)), entry_type="FIAT_PAYMENT")
                elif order.outgoing_payment_status in {SendCashStatus.SUCCESS.value, SendCashStatus.UNKNOWN_AFTER_TIMEOUT.value}: self._transfer_reserved(session, order_no=order_no, kind="FIAT", from_account=order.buyer_account, to_account=order.seller_account, currency=order.fiat, amount=D(str(order.fiat_amount)), entry_type="FIAT_PAYMENT")
            self._transition(session, order, OrderStatus.CRYPTO_RELEASED, actor=actor, event_type="CRYPTO_RELEASED"); self._transition(session, order, OrderStatus.COMPLETED, actor="SYSTEM", event_type="ORDER_COMPLETED"); order.completed_at = self.clock.now(); session.add(IdempotencyRow(key=idem_key, simulation_id=self.simulation_id, operation="RELEASE", entity_id=order_no, created_at=self.clock.now())); self._update_merchant_metrics(session, order, completed=True); session.commit(); self._emit("ORDER_COMPLETED", order_no, {"side": order.side}, correlation_id=order.bot_trade_id); return self._order_dict(session, order)

    def cancel(self, order_no: str, *, idempotency_key: str, actor: str = "BOT") -> dict[str, Any]:
        idem_key = f"CANCEL:{order_no}:{idempotency_key}"
        with self.db.session() as session:
            idem = session.get(IdempotencyRow, idem_key); order = self._order(session, order_no)
            if idem or order.status == OrderStatus.CANCELLED.value: return self._order_dict(session, order)
            if order.status in {OrderStatus.BUYER_MARKED_PAID.value, OrderStatus.PAYMENT_EVIDENCE_PENDING.value, OrderStatus.PAYMENT_VERIFIED.value, OrderStatus.AWAITING_RELEASE.value}: self._transition(session, order, OrderStatus.MANUAL_INTERVENTION, actor=actor, event_type="CANCEL_AFTER_PAYMENT_BLOCKED")
            elif OrderStatus(order.status) in TERMINAL_ORDER_STATUSES: return self._order_dict(session, order)
            else: self._transition(session, order, OrderStatus.CANCELLED, actor=actor, event_type="ORDER_CANCELLED"); self._release_reservations(session, order_no); self._update_merchant_metrics(session, order, completed=False)
            session.add(IdempotencyRow(key=idem_key, simulation_id=self.simulation_id, operation="CANCEL", entity_id=order_no, created_at=self.clock.now())); session.commit(); self._emit("ORDER_CANCELLED", order_no, {"actor": actor}, correlation_id=order.bot_trade_id); return self._order_dict(session, order)

    def open_dispute(self, order_no: str, *, reason: str, idempotency_key: str, actor: str = "BOT") -> dict[str, Any]:
        idem_key = f"DISPUTE:{order_no}:{idempotency_key}"
        with self.db.session() as session:
            order = self._order(session, order_no); existing = session.scalars(select(DisputeRow).where(DisputeRow.order_no == order_no)).one_or_none()
            if existing: return self._dispute_dict(existing)
            if OrderStatus(order.status) in TERMINAL_ORDER_STATUSES: raise SimulatorError("ORDER_TERMINAL", order.status, status_code=409)
            self._transition(session, order, OrderStatus.DISPUTE_OPENED, actor=actor, event_type="DISPUTE_OPENED", payload={"reason": reason}); dispute = DisputeRow(simulation_id=self.simulation_id, order_no=order_no, reason=reason, evidence_json="{}", status="OPEN", opened_at=self.clock.now()); session.add(dispute); session.add(IdempotencyRow(key=idem_key, simulation_id=self.simulation_id, operation="OPEN_DISPUTE", entity_id=order_no, created_at=self.clock.now())); session.commit(); session.refresh(dispute); self._emit("DISPUTE_OPENED", order_no, {"reason": reason}, correlation_id=order.bot_trade_id); return self._dispute_dict(dispute)

    def resolve_dispute(self, order_no: str, *, winner: str) -> dict[str, Any]:
        winner = winner.upper()
        if winner not in {"BUYER", "SELLER"}: raise SimulatorError("INVALID_WINNER", winner)
        with self.db.session() as session:
            order = self._order(session, order_no); dispute = session.scalars(select(DisputeRow).where(DisputeRow.order_no == order_no)).one_or_none()
            if dispute is None: raise SimulatorError("DISPUTE_NOT_FOUND", order_no, status_code=404)
            if dispute.status != "OPEN": return self._dispute_dict(dispute)
            if order.status == OrderStatus.DISPUTE_OPENED.value: self._transition(session, order, OrderStatus.UNDER_REVIEW, actor="ADMIN", event_type="DISPUTE_UNDER_REVIEW")
            if winner == "BUYER":
                self._transfer_reserved(session, order_no=order_no, kind="ASSET", from_account=order.seller_account, to_account=order.buyer_account, currency=order.asset, amount=D(str(order.asset_amount)), entry_type="DISPUTE_ASSET_TO_BUYER"); fiat_res = session.scalars(select(ReservationRow).where(ReservationRow.order_no == order_no, ReservationRow.kind == "FIAT")).one_or_none()
                if fiat_res and fiat_res.status == "ACTIVE": self._release_one_reservation(session, fiat_res)
                self._transition(session, order, OrderStatus.RESOLVED_BUYER, actor="ADMIN", event_type="DISPUTE_RESOLVED_BUYER")
            else:
                self._release_reservations(session, order_no); self._transition(session, order, OrderStatus.RESOLVED_SELLER, actor="ADMIN", event_type="DISPUTE_RESOLVED_SELLER")
            dispute.status = "RESOLVED"; dispute.resolution = winner; dispute.resolved_at = self.clock.now(); session.commit(); self._emit("DISPUTE_RESOLVED", order_no, {"winner": winner}, correlation_id=order.bot_trade_id); return self._dispute_dict(dispute)

    def _release_one_reservation(self, session, reservation: ReservationRow) -> None:
        if reservation.status != "ACTIVE": return
        bal = self._balance(session, reservation.account_id, reservation.currency); bal.reserved = D(str(bal.reserved)) - D(str(reservation.amount)); bal.updated_at = self.clock.now(); reservation.status = "RELEASED"; reservation.consumed_at = self.clock.now()

    def force_expire(self, order_no: str) -> dict[str, Any]:
        with self.db.session() as session:
            order = self._order(session, order_no); self._expire_order(session, order); session.commit(); return self._order_dict(session, order)

    def _expire_order(self, session, order: OrderRow) -> None:
        if OrderStatus(order.status) in TERMINAL_ORDER_STATUSES: return
        if order.status in {OrderStatus.BUYER_MARKED_PAID.value, OrderStatus.PAYMENT_EVIDENCE_PENDING.value, OrderStatus.PAYMENT_VERIFIED.value, OrderStatus.AWAITING_RELEASE.value}: self._transition(session, order, OrderStatus.MANUAL_INTERVENTION, actor="SYSTEM", event_type="LATE_PAYMENT_MANUAL_REVIEW")
        else: self._transition(session, order, OrderStatus.EXPIRED, actor="SYSTEM", event_type="ORDER_EXPIRED"); self._release_reservations(session, order.order_no); self._update_merchant_metrics(session, order, completed=False)

    def _transition(self, session, order: OrderRow, target: OrderStatus, *, actor: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        current = order.status; assert_transition(current, target); order.status = target.value; order.updated_at = self.clock.now(); session.add(OrderEventRow(simulation_id=self.simulation_id, order_no=order.order_no, from_status=current, to_status=target.value, actor=actor, event_type=event_type, payload_json=json.dumps(payload or {}, default=str), created_at=self.clock.now()))

    def order_timeline(self, order_no: str) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(OrderEventRow).where(OrderEventRow.order_no == order_no).order_by(OrderEventRow.id)).all(); return [{"id": r.id, "from": r.from_status, "to": r.to_status, "actor": r.actor, "event_type": r.event_type, "payload": json.loads(r.payload_json), "created_at": r.created_at.isoformat()} for r in rows]

    def _order_dict(self, session, order: OrderRow) -> dict[str, Any]:
        return {"order_no": order.order_no, "ad_no": order.ad_no, "bot_trade_id": order.bot_trade_id, "side": order.side, "asset": order.asset, "fiat": order.fiat, "asset_amount": str(order.asset_amount), "fiat_amount": str(order.fiat_amount), "unit_price": str(order.unit_price), "payment_method": order.payment_method, "merchant_no": order.merchant_no, "merchant_profile": order.merchant_profile, "status": order.status, "outgoing_payment_status": order.outgoing_payment_status, "incoming_verification_status": order.incoming_verification_status, "payment_deadline": order.payment_deadline.isoformat(), "created_at": order.created_at.isoformat(), "updated_at": order.updated_at.isoformat(), "completed_at": order.completed_at.isoformat() if order.completed_at else None}

    def _counterparty_seller_act(self, order_no: str) -> None:
        with self.db.session() as session:
            order = self._order(session, order_no)
            if order.status != OrderStatus.BUYER_MARKED_PAID.value: return
            decision = self._profile_decision(order, "seller_release")
            if decision == "GHOST": self._emit("COUNTERPARTY_GHOST", order_no, {}, correlation_id=order.bot_trade_id); return
            if decision == "DISPUTE": session.commit(); self.open_dispute(order_no, reason="counterparty_dispute", idempotency_key=f"cp-{order_no}", actor="COUNTERPARTY"); return
        self.release(order_no, idempotency_key=f"cp-release-{order_no}", actor="COUNTERPARTY")

    def _counterparty_buyer_act(self, order_no: str) -> None:
        with self.db.session() as session:
            order = self._order(session, order_no)
            if order.status not in {OrderStatus.AWAITING_PAYMENT.value, OrderStatus.PAYMENT_INITIATED.value}: return
            decision = self._profile_decision(order, "buyer_payment")
            if decision == "GHOST": self._emit("COUNTERPARTY_GHOST", order_no, {}, correlation_id=order.bot_trade_id); return
            if decision == "CANCEL": session.commit(); self.cancel(order_no, idempotency_key=f"cp-cancel-{order_no}", actor="COUNTERPARTY"); return
            if decision == "DISPUTE": self._transition(session, order, OrderStatus.BUYER_MARKED_PAID, actor="COUNTERPARTY", event_type="COUNTERPARTY_MARKED_PAID"); session.commit(); self.open_dispute(order_no, reason="counterparty_dispute", idempotency_key=f"cp-dsp-{order_no}", actor="COUNTERPARTY"); return
            self._transition(session, order, OrderStatus.BUYER_MARKED_PAID, actor="COUNTERPARTY", event_type="COUNTERPARTY_MARKED_PAID"); scenario = "MISSING" if decision == "FALSE_PAID" else "WRONG_AMOUNT" if decision == "WRONG_PAYMENT" else "SUCCESS"
            if scenario != "MISSING": self._add_payment_evidence(session, order, scenario=scenario)
            session.commit(); self._emit("COUNTERPARTY_MARKED_PAID", order_no, {"scenario": scenario}, correlation_id=order.bot_trade_id)

    def _profile_decision(self, order: OrderRow, purpose: str) -> str:
        profile = PROFILE_CONFIGS[order.merchant_profile]; sample = DeterministicRandom(self._seed()).decision_float(f"order:{order.order_no}:{purpose}"); cuts = [(profile.get("ghost_p", 0), "GHOST"), (profile.get("cancel_p", 0), "CANCEL"), (profile.get("dispute_p", 0), "DISPUTE"), (profile.get("false_paid_p", 0), "FALSE_PAID"), (profile.get("wrong_payment_p", 0), "WRONG_PAYMENT")]; total = 0.0
        for probability, label in cuts:
            total += float(probability)
            if sample < total: return label
        return "SUCCESS"

    def force_payment(self, order_no: str, scenario: str) -> dict[str, Any]:
        scenario = scenario.upper()
        with self.db.session() as session:
            order = self._order(session, order_no)
            if order.side != "SELL": raise SimulatorError("WRONG_ORDER_SIDE", "incoming payment evidence applies to SELL order", status_code=409)
            if order.status in {OrderStatus.AWAITING_PAYMENT.value, OrderStatus.PAYMENT_INITIATED.value}: self._transition(session, order, OrderStatus.BUYER_MARKED_PAID, actor="ADMIN", event_type="ADMIN_MARKED_PAID")
            if scenario != "MISSING": self._add_payment_evidence(session, order, scenario=scenario)
            session.commit()
        self._admin("FORCE_PAYMENT", {"order_no": order_no, "scenario": scenario}); return self.get_order(order_no)

    def _add_payment_evidence(self, session, order: OrderRow, *, scenario: str) -> None:
        amount = D(str(order.fiat_amount)); currency = order.fiat; counterparty = self._merchant_nickname(session, order.merchant_no); status = "BOOKED"
        if scenario == "WRONG_AMOUNT": amount += D("1")
        elif scenario == "WRONG_CURRENCY": currency = "USD"
        elif scenario == "WRONG_COUNTERPARTY": counterparty = "Different Person"
        elif scenario == "PENDING": status = "PENDING"
        count = 2 if scenario == "DUPLICATE" else 1
        for idx in range(count): session.add(PaymentEvidenceRow(simulation_id=self.simulation_id, order_no=order.order_no, evidence_id=f"PE-{order.order_no}-{scenario}-{idx}-{uuid.uuid4().hex[:6]}", direction="IN", amount=amount, currency=currency, counterparty=counterparty, reference=order.order_no, status=status, scenario=scenario, created_at=self.clock.now()))

    def payment_evidence(self, order_no: str) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(PaymentEvidenceRow).where(PaymentEvidenceRow.order_no == order_no).order_by(PaymentEvidenceRow.id)).all(); return [{"evidence_id": r.evidence_id, "amount": str(r.amount), "currency": r.currency, "counterparty": r.counterparty, "reference": r.reference, "status": r.status, "scenario": r.scenario, "created_at": r.created_at.isoformat()} for r in rows]

    def run_due_events(self, limit: int = 100) -> int:
        now = self.clock.now(); lease_cutoff = now - timedelta(seconds=self.settings.scheduler_lease_seconds); claimed_ids: list[int] = []
        with self.db.session() as session:
            rows = session.scalars(select(ScheduledEventRow).where(ScheduledEventRow.simulation_id == self.simulation_id, ScheduledEventRow.due_at <= now, or_(ScheduledEventRow.status == "PENDING", ((ScheduledEventRow.status == "PROCESSING") & (ScheduledEventRow.claimed_at < lease_cutoff)))).order_by(ScheduledEventRow.due_at, ScheduledEventRow.id).limit(limit)).all()
            for row in rows: row.status = "PROCESSING"; row.claimed_at = now; claimed_ids.append(row.id)
            session.commit()
        processed = 0
        for event_id in claimed_ids:
            with self.db.session() as session:
                row = session.get(ScheduledEventRow, event_id)
                if row is None or row.status != "PROCESSING": continue
                event_type = row.event_type; entity_id = row.entity_id
            try:
                if event_type == "ORDER_EXPIRE" and entity_id:
                    with self.db.session() as session: order = self._order(session, entity_id); self._expire_order(session, order); session.commit()
                elif event_type == "COUNTERPARTY_SELLER_ACT" and entity_id: self._counterparty_seller_act(entity_id)
                elif event_type == "COUNTERPARTY_BUYER_ACT" and entity_id: self._counterparty_buyer_act(entity_id)
                elif event_type == "OUTGOING_PAYMENT_CONFIRM" and entity_id:
                    with self.db.session() as session:
                        order = self._order(session, entity_id)
                        if order.outgoing_payment_status == SendCashStatus.PENDING.value: order.outgoing_payment_status = SendCashStatus.SUCCESS.value; self._transfer_reserved(session, order_no=order.order_no, kind="FIAT", from_account=BOT, to_account=f"merchant:{order.merchant_no}", currency=order.fiat, amount=D(str(order.fiat_amount)), entry_type="FIAT_PAYMENT"); session.commit()
                elif event_type == "MARKET_TICK": self.market_tick()
                with self.db.session() as session:
                    row = session.get(ScheduledEventRow, event_id)
                    if row: row.status = "DONE"; row.completed_at = self.clock.now(); row.error = None; session.commit()
                processed += 1
            except Exception as exc:
                with self.db.session() as session:
                    row = session.get(ScheduledEventRow, event_id)
                    if row: row.status = "PENDING"; row.error = str(exc); row.claimed_at = None; session.commit()
                raise
        return processed

    def scheduled_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(ScheduledEventRow).where(ScheduledEventRow.simulation_id == self.simulation_id).order_by(ScheduledEventRow.due_at).limit(limit)).all(); return [{"id": r.id, "event_type": r.event_type, "entity_id": r.entity_id, "due_at": r.due_at.isoformat(), "status": r.status, "error": r.error} for r in rows]

    def send_chat(self, order_no: str, *, sender: str, body: str, idempotency_key: str | None = None) -> dict[str, Any]:
        body = body.strip()
        if not body: raise SimulatorError("EMPTY_MESSAGE", "message body required")
        with self.db.session() as session:
            self._order(session, order_no)
            if idempotency_key:
                existing = session.scalars(select(ChatMessageRow).where(ChatMessageRow.client_idempotency_key == idempotency_key)).one_or_none()
                if existing: return self._chat_dict(existing)
            msg = ChatMessageRow(simulation_id=self.simulation_id, order_no=order_no, sender=sender, body=body, client_idempotency_key=idempotency_key, created_at=self.clock.now()); session.add(msg); session.commit(); session.refresh(msg); self._emit("CHAT_MESSAGE", order_no, {"message_id": msg.id, "sender": sender}); return self._chat_dict(msg)

    def chat_history(self, order_no: str) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(ChatMessageRow).where(ChatMessageRow.order_no == order_no).order_by(ChatMessageRow.id)).all(); return [self._chat_dict(r) for r in rows]

    @staticmethod
    def _chat_dict(row: ChatMessageRow) -> dict[str, Any]: return {"id": row.id, "order_no": row.order_no, "sender": row.sender, "body": row.body, "created_at": row.created_at.isoformat()}

    def set_fault(self, name: str, kind: FaultKind, *, remaining: int = 1, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if remaining < 1: raise SimulatorError("INVALID_FAULT_COUNT", "remaining must be >=1")
        with self.db.session() as session: session.merge(FaultRow(name=name, simulation_id=self.simulation_id, kind=kind.value, remaining=remaining, payload_json=json.dumps(payload or {}), enabled=True, created_at=self.clock.now())); session.commit()
        self._admin("SET_FAULT", {"name": name, "kind": kind.value, "remaining": remaining}); return {"name": name, "kind": kind.value, "remaining": remaining}

    def consume_fault(self, name: str) -> dict[str, Any] | None:
        with self.db.session() as session:
            row = session.get(FaultRow, name)
            if row is None or not row.enabled or row.remaining <= 0: return None
            result = {"name": row.name, "kind": row.kind, "payload": json.loads(row.payload_json)}; row.remaining -= 1
            if row.remaining <= 0: row.enabled = False
            session.commit(); return result

    def faults(self) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(FaultRow).where(FaultRow.simulation_id == self.simulation_id).order_by(FaultRow.name)).all(); return [{"name": r.name, "kind": r.kind, "remaining": r.remaining, "enabled": r.enabled, "payload": json.loads(r.payload_json)} for r in rows]

    def personal_order_history(self, *, page: int = 1, rows: int = 20, trade_type: str | None = None) -> dict[str, Any]:
        with self.db.session() as session:
            q = select(OrderRow).where(OrderRow.simulation_id == self.simulation_id)
            if trade_type: q = q.where(OrderRow.side == trade_type.upper())
            all_rows = session.scalars(q.order_by(OrderRow.created_at.desc())).all(); start = max(0, (page - 1) * rows); selected = all_rows[start:start + rows]; return {"data": {"total": len(all_rows), "data": [self._binance_order_dict(o) for o in selected]}}

    def order_summary(self) -> dict[str, Any]:
        with self.db.session() as session:
            total = session.scalar(select(func.count()).select_from(OrderRow).where(OrderRow.simulation_id == self.simulation_id)) or 0; completed = session.scalar(select(func.count()).select_from(OrderRow).where(OrderRow.simulation_id == self.simulation_id, OrderRow.status == OrderStatus.COMPLETED.value)) or 0; return {"data": {"totalOrderCount": int(total), "completedOrderCount": int(completed)}}

    @staticmethod
    def _binance_order_dict(o: OrderRow) -> dict[str, Any]: return {"orderNumber": o.order_no, "tradeType": o.side, "orderStatus": o.status, "asset": o.asset, "fiat": o.fiat, "amount": str(o.asset_amount), "totalPrice": str(o.fiat_amount), "unitPrice": str(o.unit_price)}

    def events(self, *, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self.db.session() as session:
            rows = session.scalars(select(DomainEventRow).where(DomainEventRow.simulation_id == self.simulation_id, DomainEventRow.id > after_id).order_by(DomainEventRow.id).limit(limit)).all(); return [self._domain_event_dict(x) for x in rows]

    @staticmethod
    def _domain_event_dict(row: DomainEventRow) -> dict[str, Any]: return {"id": row.id, "event_type": row.event_type, "entity_id": row.entity_id, "correlation_id": row.correlation_id, "payload": json.loads(row.payload_json), "created_at": row.created_at.isoformat()}

    def metrics(self) -> dict[str, Any]:
        with self.db.session() as session:
            counts = {status.value: int(session.scalar(select(func.count()).select_from(OrderRow).where(OrderRow.simulation_id == self.simulation_id, OrderRow.status == status.value)) or 0) for status in OrderStatus}; active = sum(v for k, v in counts.items() if OrderStatus(k) not in TERMINAL_ORDER_STATUSES); scheduler_due = int(session.scalar(select(func.count()).select_from(ScheduledEventRow).where(ScheduledEventRow.simulation_id == self.simulation_id, ScheduledEventRow.status == "PENDING", ScheduledEventRow.due_at <= self.clock.now())) or 0); return {"orders": counts, "active_orders": active, "scheduler_due": scheduler_due, "reconciliation": self.reconcile_balances()}

    def _emit(self, event_type: str, entity_id: str | None, payload: dict[str, Any], correlation_id: str | None = None) -> None:
        with self.db.session() as session: session.add(DomainEventRow(simulation_id=self.simulation_id, event_type=event_type, entity_id=entity_id, correlation_id=correlation_id, payload_json=json.dumps(payload, default=str), created_at=self.clock.now())); session.commit()

    def _admin(self, action: str, payload: dict[str, Any]) -> None:
        with self.db.session() as session: session.add(AdminActionRow(simulation_id=self.simulation_id, action=action, payload_json=json.dumps(payload, default=str), created_at=self.clock.now())); session.add(DomainEventRow(simulation_id=self.simulation_id, event_type=f"ADMIN_{action}", entity_id=None, correlation_id=None, payload_json=json.dumps(payload, default=str), created_at=self.clock.now())); session.commit()

    def _ad(self, session, ad_no: str) -> AdRow:
        ad = session.get(AdRow, ad_no)
        if ad is None or ad.simulation_id != self.simulation_id: raise SimulatorError("AD_NOT_FOUND", ad_no, status_code=404)
        return ad

    def _order(self, session, order_no: str) -> OrderRow:
        order = session.get(OrderRow, order_no)
        if order is None or order.simulation_id != self.simulation_id: raise SimulatorError("ORDER_NOT_FOUND", order_no, status_code=404)
        return order

    def _merchant_nickname(self, session, merchant_no: str) -> str:
        m = session.get(MerchantRow, merchant_no); return m.nickname if m else merchant_no

    def _update_merchant_metrics(self, session, order: OrderRow, *, completed: bool) -> None:
        merchant = session.get(MerchantRow, order.merchant_no)
        if merchant is None: return
        old_orders = max(1, merchant.order_count); merchant.order_count = old_orders + 1; old_completed = merchant.completion_rate_pct / 100 * old_orders; new_completed = old_completed + (1 if completed else 0); merchant.completion_rate_pct = max(0.0, min(100.0, new_completed / merchant.order_count * 100))

    @staticmethod
    def _dispute_dict(d: DisputeRow) -> dict[str, Any]: return {"id": d.id, "order_no": d.order_no, "reason": d.reason, "status": d.status, "resolution": d.resolution, "opened_at": d.opened_at.isoformat(), "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None}
