from __future__ import annotations

from .domain import TradeState


class InvalidTransition(ValueError):
    pass


_ALLOWED: dict[TradeState, set[TradeState]] = {
    TradeState.CREATED: {TradeState.RISK_APPROVED, TradeState.CANCELLED, TradeState.FAILED},
    TradeState.RISK_APPROVED: {TradeState.BUY_ORDER_PROPOSED, TradeState.CANCELLED, TradeState.FAILED},
    TradeState.BUY_ORDER_PROPOSED: {TradeState.BUY_ORDER_OPEN, TradeState.MANUAL_REVIEW, TradeState.CANCELLED},
    TradeState.BUY_ORDER_OPEN: {TradeState.BUY_PAYMENT_PROPOSED, TradeState.MANUAL_REVIEW, TradeState.CANCELLED},
    TradeState.BUY_PAYMENT_PROPOSED: {TradeState.BUY_MARKED_PAID, TradeState.MANUAL_REVIEW, TradeState.CANCELLED},
    TradeState.BUY_MARKED_PAID: {TradeState.ASSET_RECEIVED, TradeState.MANUAL_REVIEW, TradeState.FAILED},
    TradeState.ASSET_RECEIVED: {TradeState.SELL_ORDER_PROPOSED, TradeState.MANUAL_REVIEW, TradeState.FAILED},
    TradeState.SELL_ORDER_PROPOSED: {TradeState.SELL_ORDER_OPEN, TradeState.MANUAL_REVIEW, TradeState.CANCELLED},
    TradeState.SELL_ORDER_OPEN: {TradeState.SELL_PAYMENT_DETECTED, TradeState.MANUAL_REVIEW, TradeState.CANCELLED},
    TradeState.SELL_PAYMENT_DETECTED: {TradeState.SELL_PAYMENT_VERIFIED, TradeState.MANUAL_REVIEW, TradeState.FAILED},
    TradeState.SELL_PAYMENT_VERIFIED: {TradeState.RELEASE_PROPOSED, TradeState.MANUAL_REVIEW, TradeState.FAILED},
    TradeState.RELEASE_PROPOSED: {TradeState.COMPLETED, TradeState.MANUAL_REVIEW, TradeState.FAILED},
    TradeState.MANUAL_REVIEW: {TradeState.CANCELLED, TradeState.FAILED},
    TradeState.COMPLETED: set(),
    TradeState.CANCELLED: set(),
    TradeState.FAILED: set(),
}


def transition(current: TradeState, target: TradeState) -> TradeState:
    if target not in _ALLOWED[current]:
        raise InvalidTransition(f'{current} -> {target} is not allowed')
    return target


def can_transition(current: TradeState, target: TradeState) -> bool:
    return target in _ALLOWED[current]
