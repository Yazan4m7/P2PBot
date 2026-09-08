from decimal import Decimal

from p2pbot.domain import Ad, Merchant
from p2pbot.scoring import score_merchant


def test_high_quality_merchant_scores_high():
    ad = Ad(
        ad_no="A1", trade_type="BUY", asset="USDT", fiat="JOD", price=Decimal("0.708"),
        available_asset=Decimal("1000"), min_fiat=Decimal("20"), max_fiat=Decimal("500"),
        payment_methods=("BANK",),
        merchant=Merchant("M1", "Alpha", 99.8, 900, 60, "merchant"),
    )
    score = score_merchant(ad, {"BANK"})
    assert score.score >= 95
