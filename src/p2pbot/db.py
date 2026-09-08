from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Float, Integer, Numeric, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .domain import Ad, Opportunity, PaperTrade


class Base(DeclarativeBase):
    pass


class MerchantRow(Base):
    __tablename__ = 'merchants'
    merchant_no: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(255))
    completion_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_release_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    merchant_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AdSnapshotRow(Base):
    __tablename__ = 'ad_snapshots'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ad_no: Mapped[str] = mapped_column(String(128), index=True)
    merchant_no: Mapped[str] = mapped_column(String(128), index=True)
    trade_type: Mapped[str] = mapped_column(String(8), index=True)
    asset: Mapped[str] = mapped_column(String(20), index=True)
    fiat: Mapped[str] = mapped_column(String(20), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    available_asset: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    min_fiat: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    max_fiat: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    payment_methods_json: Mapped[str] = mapped_column(Text, default='[]')
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw_json: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint('ad_no', 'trade_type', 'observed_at', name='uq_ad_observation'),)


class OpportunityRow(Base):
    __tablename__ = 'opportunities'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buy_ad_no: Mapped[str] = mapped_column(String(128), index=True)
    sell_ad_no: Mapped[str] = mapped_column(String(128), index=True)
    buy_merchant_no: Mapped[str] = mapped_column(String(128))
    sell_merchant_no: Mapped[str] = mapped_column(String(128))
    asset: Mapped[str] = mapped_column(String(20))
    fiat: Mapped[str] = mapped_column(String(20))
    asset_amount: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    buy_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    sell_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    gross_profit_fiat: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    net_profit_fiat: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    net_roi_pct: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    buy_merchant_score: Mapped[float] = mapped_column(Float)
    sell_merchant_score: Mapped[float] = mapped_column(Float)
    common_payment_methods_json: Mapped[str] = mapped_column(Text, default='[]')
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PaperTradeRow(Base):
    __tablename__ = 'paper_trades'
    trade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(64), index=True)
    buy_ad_no: Mapped[str] = mapped_column(String(128))
    sell_ad_no: Mapped[str] = mapped_column(String(128))
    buy_merchant_no: Mapped[str] = mapped_column(String(128), index=True)
    sell_merchant_no: Mapped[str] = mapped_column(String(128), index=True)
    asset: Mapped[str] = mapped_column(String(20))
    fiat: Mapped[str] = mapped_column(String(20))
    asset_amount: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    buy_cost_fiat: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    sell_revenue_fiat: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    realized_profit_fiat: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EventRow(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default='INFO')
    payload_json: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IdempotencyRow(Base):
    __tablename__ = 'idempotency_keys'
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BotStateRow(Base):
    __tablename__ = 'bot_state'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountOrderRow(Base):
    __tablename__ = 'account_orders'
    order_number: Mapped[str] = mapped_column(String(128), primary_key=True)
    trade_type: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    asset: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fiat: Mapped[str | None] = mapped_column(String(20), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    raw_json: Mapped[str] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Repository:
    def __init__(self, database_url: str):
        connect_args = {'check_same_thread': False} if database_url.startswith('sqlite') else {}
        self.engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        if self.get_state('kill_switch') is None:
            self.set_state('kill_switch', 'false')

    def save_ads(self, ads: list[Ad]) -> None:
        with Session(self.engine) as session:
            for ad in ads:
                merchant = session.get(MerchantRow, ad.merchant.merchant_no)
                if merchant is None:
                    merchant = MerchantRow(merchant_no=ad.merchant.merchant_no, nickname=ad.merchant.nickname, updated_at=ad.observed_at)
                    session.add(merchant)
                merchant.nickname = ad.merchant.nickname
                merchant.completion_rate_pct = ad.merchant.completion_rate_pct
                merchant.order_count = ad.merchant.order_count
                merchant.avg_release_seconds = ad.merchant.avg_release_seconds
                merchant.merchant_type = ad.merchant.merchant_type
                merchant.updated_at = ad.observed_at
                session.add(AdSnapshotRow(ad_no=ad.ad_no, merchant_no=ad.merchant.merchant_no, trade_type=ad.trade_type, asset=ad.asset, fiat=ad.fiat, price=ad.price, available_asset=ad.available_asset, min_fiat=ad.min_fiat, max_fiat=ad.max_fiat, payment_methods_json=json.dumps(ad.payment_methods), observed_at=ad.observed_at, raw_json=json.dumps(ad.raw, ensure_ascii=False, default=str)))
            session.commit()

    def save_opportunities(self, opportunities: list[Opportunity]) -> None:
        with Session(self.engine) as session:
            for op in opportunities:
                session.add(OpportunityRow(buy_ad_no=op.buy_ad_no, sell_ad_no=op.sell_ad_no, buy_merchant_no=op.buy_merchant_no, sell_merchant_no=op.sell_merchant_no, asset=op.asset, fiat=op.fiat, asset_amount=op.asset_amount, buy_price=op.buy_price, sell_price=op.sell_price, gross_profit_fiat=op.gross_profit_fiat, net_profit_fiat=op.net_profit_fiat, net_roi_pct=op.net_roi_pct, buy_merchant_score=op.buy_merchant_score, sell_merchant_score=op.sell_merchant_score, common_payment_methods_json=json.dumps(op.common_payment_methods), observed_at=op.observed_at))
            session.commit()

    def recent_opportunities(self, limit: int = 50) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.scalars(select(OpportunityRow).order_by(OpportunityRow.id.desc()).limit(limit)).all()
            return [{'buy_ad_no': r.buy_ad_no, 'sell_ad_no': r.sell_ad_no, 'asset': r.asset, 'fiat': r.fiat, 'asset_amount': str(r.asset_amount), 'buy_price': str(r.buy_price), 'sell_price': str(r.sell_price), 'net_profit_fiat': str(r.net_profit_fiat), 'net_roi_pct': str(r.net_roi_pct), 'buy_merchant_score': r.buy_merchant_score, 'sell_merchant_score': r.sell_merchant_score, 'common_payment_methods': json.loads(r.common_payment_methods_json), 'observed_at': r.observed_at.isoformat()} for r in rows]

    def save_paper_trade(self, trade: PaperTrade) -> None:
        op = trade.opportunity
        with Session(self.engine) as session:
            session.merge(PaperTradeRow(trade_id=trade.trade_id, state=trade.state.value, buy_ad_no=op.buy_ad_no, sell_ad_no=op.sell_ad_no, buy_merchant_no=op.buy_merchant_no, sell_merchant_no=op.sell_merchant_no, asset=op.asset, fiat=op.fiat, asset_amount=op.asset_amount, buy_cost_fiat=trade.buy_cost_fiat, sell_revenue_fiat=trade.sell_revenue_fiat, realized_profit_fiat=trade.realized_profit_fiat, created_at=trade.created_at, completed_at=trade.completed_at))
            session.commit()

    def recent_paper_trades(self, limit: int = 50) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.scalars(select(PaperTradeRow).order_by(PaperTradeRow.created_at.desc()).limit(limit)).all()
            return [{'trade_id': r.trade_id, 'state': r.state, 'buy_ad_no': r.buy_ad_no, 'sell_ad_no': r.sell_ad_no, 'asset': r.asset, 'fiat': r.fiat, 'asset_amount': str(r.asset_amount), 'buy_cost_fiat': str(r.buy_cost_fiat), 'sell_revenue_fiat': str(r.sell_revenue_fiat), 'realized_profit_fiat': str(r.realized_profit_fiat), 'created_at': r.created_at.isoformat(), 'completed_at': r.completed_at.isoformat() if r.completed_at else None} for r in rows]

    def paper_stats(self) -> dict:
        with Session(self.engine) as session:
            count = session.scalar(select(func.count()).select_from(PaperTradeRow)) or 0
            pnl = session.scalar(select(func.coalesce(func.sum(PaperTradeRow.realized_profit_fiat), 0))) or Decimal('0')
            turnover = session.scalar(select(func.coalesce(func.sum(PaperTradeRow.buy_cost_fiat), 0))) or Decimal('0')
            open_count = session.scalar(select(func.count()).select_from(PaperTradeRow).where(PaperTradeRow.state.not_in(['COMPLETED', 'CANCELLED', 'FAILED']))) or 0
            return {'trade_count': int(count), 'pnl_fiat': str(pnl), 'turnover_fiat': str(turnover), 'open_trades': int(open_count)}

    def append_event(self, event_type: str, *, entity_id: str | None = None, severity: str = 'INFO', payload: dict | None = None) -> int:
        with Session(self.engine) as session:
            row = EventRow(event_type=event_type, entity_id=entity_id, severity=severity.upper(), payload_json=json.dumps(payload or {}, ensure_ascii=False, default=str), created_at=datetime.now(timezone.utc))
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id

    def recent_events(self, limit: int = 100) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.scalars(select(EventRow).order_by(EventRow.id.desc()).limit(limit)).all()
            return [{'id': r.id, 'event_type': r.event_type, 'entity_id': r.entity_id, 'severity': r.severity, 'payload': json.loads(r.payload_json), 'created_at': r.created_at.isoformat()} for r in rows]

    def claim_idempotency(self, key: str) -> bool:
        with Session(self.engine) as session:
            session.add(IdempotencyRow(key=key, created_at=datetime.now(timezone.utc)))
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False

    def set_state(self, key: str, value: str) -> None:
        with Session(self.engine) as session:
            session.merge(BotStateRow(key=key, value=value, updated_at=datetime.now(timezone.utc)))
            session.commit()

    def get_state(self, key: str) -> str | None:
        with Session(self.engine) as session:
            row = session.get(BotStateRow, key)
            return None if row is None else row.value

    def kill_switch_enabled(self) -> bool:
        return (self.get_state('kill_switch') or 'false').lower() == 'true'

    def save_account_orders(self, payload: object) -> int:
        if not isinstance(payload, dict):
            return 0
        data = payload.get('data', payload)
        rows = data.get('data') if isinstance(data, dict) and isinstance(data.get('data'), list) else data.get('rows') if isinstance(data, dict) else None
        if not isinstance(rows, list):
            rows = payload.get('rows') if isinstance(payload.get('rows'), list) else []
        count = 0
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            for item in rows:
                if not isinstance(item, dict):
                    continue
                order_no = item.get('orderNumber') or item.get('orderNo') or item.get('order_number')
                if not order_no:
                    continue
                def dec(key: str):
                    value = item.get(key)
                    try:
                        return Decimal(str(value)) if value is not None else None
                    except Exception:
                        return None
                session.merge(AccountOrderRow(order_number=str(order_no), trade_type=item.get('tradeType'), status=item.get('orderStatus') or item.get('status'), asset=item.get('asset'), fiat=item.get('fiat'), amount=dec('amount'), total_price=dec('totalPrice'), raw_json=json.dumps(item, ensure_ascii=False, default=str), synced_at=now))
                count += 1
            session.commit()
        return count

    def recent_account_orders(self, limit: int = 50) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.scalars(select(AccountOrderRow).order_by(AccountOrderRow.synced_at.desc()).limit(limit)).all()
            return [{'order_number': r.order_number, 'trade_type': r.trade_type, 'status': r.status, 'asset': r.asset, 'fiat': r.fiat, 'amount': str(r.amount) if r.amount is not None else None, 'total_price': str(r.total_price) if r.total_price is not None else None, 'synced_at': r.synced_at.isoformat()} for r in rows]
