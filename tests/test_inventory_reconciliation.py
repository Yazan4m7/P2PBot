from decimal import Decimal

from p2pbot.domain import InventorySnapshot
from p2pbot.inventory import inventory_decision
from p2pbot.reconciliation import reconcile


def test_inventory_biases_toward_asset_when_low():
    snap = InventorySnapshot(Decimal('900'), Decimal('100'), Decimal('0.7'))
    assert inventory_decision(snap).bias == 'BUY_ASSET'


def test_reconciliation_detects_difference():
    result = reconcile(starting_fiat=Decimal('1000'), fiat_in=Decimal('100'), fiat_out=Decimal('200'), actual_fiat=Decimal('899'), starting_asset=Decimal('100'), asset_in=Decimal('20'), asset_out=Decimal('10'), actual_asset=Decimal('110'))
    assert not result.ok
    assert result.fiat_difference == Decimal('-1')
