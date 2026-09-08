from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AdPriceProposal:
    side: str
    market_reference: Decimal
    proposed_price: Decimal
    tick: Decimal
    status: str = 'PROPOSAL_ONLY'


def propose_competitive_price(*, side: str, market_reference: Decimal, tick: Decimal) -> AdPriceProposal:
    side = side.upper()
    if tick <= 0:
        raise ValueError('tick must be positive')
    if side == 'BUY':
        price = market_reference + tick
    elif side == 'SELL':
        price = max(Decimal('0'), market_reference - tick)
    else:
        raise ValueError('side must be BUY or SELL')
    return AdPriceProposal(side=side, market_reference=market_reference, proposed_price=price, tick=tick)
