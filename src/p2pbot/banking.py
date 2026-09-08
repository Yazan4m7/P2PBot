from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher

from .domain import PaymentExpectation, PaymentRecord


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
    transactions: list[PaymentRecord]

    def recent_transactions(self) -> list[PaymentRecord]:
        return list(self.transactions)


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
