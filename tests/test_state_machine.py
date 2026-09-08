import pytest

from p2pbot.domain import TradeState
from p2pbot.state_machine import InvalidTransition, can_transition, transition


def test_state_machine_allows_forward_flow_and_blocks_invalid_jump():
    assert can_transition(TradeState.CREATED, TradeState.RISK_APPROVED)
    assert transition(TradeState.CREATED, TradeState.RISK_APPROVED) == TradeState.RISK_APPROVED
    with pytest.raises(InvalidTransition):
        transition(TradeState.CREATED, TradeState.COMPLETED)
