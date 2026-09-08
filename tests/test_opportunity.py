from decimal import Decimal

from p2pbot.domain import Ad, Merchant
from p2pbot.opportunity import find_opportunities


def mk(ad_no, tt, price, merchant_no):
    return Ad(
        ad_no=ad_no,
        trade_type=tt,
        asset="USDT",
        fiat="JOD",
        price=Decimal(price),
        available_asset=Decimal("1000"),
        min_fiat=Decimal("20"),
        max_fiat=Decimal("500"),
        payment_methods=("BANK",),
        merchant=Merchant(merchant_no, merchant_no, 99.5, 500, 90, "merchant"),
    )


def test_profitable_pair_is_found_and_costs_applied():
    buy = mk("BUY1", "BUY", "0.708", "M1")
    sell = mk("SELL1", "SELL", "0.715", "M2")
    ops = find_opportunities(
        [buy], [sell], min_net_roi_pct=0.1, max_trade_fiat=Decimal("500"),
        slippage_bps_per_leg=Decimal("5"), preferred_payment_methods={"BANK"}
    )
    assert len(ops) == 1
    assert ops[0].net_profit_fiat > 0
    assert ops[0].sell_price > ops[0].buy_price


def test_low_completion_is_rejected():
    buy = mk("BUY1", "BUY", "0.708", "M1")
    bad = Merchant("M2", "bad", 80.0, 1000, 60, "merchant")
    sell = Ad(
        ad_no="SELL1", trade_type="SELL", asset="USDT", fiat="JOD", price=Decimal("0.720"),
        available_asset=Decimal("1000"), min_fiat=Decimal("20"), max_fiat=Decimal("500"),
        payment_methods=("BANK",), merchant=bad,
    )
    assert find_opportunities([buy], [sell]) == []
