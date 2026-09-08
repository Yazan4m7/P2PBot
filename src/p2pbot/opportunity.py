from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from .domain import Ad, Opportunity
from .scoring import score_merchant

D = Decimal


def _asset_bounds(ad: Ad) -> tuple[Decimal, Decimal]:
    lower = D("0") if ad.min_fiat is None else ad.min_fiat / ad.price
    candidates: list[Decimal] = []
    if ad.max_fiat is not None:
        candidates.append(ad.max_fiat / ad.price)
    if ad.available_asset is not None:
        candidates.append(ad.available_asset)
    upper = min(candidates) if candidates else D("Infinity")
    return lower, upper


def find_opportunities(
    buy_ads: list[Ad],
    sell_ads: list[Ad],
    *,
    min_completion_rate: float = 95.0,
    min_merchant_orders: int = 20,
    min_net_roi_pct: float = 0.20,
    max_trade_fiat: Decimal = D("500"),
    slippage_bps_per_leg: Decimal = D("5"),
    platform_fee_bps_per_leg: Decimal = D("0"),
    fixed_bank_fee_buy: Decimal = D("0"),
    fixed_bank_fee_sell: Decimal = D("0"),
    preferred_payment_methods: set[str] | None = None,
) -> list[Opportunity]:
    preferred = {x.upper() for x in (preferred_payment_methods or set())}
    results: list[Opportunity] = []
    slippage = slippage_bps_per_leg / D("10000")
    platform_fee = platform_fee_bps_per_leg / D("10000")

    def eligible(ad: Ad) -> bool:
        m = ad.merchant
        if m.completion_rate_pct is None or m.completion_rate_pct < min_completion_rate:
            return False
        if m.order_count is None or m.order_count < min_merchant_orders:
            return False
        if preferred and not (preferred & {x.upper() for x in ad.payment_methods}):
            return False
        return True

    buys = [ad for ad in buy_ads if eligible(ad)]
    sells = [ad for ad in sell_ads if eligible(ad)]

    for buy in buys:
        buy_low, buy_high = _asset_bounds(buy)
        buy_high = min(buy_high, max_trade_fiat / buy.price)
        buy_score = score_merchant(buy, preferred)

        for sell in sells:
            if buy.merchant.merchant_no == sell.merchant.merchant_no:
                continue
            if sell.price <= buy.price:
                continue

            sell_low, sell_high = _asset_bounds(sell)
            sell_high = min(sell_high, max_trade_fiat / sell.price)
            amount_low = max(buy_low, sell_low)
            amount_high = min(buy_high, sell_high)
            if amount_high.is_infinite() or amount_high <= 0 or amount_high < amount_low:
                continue

            # Use the largest amount allowed by configured paper-trade cap and both ads.
            amount = amount_high.quantize(D("0.000001"), rounding=ROUND_DOWN)
            if amount <= 0:
                continue

            buy_notional = amount * buy.price
            sell_notional = amount * sell.price
            gross_profit = sell_notional - buy_notional

            effective_buy_cost = buy_notional * (D("1") + slippage + platform_fee) + fixed_bank_fee_buy
            effective_sell_revenue = sell_notional * (D("1") - slippage - platform_fee) - fixed_bank_fee_sell
            net_profit = effective_sell_revenue - effective_buy_cost
            if effective_buy_cost <= 0:
                continue
            roi = (net_profit / effective_buy_cost) * D("100")
            if roi < D(str(min_net_roi_pct)):
                continue

            common_methods = tuple(sorted(set(buy.payment_methods) & set(sell.payment_methods)))
            sell_score = score_merchant(sell, preferred)
            results.append(
                Opportunity(
                    buy_ad_no=buy.ad_no,
                    sell_ad_no=sell.ad_no,
                    buy_merchant_no=buy.merchant.merchant_no,
                    sell_merchant_no=sell.merchant.merchant_no,
                    asset=buy.asset,
                    fiat=buy.fiat,
                    asset_amount=amount,
                    buy_price=buy.price,
                    sell_price=sell.price,
                    gross_profit_fiat=gross_profit.quantize(D("0.0001")),
                    net_profit_fiat=net_profit.quantize(D("0.0001")),
                    net_roi_pct=roi.quantize(D("0.0001")),
                    buy_merchant_score=buy_score.score,
                    sell_merchant_score=sell_score.score,
                    common_payment_methods=common_methods,
                )
            )

    results.sort(
        key=lambda x: (x.net_profit_fiat, x.net_roi_pct, min(x.buy_merchant_score, x.sell_merchant_score)),
        reverse=True,
    )
    return results
