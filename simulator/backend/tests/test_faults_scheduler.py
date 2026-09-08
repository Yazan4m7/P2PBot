from decimal import Decimal

from p2psim.api import engine
from p2psim.domain import CreateOrderRequest, FaultKind


def test_fault_consumed_deterministically():
    engine.set_fault("x", FaultKind.HTTP_500, remaining=2)
    assert engine.consume_fault("x")["kind"] == "HTTP_500"
    assert engine.consume_fault("x")["kind"] == "HTTP_500"
    assert engine.consume_fault("x") is None


def test_scheduler_exactly_once_on_completed_event():
    ad = engine.public_ads(fiat="JOD", asset="USDT", trade_type="BUY", limit=20, payment_methods=[])["data"][0]
    o = engine.create_order(CreateOrderRequest(ad_no=ad["adv"]["adNo"], payment_method=ad["adv"]["tradeMethods"][0]["identifier"], idempotency_key="sched", fiat_amount=Decimal("100"), expected_price=Decimal(ad["adv"]["price"])))
    engine.pause()
    engine.clock.advance(16 * 60)
    first = engine.run_due_events()
    second = engine.run_due_events()
    assert first >= 1
    assert second == 0
    assert engine.get_order(o["order_no"])["status"] == "EXPIRED"
