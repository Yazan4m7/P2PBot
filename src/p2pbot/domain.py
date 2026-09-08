from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Merchant:
    merchant_no: str
    nickname: str
    completion_rate_pct: float | None = None
    order_count: int | None = None
    avg_release_seconds: float | None = None
    merchant_type: str | None = None


@dataclass(frozen=True, slots=True)
class Ad:
    ad_no: str
    trade_type: str
    asset: str
    fiat: str
    price: Decimal
    available_asset: Decimal | None
    min_fiat: Decimal | None
    max_fiat: Decimal | None
    payment_methods: tuple[str, ...]
    merchant: Merchant
    observed_at: datetime = field(default_factory=utcnow)
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class MerchantScore:
    merchant_no: str
    score: float
    completion_component: float
    orders_component: float
    release_component: float
    payment_component: float
    merchant_type_component: float


@dataclass(frozen=True, slots=True)
class Opportunity:
    buy_ad_no: str
    sell_ad_no: str
    buy_merchant_no: str
    sell_merchant_no: str
    asset: str
    fiat: str
    asset_amount: Decimal
    buy_price: Decimal
    sell_price: Decimal
    gross_profit_fiat: Decimal
    net_profit_fiat: Decimal
    net_roi_pct: Decimal
    buy_merchant_score: float
    sell_merchant_score: float
    common_payment_methods: tuple[str, ...]
    observed_at: datetime = field(default_factory=utcnow)


class TradeState(StrEnum):
    CREATED = 'CREATED'
    RISK_APPROVED = 'RISK_APPROVED'
    BUY_ORDER_PROPOSED = 'BUY_ORDER_PROPOSED'
    BUY_ORDER_OPEN = 'BUY_ORDER_OPEN'
    BUY_PAYMENT_PROPOSED = 'BUY_PAYMENT_PROPOSED'
    BUY_MARKED_PAID = 'BUY_MARKED_PAID'
    ASSET_RECEIVED = 'ASSET_RECEIVED'
    SELL_ORDER_PROPOSED = 'SELL_ORDER_PROPOSED'
    SELL_ORDER_OPEN = 'SELL_ORDER_OPEN'
    SELL_PAYMENT_DETECTED = 'SELL_PAYMENT_DETECTED'
    SELL_PAYMENT_VERIFIED = 'SELL_PAYMENT_VERIFIED'
    RELEASE_PROPOSED = 'RELEASE_PROPOSED'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'
    MANUAL_REVIEW = 'MANUAL_REVIEW'
    FAILED = 'FAILED'


@dataclass(frozen=True, slots=True)
class PaperTrade:
    trade_id: str
    opportunity: Opportunity
    state: TradeState
    buy_cost_fiat: Decimal
    sell_revenue_fiat: Decimal
    realized_profit_fiat: Decimal
    created_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PaymentRecord:
    transaction_id: str
    amount: Decimal
    currency: str
    direction: str
    counterparty_name: str | None
    booked_at: datetime
    status: str = 'BOOKED'


@dataclass(frozen=True, slots=True)
class PaymentExpectation:
    amount: Decimal
    currency: str
    direction: str
    counterparty_name: str | None
    not_before: datetime
    not_after: datetime


@dataclass(frozen=True, slots=True)
class InventorySnapshot:
    fiat_balance: Decimal
    asset_balance: Decimal
    asset_price_fiat: Decimal
    observed_at: datetime = field(default_factory=utcnow)
