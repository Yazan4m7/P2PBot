from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
import random

from .banking import MockBankAdapter
from .domain import PaymentExpectation, utcnow
from .payment_verification import PaymentVerificationResult, verify_payment
from .sms import MockSmsAdapter


SCENARIOS = (
    'success',
    'sms_missing',
    'bank_missing',
    'wrong_amount',
    'wrong_name',
    'pending',
    'delayed',
    'duplicate',
)


@dataclass(slots=True)
class MockPaymentEnvironment:
    bank: MockBankAdapter
    sms: MockSmsAdapter
    _rng: random.Random

    @classmethod
    def create(cls, *, seed: int | None = None) -> 'MockPaymentEnvironment':
        return cls(
            bank=MockBankAdapter(seed=seed),
            sms=MockSmsAdapter(seed=seed),
            _rng=random.Random(seed),
        )

    def random_scenario(self) -> str:
        return self._rng.choices(
            SCENARIOS,
            weights=[72, 5, 5, 4, 3, 4, 3, 4],
            k=1,
        )[0]

    def clear(self) -> None:
        self.bank.transactions.clear()
        self.sms.messages.clear()

    def simulate(self, expectation: PaymentExpectation, *, scenario: str | None = None) -> str:
        self.clear()
        scenario = scenario or self.random_scenario()
        if scenario not in SCENARIOS:
            raise ValueError(f'unknown mock payment scenario: {scenario}')

        if scenario != 'sms_missing':
            self.sms.simulate_for(expectation, scenario=scenario)
        if scenario != 'bank_missing':
            self.bank.simulate_for(expectation, scenario=scenario)
        return scenario

    def check(self, expectation: PaymentExpectation, *, require_sms: bool = True) -> PaymentVerificationResult:
        return verify_payment(expectation, bank=self.bank, sms=self.sms, require_sms=require_sms)


def make_expectation(
    *,
    amount: Decimal,
    currency: str = 'JOD',
    direction: str = 'IN',
    counterparty_name: str | None = None,
    window_minutes: int = 15,
) -> PaymentExpectation:
    now = utcnow()
    return PaymentExpectation(
        amount=amount,
        currency=currency.upper(),
        direction=direction.upper(),
        counterparty_name=counterparty_name,
        not_before=now - timedelta(minutes=1),
        not_after=now + timedelta(minutes=window_minutes),
    )
