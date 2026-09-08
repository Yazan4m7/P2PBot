import httpx

from p2pbot.binance_auth import BinanceAuthClient


def test_signed_read_request_and_capability_probe():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        assert request.headers['X-MBX-APIKEY'] == 'key'
        assert 'timestamp=' in str(request.url)
        assert 'signature=' in str(request.url)
        if request.url.path.endswith('listUserOrderHistory'):
            return httpx.Response(200, json={'data': []})
        if request.url.path.endswith('getUserOrderSummary'):
            return httpx.Response(200, json={'data': {}})
        if request.url.path.endswith('getAvailableAdsCategory'):
            return httpx.Response(403, json={'code': -1002, 'msg': 'Permission denied'})
        raise AssertionError(request.url.path)

    client = BinanceAuthClient('https://api.binance.com', 'key', 'secret', transport=httpx.MockTransport(handler))
    report = client.capability_probe()
    client.close()
    assert report['personal_order_history'] is True
    assert report['order_summary'] is True
    assert report['ad_management_eligibility'] is False
    assert len(seen) == 3
