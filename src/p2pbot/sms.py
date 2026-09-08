from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
import random
import uuid

from .domain import PaymentExpectation, utcnow


@dataclass(frozen=True, slots=True)
class SmsRecord:
    message_id: str
    sender_id: str
    amount: Decimal
    currency: str
    direction: str
    counterparty_name: str | None
    received_at: datetime
    body: str


class SmsAdapter:
    """Read-only boundary for payment-notification messages."""

    def recent_messages(self) -> list[SmsRecord]:
        raise NotImplementedError


@dataclass(slots=True)
class MemorySmsAdapter(SmsAdapter):
    messages: list[SmsRecord] = field(default_factory=list)

    def recent_messages(self) -> list[SmsRecord]:
        return list(self.messages)


class MockSmsAdapter(MemorySmsAdapter):
    """Synthetic SMS source used until the Android adapter is available."""

    def __init__(self, *, seed: int | None = None):
        super().__init__([])
        self._rng = random.Random(seed)

    def simulate_for(self, expectation: PaymentExpectation, scenario: str = 'success') -> list[SmsRecord]:
        if scenario == 'sms_missing':
            return []

        amount = expectation.amount
        name = expectation.counterparty_name
        received_at = utcnow()
        if scenario == 'wrong_amount':
            amount += Decimal('1.00')
        elif scenario == 'wrong_name':
            name = 'Different Sender'
        elif scenario == 'delayed':
            received_at = expectation.not_after + timedelta(minutes=5)

        message = SmsRecord(
            message_id=uuid.uuid4().hex,
            sender_id='MOCK_BANK_SMS',
            amount=amount,
            currency=expectation.currency.upper(),
            direction=expectation.direction.upper(),
            counterparty_name=name,
            received_at=received_at,
            body=f'{expectation.direction.upper()} {amount} {expectation.currency.upper()} {name or ""}'.strip(),
        )
        self.messages.append(message)

        if scenario == 'duplicate':
            duplicate = SmsRecord(
                message_id=uuid.uuid4().hex,
                sender_id=message.sender_id,
                amount=message.amount,
                currency=message.currency,
                direction=message.direction,
                counterparty_name=message.counterparty_name,
                received_at=message.received_at,
                body=message.body,
            )
            self.messages.append(duplicate)
            return [message, duplicate]

        return [message]

    def random_scenario(self) -> str:
        return self._rng.choices(
            ['success', 'sms_missing', 'wrong_amount', 'wrong_name', 'delayed', 'duplicate'],
            weights=[78, 5, 5, 4, 3, 5],
            k=1,
        )[0]
