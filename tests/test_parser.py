from decimal import Decimal

from p2pbot.binance_public import parse_ads


def test_parse_legacy_nested_ad_shape():
    payload = {
        "code": "000000",
        "success": True,
        "data": [
            {
                "adv": {
                    "advNo": "A1",
                    "price": "0.708",
                    "surplusAmount": "1000",
                    "minSingleTransAmount": "50",
                    "maxSingleTransAmount": "500",
                    "tradeMethods": [{"tradeMethodIdentifier": "BANK"}],
                },
                "advertiser": {
                    "userNo": "M1",
                    "nickName": "Alpha",
                    "monthFinishRate": 0.991,
                    "monthOrderCount": 412,
                    "advConfirmTime": 85,
                    "userType": "merchant",
                },
            }
        ],
    }
    ads = parse_ads(payload, trade_type="BUY", asset="USDT", fiat="JOD")
    assert len(ads) == 1
    ad = ads[0]
    assert ad.ad_no == "A1"
    assert ad.price == Decimal("0.708")
    assert ad.payment_methods == ("BANK",)
    assert ad.merchant.completion_rate_pct == 99.1
    assert ad.merchant.order_count == 412
