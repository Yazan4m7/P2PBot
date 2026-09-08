from __future__ import annotations

from .domain import OrderStatus, SimulatorError


ALLOWED: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.AWAITING_PAYMENT, OrderStatus.CANCELLED, OrderStatus.FAILED_TECHNICAL},
    OrderStatus.AWAITING_PAYMENT: {OrderStatus.PAYMENT_INITIATED, OrderStatus.BUYER_MARKED_PAID, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.DISPUTE_OPENED, OrderStatus.MANUAL_INTERVENTION, OrderStatus.FAILED_TECHNICAL},
    OrderStatus.PAYMENT_INITIATED: {OrderStatus.BUYER_MARKED_PAID, OrderStatus.PAYMENT_EVIDENCE_PENDING, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.DISPUTE_OPENED, OrderStatus.MANUAL_INTERVENTION},
    OrderStatus.BUYER_MARKED_PAID: {OrderStatus.PAYMENT_EVIDENCE_PENDING, OrderStatus.PAYMENT_VERIFIED, OrderStatus.AWAITING_RELEASE, OrderStatus.DISPUTE_OPENED, OrderStatus.MANUAL_INTERVENTION, OrderStatus.FAILED_TECHNICAL},
    OrderStatus.PAYMENT_EVIDENCE_PENDING: {OrderStatus.PAYMENT_VERIFIED, OrderStatus.DISPUTE_OPENED, OrderStatus.MANUAL_INTERVENTION, OrderStatus.FAILED_TECHNICAL},
    OrderStatus.PAYMENT_VERIFIED: {OrderStatus.AWAITING_RELEASE, OrderStatus.DISPUTE_OPENED, OrderStatus.MANUAL_INTERVENTION},
    OrderStatus.AWAITING_RELEASE: {OrderStatus.CRYPTO_RELEASED, OrderStatus.DISPUTE_OPENED, OrderStatus.MANUAL_INTERVENTION, OrderStatus.FAILED_TECHNICAL},
    OrderStatus.CRYPTO_RELEASED: {OrderStatus.COMPLETED, OrderStatus.FAILED_TECHNICAL},
    OrderStatus.CANCEL_REQUESTED: {OrderStatus.CANCELLED, OrderStatus.DISPUTE_OPENED, OrderStatus.MANUAL_INTERVENTION},
    OrderStatus.DISPUTE_OPENED: {OrderStatus.UNDER_REVIEW, OrderStatus.MANUAL_INTERVENTION},
    OrderStatus.UNDER_REVIEW: {OrderStatus.RESOLVED_BUYER, OrderStatus.RESOLVED_SELLER, OrderStatus.MANUAL_INTERVENTION},
    OrderStatus.MANUAL_INTERVENTION: {OrderStatus.UNDER_REVIEW, OrderStatus.RESOLVED_BUYER, OrderStatus.RESOLVED_SELLER},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.EXPIRED: set(),
    OrderStatus.RESOLVED_BUYER: set(),
    OrderStatus.RESOLVED_SELLER: set(),
    OrderStatus.FAILED_TECHNICAL: set(),
}


def assert_transition(current: str, target: OrderStatus) -> None:
    source = OrderStatus(current)
    if target not in ALLOWED[source]:
        raise SimulatorError("INVALID_ORDER_TRANSITION", f"{source.value} -> {target.value} is not allowed", status_code=409)
