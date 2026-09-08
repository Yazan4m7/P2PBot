from __future__ import annotations

import uuid
from dataclasses import replace
from decimal import Decimal

from .domain import Opportunity, PaperTrade, TradeState, utcnow
from .risk import RiskContext, RiskPolicy
from .state_machine import transition


class PaperExecutionEngine:
    def __init__(self, risk_policy: RiskPolicy):
        self.risk_policy = risk_policy

    def execute(self, opportunity: Opportunity, context: RiskContext) -> PaperTrade:
        trade_id = uuid.uuid4().hex
        buy_cost = opportunity.asset_amount * opportunity.buy_price
        sell_revenue = buy_cost + opportunity.net_profit_fiat
        trade = PaperTrade(
            trade_id=trade_id,
            opportunity=opportunity,
            state=TradeState.CREATED,
            buy_cost_fiat=buy_cost,
            sell_revenue_fiat=sell_revenue,
            realized_profit_fiat=Decimal('0'),
        )
        decision = self.risk_policy.evaluate(opportunity, context)
        if not decision.allowed:
            return replace(trade, state=TradeState.MANUAL_REVIEW)

        state = transition(trade.state, TradeState.RISK_APPROVED)
        # Paper mode models the whole lifecycle but performs no external action.
        for target in (
            TradeState.BUY_ORDER_PROPOSED,
            TradeState.BUY_ORDER_OPEN,
            TradeState.BUY_PAYMENT_PROPOSED,
            TradeState.BUY_MARKED_PAID,
            TradeState.ASSET_RECEIVED,
            TradeState.SELL_ORDER_PROPOSED,
            TradeState.SELL_ORDER_OPEN,
            TradeState.SELL_PAYMENT_DETECTED,
            TradeState.SELL_PAYMENT_VERIFIED,
            TradeState.RELEASE_PROPOSED,
            TradeState.COMPLETED,
        ):
            state = transition(state, target)
        return replace(
            trade,
            state=state,
            realized_profit_fiat=opportunity.net_profit_fiat,
            completed_at=utcnow(),
        )
