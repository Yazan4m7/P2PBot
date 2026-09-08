from decimal import Decimal

import pytest

from p2pbot.payment_verification import VerificationStatus
from p2pbot.simulation import MockPaymentEnvironment, SCENARIOS, make_expectation


@pytest.fixture
def expectation():
    return make_expectation(amount=Decimal('127.50'), counterparty_name='Ahmad Ali')


def test_success_requires_matching_bank_and_sms(expectation):
    env = MockPaymentEnvironment.create(seed=1)
    env.simulate(expectation, scenario='success')
    result = env.check(expectation)
    assert result.status == VerificationStatus.VERIFIED
    assert result.bank_transaction is not None
    assert result.sms_message is not None


@pytest.mark.parametrize('scenario', ['sms_missing', 'bank_missing', 'wrong_amount', 'wrong_name', 'pending', 'delayed'])
def test_bad_or_incomplete_scenarios_do_not_verify(expectation, scenario):
    env = MockPaymentEnvironment.create(seed=2)
    env.simulate(expectation, scenario=scenario)
    assert not env.check(expectation).verified


def test_duplicate_matching_records_force_manual_review(expectation):
    env = MockPaymentEnvironment.create(seed=3)
    env.simulate(expectation, scenario='duplicate')
    result = env.check(expectation)
    assert result.status == VerificationStatus.MANUAL_REVIEW
    assert 'duplicate_matching_records' in result.reasons


def test_random_simulation_only_emits_known_scenarios(expectation):
    env = MockPaymentEnvironment.create(seed=42)
    seen = {env.simulate(expectation) for _ in range(50)}
    assert seen
    assert seen <= set(SCENARIOS)
