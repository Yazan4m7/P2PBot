from decimal import Decimal

from p2psim.api import engine
from p2psim.domain import CreateOrderRequest


def buy_ad():
    return engine.public_ads(fiat="JOD", asset="USDT", trade_type="BUY", limit=20, payment_methods=[])["data"][0]


def test_buy_order_full_lifecycle_and_accounting():
    ad = buy_ad()
    price = Decimal(ad["adv"]["price"])
    bot_before = {x["currency"]: x for x in engine.balances("BOT")}
    order = engine.create_order(CreateOrderRequest(ad_no=ad["adv"]["adNo"], payment_method=ad["adv"]["tradeMethods"][0]["identifier"], idempotency_key="buy-1", fiat_amount=Decimal("100"), expected_price=price))
    assert order["status"] == "AWAITING_PAYMENT"
    order2 = engine.create_order(CreateOrderRequest(ad_no=ad["adv"]["adNo"], payment_method=ad["adv"]["tradeMethods"][0]["identifier"], idempotency_key="buy-1", fiat_amount=Decimal("100"), expected_price=price))
    assert order2["order_no"] == order["order_no"]
    engine.send_cash(order["order_no"], idempotency_key="cash-1", scenario="SUCCESS")
    engine.mark_paid(order["order_no"], idempotency_key="paid-1")
    engine.release(order["order_no"], idempotency_key="release-1", actor="COUNTERPARTY")
    final = engine.get_order(order["order_no"])
    assert final["status"] == "COMPLETED"
    bot_after = {x["currency"]: x for x in engine.balances("BOT")}
    assert Decimal(bot_after["JOD"]["owned"]) < Decimal(bot_before["JOD"]["owned"])
    assert Decimal(bot_after["USDT"]["owned"]) > Decimal(bot_before["USDT"]["owned"])
    assert engine.reconcile_balances()["ok"] is True


def test_price_change_rejected():
    ad = buy_ad()
    old = Decimal(ad["adv"]["price"])
    engine.reprice_ad(ad["adv"]["adNo"], old + Decimal("0.001"))
    try:
        engine.create_order(CreateOrderRequest(ad_no=ad["adv"]["adNo"], payment_method=ad["adv"]["tradeMethods"][0]["identifier"], idempotency_key="stale", fiat_amount=Decimal("100"), expected_price=old))
    except Exception as exc:
        assert getattr(exc, "code", None) == "PRICE_CHANGED"
    else:
        raise AssertionError("expected price change rejection")


def test_cancel_returns_reservations_exactly_once():
    ad = buy_ad()
    price = Decimal(ad["adv"]["price"])
    o = engine.create_order(CreateOrderRequest(ad_no=ad["adv"]["adNo"], payment_method=ad["adv"]["tradeMethods"][0]["identifier"], idempotency_key="cancel-create", fiat_amount=Decimal("100"), expected_price=price))
    assert engine.reconcile_balances()["ok"]
    engine.cancel(o["order_no"], idempotency_key="cancel-1")
    engine.cancel(o["order_no"], idempotency_key="cancel-1")
    assert engine.get_order(o["order_no"])["status"] == "CANCELLED"
    assert engine.reconcile_balances()["ok"]


def test_expiry_after_virtual_time():
    ad = buy_ad()
    price = Decimal(ad["adv"]["price"])
    o = engine.create_order(CreateOrderRequest(ad_no=ad["adv"]["adNo"], payment_method=ad["adv"]["tradeMethods"][0]["identifier"], idempotency_key="expire", fiat_amount=Decimal("100"), expected_price=price))
    engine.pause()
    engine.advance(16 * 60)
    assert engine.get_order(o["order_no"])["status"] == "EXPIRED"
    assert engine.reconcile_balances()["ok"]
