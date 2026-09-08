import hashlib
import hmac
import time
from urllib.parse import urlencode


def signed(path, secret="SIMULATOR_TEST_SECRET", **params):
    ordered = [(k, str(v)) for k, v in params.items()]
    ordered += [("recvWindow", "5000"), ("timestamp", str(int(time.time() * 1000)))]
    sig = hmac.new(secret.encode(), urlencode(ordered).encode(), hashlib.sha256).hexdigest()
    return path + "?" + urlencode(ordered + [("signature", sig)])


def test_signed_order_history(client):
    url = signed("/sapi/v1/c2c/orderMatch/listUserOrderHistory", page=1, rows=20)
    r = client.get(url, headers={"X-MBX-APIKEY": "SIMULATOR_TEST_KEY"})
    assert r.status_code == 200
    assert "data" in r.json()


def test_bad_signature_rejected(client):
    url = signed("/sapi/v1/c2c/orderMatch/getUserOrderSummary", secret="wrong")
    r = client.get(url, headers={"X-MBX-APIKEY": "SIMULATOR_TEST_KEY"})
    assert r.status_code == 401
