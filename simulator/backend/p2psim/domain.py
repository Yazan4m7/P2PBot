from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class SimulationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    RESETTING = "RESETTING"


class AdStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"
    EXHAUSTED = "EXHAUSTED"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAYMENT_INITIATED = "PAYMENT_INITIATED"
    BUYER_MARKED_PAID = "BUYER_MARKED_PAID"
    PAYMENT_EVIDENCE_PENDING = "PAYMENT_EVIDENCE_PENDING"
    PAYMENT_VERIFIED = "PAYMENT_VERIFIED"
    AWAITING_RELEASE = "AWAITING_RELEASE"
    CRYPTO_RELEASED = "CRYPTO_RELEASED"
    COMPLETED = "COMPLETED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    DISPUTE_OPENED = "DISPUTE_OPENED"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED_BUYER = "RESOLVED_BUYER"
    RESOLVED_SELLER = "RESOLVED_SELLER"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"
    FAILED_TECHNICAL = "FAILED_TECHNICAL"


TERMINAL_ORDER_STATUSES = {
    OrderStatus.COMPLETED,
    OrderStatus.CANCELLED,
    OrderStatus.EXPIRED,
    OrderStatus.RESOLVED_BUYER,
    OrderStatus.RESOLVED_SELLER,
    OrderStatus.FAILED_TECHNICAL,
}


class SendCashStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PENDING = "PENDING"
    FAILED = "FAILED"
    UNKNOWN_AFTER_TIMEOUT = "UNKNOWN_AFTER_TIMEOUT"


class VerifyCashStatus(StrEnum):
    VERIFIED = "VERIFIED"
    WAITING = "WAITING"
    MISMATCH = "MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"


class FaultKind(StrEnum):
    TIMEOUT_BEFORE = "TIMEOUT_BEFORE"
    TIMEOUT_AFTER = "TIMEOUT_AFTER"
    HTTP_429 = "HTTP_429"
    HTTP_500 = "HTTP_500"
    MALFORMED = "MALFORMED"
    STALE = "STALE"
    DISCONNECT = "DISCONNECT"


class SimulatorError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class CreateOrderRequest:
    ad_no: str
    payment_method: str
    idempotency_key: str
    fiat_amount: Decimal | None = None
    asset_amount: Decimal | None = None
    expected_price: Decimal | None = None
    bot_trade_id: str | None = None


@dataclass(frozen=True, slots=True)
class PaymentCheck:
    status: VerifyCashStatus
    reasons: tuple[str, ...]
