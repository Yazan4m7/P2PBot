import json
import httpx

from p2pbot.binance_public import BinancePublicClient


def test_client_uses_public_ad_list_and_parses():
    def handler(request: httpx.Request):
        assert request.url.path.endswith("/agent/ad-list")
        payload = {"data": [{
            "adNo": "A9",
            "price": "0.709",
            "surplusAmount": "250",
            "minSingleTransAmount": "10",
            "maxSingleTransAmount": "100",
            "tradeMethods": [{"identifier": "BANK"}],
            "merchant": {"merchantNo": "M9", "merchantNick": "Nine", "monthFinishRate": 99.2, "monthOrderCount": 220},
        }]}
        return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})

    client = BinancePublicClient("https://www.binance.com", transport=httpx.MockTransport(handler))
    try:
        ads = client.get_ads(fiat="JOD", asset="USDT", trade_type="BUY", limit=5)
        assert len(ads) == 1
        assert ads[0].ad_no == "A9"
    finally:
        client.close()
