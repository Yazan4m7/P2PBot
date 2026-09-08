from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .domain import InventorySnapshot


@dataclass(frozen=True, slots=True)
class InventoryDecision:
    asset_pct: Decimal
    bias: str
    reason: str


def inventory_decision(
    snapshot: InventorySnapshot,
    *,
    low_asset_pct: Decimal = Decimal('20'),
    high_asset_pct: Decimal = Decimal('80'),
) -> InventoryDecision:
    asset_value = snapshot.asset_balance * snapshot.asset_price_fiat
    total = snapshot.fiat_balance + asset_value
    pct = Decimal('0') if total <= 0 else (asset_value / total) * Decimal('100')
    if pct < low_asset_pct:
        return InventoryDecision(pct.quantize(Decimal('0.01')), 'BUY_ASSET', 'asset_inventory_low')
    if pct > high_asset_pct:
        return InventoryDecision(pct.quantize(Decimal('0.01')), 'SELL_ASSET', 'asset_inventory_high')
    return InventoryDecision(pct.quantize(Decimal('0.01')), 'NEUTRAL', 'inventory_in_target_band')
