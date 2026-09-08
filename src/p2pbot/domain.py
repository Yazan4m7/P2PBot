from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
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
