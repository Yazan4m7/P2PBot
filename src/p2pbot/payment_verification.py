from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .banking import BankAdapter, match_payment
from .domain import PaymentExpectation, PaymentRecord
from .sms import SmsAdapter, SmsRecord


class VerificationStatus(StrEnum):
    VERIFIED = 'VERIFIED'
    WAITING = 'WAITING'
    MANUAL_REVIEW = 'MANUAL_REVIEW'


@dataclass(frozen=True, slots=True)
class PaymentVerificationResult:
    status: VerificationStatus
    bank_transaction: PaymentRecord | None
    sms_message: SmsRecord | None
    reasons: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return self.status == VerificationStatus.VERIFIED


def _sms_matches(expectation: PaymentExpectation, message: SmsRecord) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if message.currency.upper() != expectation.currency.upper():
        reasons.append('sms_currency_mismatch')
    if message.direction.upper() != expectation.direction.upper():
        reasons.append('sms_direction_mismatch')
    if message.amount != expectation.amount:
        reasons.append('sms_amount_mismatch')
    if not (expectation.not_before <= message.received_at <= expectation.not_after):
        reasons.append('sms_outside_time_window')
    if expectation.counterparty_name and message.counterparty_name:
        left = expectation.counterparty_name.casefold().strip()
        right = message.counterparty_name.casefold().strip()
        if left != right:
            reasons.append('sms_counterparty_name_mismatch')
    return (not reasons, tuple(reasons))


def verify_payment(
    expectation: PaymentExpectation,
    *,
    bank: BankAdapter,
    sms: SmsAdapter,
    require_sms: bool = True,
) -> PaymentVerificationResult:
    bank_matches: list[PaymentRecord] = []
    bank_reasons: list[str] = []
    for transaction in bank.recent_transactions():
        ok, _, reasons = match_payment(expectation, transaction)
        if ok:
            bank_matches.append(transaction)
        else:
            bank_reasons.extend(reasons)

    sms_matches: list[SmsRecord] = []
    sms_reasons: list[str] = []
    for message in sms.recent_messages():
        ok, reasons = _sms_matches(expectation, message)
        if ok:
            sms_matches.append(message)
        else:
            sms_reasons.extend(reasons)

    if len(bank_matches) > 1 or len(sms_matches) > 1:
        return PaymentVerificationResult(
            VerificationStatus.MANUAL_REVIEW,
            bank_matches[0] if bank_matches else None,
            sms_matches[0] if sms_matches else None,
            ('duplicate_matching_records',),
        )

    if len(bank_matches) == 1 and (len(sms_matches) == 1 or not require_sms):
        return PaymentVerificationResult(
            VerificationStatus.VERIFIED,
            bank_matches[0],
            sms_matches[0] if sms_matches else None,
            (),
        )

    reasons: list[str] = []
    if not bank_matches:
        reasons.append('bank_transaction_not_confirmed')
    if require_sms and not sms_matches:
        reasons.append('sms_not_confirmed')
    reasons.extend(dict.fromkeys(bank_reasons + sms_reasons))
    return PaymentVerificationResult(
        VerificationStatus.WAITING,
        None,
        None,
        tuple(dict.fromkeys(reasons)),
    )
