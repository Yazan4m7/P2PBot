from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from .domain import Opportunity


@dataclass(frozen=True, slots=True)
class RiskContext:
    daily_turnover_fiat: Decimal = Decimal('0')
    daily_pnl_fiat: Decimal = Decimal('0')
    open_trades: int = 0
    merchant_exposure_fiat: dict[str, Decimal] = field(default_factory=dict)
    market_age_seconds: float = 0.0
    recent_price_jump_pct: float = 0.0
    kill_switch: bool = False


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    max_trade_fiat: Decimal
    max_daily_turnover_fiat: Decimal
    max_daily_loss_fiat: Decimal
    max_open_trades: int
    max_merchant_exposure_fiat: Decimal
    min_merchant_score: float
    stale_market_seconds: float
    max_price_jump_pct: float

    def evaluate(self, opportunity: Opportunity, context: RiskContext) -> RiskDecision:
        reasons: list[str] = []
        trade_notional = opportunity.asset_amount * opportunity.buy_price
        if context.kill_switch:
            reasons.append('kill_switch_enabled')
        if trade_notional > self.max_trade_fiat:
            reasons.append('trade_size_limit')
        if context.daily_turnover_fiat + trade_notional > self.max_daily_turnover_fiat:
            reasons.append('daily_turnover_limit')
        if context.daily_pnl_fiat <= -self.max_daily_loss_fiat:
            reasons.append('daily_loss_limit')
        if context.open_trades >= self.max_open_trades:
            reasons.append('open_trade_limit')
        if min(opportunity.buy_merchant_score, opportunity.sell_merchant_score) < self.min_merchant_score:
            reasons.append('merchant_score_below_minimum')
        if context.market_age_seconds > self.stale_market_seconds:
            reasons.append('stale_market_data')
        if abs(context.recent_price_jump_pct) > self.max_price_jump_pct:
            reasons.append('price_anomaly')
        for merchant_no in (opportunity.buy_merchant_no, opportunity.sell_merchant_no):
            exposure = context.merchant_exposure_fiat.get(merchant_no, Decimal('0'))
            if exposure + trade_notional > self.max_merchant_exposure_fiat:
                reasons.append(f'merchant_exposure_limit:{merchant_no}')
        return RiskDecision(allowed=not reasons, reasons=tuple(reasons))


def utc_day_start_ms() -> int:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)
