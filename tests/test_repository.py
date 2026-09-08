from decimal import Decimal

from p2pbot.db import Repository
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


def test_repository_round_trip(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    repo.create_schema()
    buy = mk("B1", "BUY", "0.708", "M1")
    sell = mk("S1", "SELL", "0.715", "M2")
    repo.save_ads([buy, sell])
    ops = find_opportunities(
        [buy], [sell], min_net_roi_pct=0.1, slippage_bps_per_leg=Decimal("5")
    )
    repo.save_opportunities(ops)
    rows = repo.recent_opportunities()
    assert len(rows) == 1
    assert rows[0]["buy_ad_no"] == "B1"
    assert rows[0]["sell_ad_no"] == "S1"
