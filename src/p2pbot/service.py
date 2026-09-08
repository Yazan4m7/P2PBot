from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

from .binance_public import BinancePublicClient
from .config import Settings
from .db import Repository
from .opportunity import find_opportunities


class MarketService:
    def __init__(self, settings: Settings, repository: Repository, client: BinancePublicClient):
        self.settings = settings
        self.repository = repository
        self.client = client

    def scan_and_analyze(self, fiat: str | None = None, asset: str | None = None) -> dict:
        fiat = (fiat or self.settings.default_fiat).upper()
        asset = (asset or self.settings.default_asset).upper()
        methods = self.settings.preferred_payment_methods

        buy_ads = self.client.get_ads(
            fiat=fiat,
            asset=asset,
            trade_type="BUY",
            limit=self.settings.scan_limit,
            payment_methods=methods or None,
        )
        sell_ads = self.client.get_ads(
            fiat=fiat,
            asset=asset,
            trade_type="SELL",
            limit=self.settings.scan_limit,
            payment_methods=methods or None,
        )

        self.repository.save_ads([*buy_ads, *sell_ads])
        opportunities = find_opportunities(
            buy_ads,
            sell_ads,
            min_completion_rate=self.settings.min_completion_rate,
            min_merchant_orders=self.settings.min_merchant_orders,
            min_net_roi_pct=self.settings.min_net_roi_pct,
            max_trade_fiat=Decimal(str(self.settings.max_trade_fiat)),
            slippage_bps_per_leg=Decimal(str(self.settings.slippage_bps_per_leg)),
            platform_fee_bps_per_leg=Decimal(str(self.settings.platform_fee_bps_per_leg)),
            fixed_bank_fee_buy=Decimal(str(self.settings.fixed_bank_fee_buy)),
            fixed_bank_fee_sell=Decimal(str(self.settings.fixed_bank_fee_sell)),
            preferred_payment_methods=set(methods),
        )
        self.repository.save_opportunities(opportunities)

        def serialize_op(op):
            result = asdict(op)
            for key, value in list(result.items()):
                if isinstance(value, Decimal):
                    result[key] = str(value)
                elif hasattr(value, "isoformat"):
                    result[key] = value.isoformat()
            return result

        return {
            "pair": f"{asset}/{fiat}",
            "buy_ads": len(buy_ads),
            "sell_ads": len(sell_ads),
            "opportunity_count": len(opportunities),
            "opportunities": [serialize_op(x) for x in opportunities[:20]],
        }
