from __future__ import annotations

import math

from .domain import Ad, MerchantScore


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def score_merchant(ad: Ad, preferred_payment_methods: set[str] | None = None) -> MerchantScore:
    merchant = ad.merchant

    completion = 0.50 if merchant.completion_rate_pct is None else _clamp(merchant.completion_rate_pct / 100)

    if merchant.order_count is None:
        orders = 0.40
    else:
        # ~100 orders is respectable; 1000+ saturates the score.
        orders = _clamp(math.log1p(max(0, merchant.order_count)) / math.log1p(1000))

    if merchant.avg_release_seconds is None:
        release = 0.50
    elif merchant.avg_release_seconds <= 120:
        release = 1.0
    elif merchant.avg_release_seconds >= 1800:
        release = 0.0
    else:
        release = 1 - ((merchant.avg_release_seconds - 120) / (1800 - 120))

    preferred = {x.upper() for x in (preferred_payment_methods or set())}
    ad_methods = {x.upper() for x in ad.payment_methods}
    payment = 1.0 if not preferred else (1.0 if preferred & ad_methods else 0.0)

    kind = (merchant.merchant_type or "").lower()
    merchant_type = 1.0 if any(token in kind for token in ("merchant", "pro", "verified")) else 0.50

    score = (
        completion * 50
        + orders * 20
        + release * 15
        + payment * 10
        + merchant_type * 5
    )

    return MerchantScore(
        merchant_no=merchant.merchant_no,
        score=round(score, 2),
        completion_component=round(completion * 50, 2),
        orders_component=round(orders * 20, 2),
        release_component=round(release * 15, 2),
        payment_component=round(payment * 10, 2),
        merchant_type_component=round(merchant_type * 5, 2),
    )
