from datetime import datetime, timedelta, timezone
from decimal import Decimal

from p2pbot.banking import match_payment
from p2pbot.domain import PaymentExpectation, PaymentRecord


def test_payment_match_requires_exact_money_and_window():
    now = datetime.now(timezone.utc)
    exp = PaymentExpectation(Decimal('70.00'), 'JOD', 'IN', 'Ahmad Ali', now - timedelta(minutes=1), now + timedelta(minutes=10))
    tx = PaymentRecord('t1', Decimal('70.00'), 'JOD', 'IN', 'Ahmad Ali', now, 'BOOKED')
    ok, score, reasons = match_payment(exp, tx)
    assert ok
    assert score > 0.95
    assert reasons == ()


def test_payment_match_rejects_wrong_amount():
    now = datetime.now(timezone.utc)
    exp = PaymentExpectation(Decimal('70.00'), 'JOD', 'IN', None, now - timedelta(minutes=1), now + timedelta(minutes=1))
    tx = PaymentRecord('t1', Decimal('69.00'), 'JOD', 'IN', None, now, 'BOOKED')
    ok, _, reasons = match_payment(exp, tx)
    assert not ok
    assert 'amount_mismatch' in reasons
