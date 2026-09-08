from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    ok: bool
    expected_fiat: Decimal
    actual_fiat: Decimal
    fiat_difference: Decimal
    expected_asset: Decimal
    actual_asset: Decimal
    asset_difference: Decimal


def reconcile(
    *,
    starting_fiat: Decimal,
    fiat_in: Decimal,
    fiat_out: Decimal,
    actual_fiat: Decimal,
    starting_asset: Decimal,
    asset_in: Decimal,
    asset_out: Decimal,
    actual_asset: Decimal,
    fiat_tolerance: Decimal = Decimal('0.01'),
    asset_tolerance: Decimal = Decimal('0.000001'),
) -> ReconciliationResult:
    expected_fiat = starting_fiat + fiat_in - fiat_out
    expected_asset = starting_asset + asset_in - asset_out
    fiat_diff = actual_fiat - expected_fiat
    asset_diff = actual_asset - expected_asset
    ok = abs(fiat_diff) <= fiat_tolerance and abs(asset_diff) <= asset_tolerance
    return ReconciliationResult(
        ok=ok,
        expected_fiat=expected_fiat,
        actual_fiat=actual_fiat,
        fiat_difference=fiat_diff,
        expected_asset=expected_asset,
        actual_asset=actual_asset,
        asset_difference=asset_diff,
    )
