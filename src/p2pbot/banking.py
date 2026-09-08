from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from difflib import SequenceMatcher
import random
import uuid

from .domain import PaymentExpectation, PaymentRecord, utcnow


class MoneyActionDisabled(RuntimeError):
    pass


class BankAdapter:
    """Read/verification boundary. Production money movement is intentionally not implemented."""

    def recent_transactions(self) -> list[PaymentRecord]:
        raise NotImplementedError

    def propose_transfer(self, *, amount: Decimal, currency: str, recipient: str) -> dict:
        return {
            'action': 'BANK_TRANSFER',
            'amount': str(amount),
            'currency': currency.upper(),
            'recipient': recipient,
            'status': 'APPROVAL_REQUIRED',
        }

    def execute_transfer(self, **_: object) -> None:
        raise MoneyActionDisabled('Unattended fiat transfer is disabled; use an approved official adapter with explicit approval.')


@dataclass(slots=True)
class MemoryBankAdapter(BankAdapter):
    transactions: list[PaymentRecord] = field(default_factory=list)

    def recent_transactions(self) -> list[PaymentRecord]:
        return list(self.transactions)


class MockBankAdapter(MemoryBankAdapter):
    """Synthetic transaction source used until a real read-only bank adapter exists."""

    def __init__(self, *, seed: int | None = None):
        super().__init__([])
        self._rng = random.Random(seed)

    def simulate_for(self, expectation: PaymentExpectation, scenario: str = 'success') -> list[PaymentRecord]:
        if scenario == 'bank_missing':
            return []

        amount = expectation.amount
        name = expectation.counterparty_name
        booked_at = utcnow()
        status = 'BOOKED'
        if scenario == 'wrong_amount':
            amount += Decimal('1.00')
        elif scenario == 'wrong_name':
            name = 'Different Sender'
        elif scenario == 'pending':
            status = 'PENDING'
        elif scenario == 'delayed':
            booked_at = expectation.not_after + timedelta(minutes=5)

        transaction = PaymentRecord(
            transaction_id=uuid.uuid4().hex,
            amount=amount,
            currency=expectation.currency.upper(),
            direction=expectation.direction.upper(),
            counterparty_name=name,
            booked_at=booked_at,
            status=status,
        )
        self.transactions.append(transaction)

        if scenario == 'duplicate':
            duplicate = PaymentRecord(
                transaction_id=uuid.uuid4().hex,
                amount=transaction.amount,
                currency=transaction.currency,
                direction=transaction.direction,
                counterparty_name=transaction.counterparty_name,
                booked_at=transaction.booked_at,
                status=transaction.status,
            )
            self.transactions.append(duplicate)
            return [transaction, duplicate]

        return [transaction]

    def random_scenario(self) -> str:
        return self._rng.choices(
            ['success', 'bank_missing', 'wrong_amount', 'wrong_name', 'pending', 'delayed', 'duplicate'],
            weights=[76, 5, 5, 3, 4, 3, 4],
            k=1,
        )[0]


def _name_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.5
    return SequenceMatcher(None, a.casefold().strip(), b.casefold().strip()).ratio()


def match_payment(expectation: PaymentExpectation, record: PaymentRecord) -> tuple[bool, float, tuple[str, ...]]:
    reasons: list[str] = []
    score = 0.0
    if record.status.upper() not in {'BOOKED', 'COMPLETED', 'SUCCESS', 'CREDITED'}:
        reasons.append('transaction_not_final')
    else:
        score += 0.2
    if record.currency.upper() != expectation.currency.upper():
        reasons.append('currency_mismatch')
    else:
        score += 0.2
    if record.direction.upper() != expectation.direction.upper():
        reasons.append('direction_mismatch')
    else:
        score += 0.1
    if record.amount != expectation.amount:
        reasons.append('amount_mismatch')
    else:
        score += 0.35
    if not (expectation.not_before <= record.booked_at <= expectation.not_after):
        reasons.append('outside_time_window')
    else:
        score += 0.1
    name_score = _name_similarity(expectation.counterparty_name, record.counterparty_name)
    score += 0.05 * name_score
    if expectation.counterparty_name and name_score < 0.65:
        reasons.append('counterparty_name_mismatch')
    return (not reasons, round(score, 4), tuple(reasons))
