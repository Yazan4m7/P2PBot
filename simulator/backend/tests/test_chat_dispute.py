from decimal import Decimal

from p2psim.api import engine
from p2psim.domain import CreateOrderRequest


def make_buy():
    ad = engine.public_ads(fiat="JOD", asset="USDT", trade_type="BUY", limit=20, payment_methods=[])["data"][0]
    return engine.create_order(CreateOrderRequest(ad_no=ad["adv"]["adNo"], payment_method=ad["adv"]["tradeMethods"][0]["identifier"], idempotency_key="dsp-create", fiat_amount=Decimal("100"), expected_price=Decimal(ad["adv"]["price"])))


def test_chat_idempotency():
    o = make_buy()
    a = engine.send_chat(o["order_no"], sender="BOT", body="hello", idempotency_key="chat1")
    b = engine.send_chat(o["order_no"], sender="BOT", body="hello", idempotency_key="chat1")
    assert a["id"] == b["id"]
    assert len(engine.chat_history(o["order_no"])) == 1


def test_dispute_freezes_normal_flow_and_resolves():
    o = make_buy()
    d = engine.open_dispute(o["order_no"], reason="test", idempotency_key="d1")
    assert d["status"] == "OPEN"
    resolved = engine.resolve_dispute(o["order_no"], winner="SELLER")
    assert resolved["status"] == "RESOLVED"
    assert engine.get_order(o["order_no"])["status"] == "RESOLVED_SELLER"
    assert engine.reconcile_balances()["ok"]
