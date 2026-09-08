def first_ad(client, side="BUY"):
    return client.get(f"/bapi/c2c/v1/public/c2c/agent/ad-list?fiat=JOD&asset=USDT&tradeType={side}&limit=20").json()["data"][0]


def test_order_create_timeout_after_commit_recovers_by_idempotency(client):
    ad = first_ad(client)
    client.post("/sim/admin/faults/order_create", json={"kind": "TIMEOUT_AFTER", "remaining": 1, "payload": {}})
    body = {"ad_no": ad["adv"]["adNo"], "payment_method": ad["adv"]["tradeMethods"][0]["identifier"], "fiat_amount": "100", "expected_price": ad["adv"]["price"]}
    r1 = client.post("/sim/api/v1/orders", headers={"Idempotency-Key": "same-create"}, json=body)
    assert r1.status_code == 504
    r2 = client.post("/sim/api/v1/orders", headers={"Idempotency-Key": "same-create"}, json=body)
    assert r2.status_code == 200
    orders = client.get("/sim/api/v1/orders").json()["items"]
    assert len(orders) == 1
    assert orders[0]["order_no"] == r2.json()["order_no"]


def test_mark_paid_timeout_after_commit_is_safe(client):
    ad = first_ad(client)
    body = {"ad_no": ad["adv"]["adNo"], "payment_method": ad["adv"]["tradeMethods"][0]["identifier"], "fiat_amount": "100", "expected_price": ad["adv"]["price"]}
    o = client.post("/sim/api/v1/orders", headers={"Idempotency-Key": "create"}, json=body).json()
    client.post(f"/sim/api/v1/orders/{o['order_no']}/send-cash", headers={"Idempotency-Key": "cash"}, json={"scenario": "SUCCESS"})
    client.post("/sim/admin/faults/mark_paid", json={"kind": "TIMEOUT_AFTER", "remaining": 1, "payload": {}})
    r1 = client.post(f"/sim/api/v1/orders/{o['order_no']}/mark-paid", headers={"Idempotency-Key": "paid"})
    assert r1.status_code == 504
    r2 = client.post(f"/sim/api/v1/orders/{o['order_no']}/mark-paid", headers={"Idempotency-Key": "paid"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "BUYER_MARKED_PAID"
