from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

from .binance_auth import BinanceAuthClient
from .binance_public import BinancePublicClient
from .config import Settings
from .db import Repository
from .opportunity import find_opportunities
from .paper import PaperExecutionEngine
from .risk import RiskContext, RiskPolicy


class MarketService:
    def __init__(self, settings: Settings, repository: Repository, client: BinancePublicClient):
        self.settings = settings
        self.repository = repository
        self.client = client

    def scan_objects(self, fiat: str | None = None, asset: str | None = None):
        fiat = (fiat or self.settings.default_fiat).upper()
        asset = (asset or self.settings.default_asset).upper()
        methods = self.settings.preferred_payment_methods
        buy_ads = self.client.get_ads(fiat=fiat, asset=asset, trade_type='BUY', limit=self.settings.scan_limit, payment_methods=methods or None)
        sell_ads = self.client.get_ads(fiat=fiat, asset=asset, trade_type='SELL', limit=self.settings.scan_limit, payment_methods=methods or None)
        self.repository.save_ads([*buy_ads, *sell_ads])
        opportunities = find_opportunities(buy_ads, sell_ads, min_completion_rate=self.settings.min_completion_rate, min_merchant_orders=self.settings.min_merchant_orders, min_net_roi_pct=self.settings.min_net_roi_pct, max_trade_fiat=Decimal(str(self.settings.max_trade_fiat)), slippage_bps_per_leg=Decimal(str(self.settings.slippage_bps_per_leg)), platform_fee_bps_per_leg=Decimal(str(self.settings.platform_fee_bps_per_leg)), fixed_bank_fee_buy=Decimal(str(self.settings.fixed_bank_fee_buy)), fixed_bank_fee_sell=Decimal(str(self.settings.fixed_bank_fee_sell)), preferred_payment_methods=set(methods))
        self.repository.save_opportunities(opportunities)
        return fiat, asset, buy_ads, sell_ads, opportunities

    @staticmethod
    def _serialize(value):
        if isinstance(value, Decimal):
            return str(value)
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        return value

    def scan_and_analyze(self, fiat: str | None = None, asset: str | None = None) -> dict:
        fiat, asset, buy_ads, sell_ads, opportunities = self.scan_objects(fiat, asset)
        serialized = []
        for op in opportunities[:20]:
            item = asdict(op)
            item = {k: self._serialize(v) for k, v in item.items()}
            serialized.append(item)
        self.repository.append_event('MARKET_SCAN', payload={'fiat': fiat, 'asset': asset, 'buy_ads': len(buy_ads), 'sell_ads': len(sell_ads), 'opportunities': len(opportunities)})
        return {'pair': f'{asset}/{fiat}', 'buy_ads': len(buy_ads), 'sell_ads': len(sell_ads), 'opportunity_count': len(opportunities), 'opportunities': serialized}


class BotService:
    def __init__(self, settings: Settings, repository: Repository, market: MarketService):
        self.settings = settings
        self.repository = repository
        self.market = market
        self.risk_policy = RiskPolicy(max_trade_fiat=Decimal(str(settings.max_trade_fiat)), max_daily_turnover_fiat=Decimal(str(settings.max_daily_turnover_fiat)), max_daily_loss_fiat=Decimal(str(settings.max_daily_loss_fiat)), max_open_trades=settings.max_open_trades, max_merchant_exposure_fiat=Decimal(str(settings.max_merchant_exposure_fiat)), min_merchant_score=settings.min_merchant_score, stale_market_seconds=settings.stale_market_seconds, max_price_jump_pct=settings.max_price_jump_pct)
        self.paper = PaperExecutionEngine(self.risk_policy)

    def _risk_context(self) -> RiskContext:
        stats = self.repository.paper_stats()
        return RiskContext(daily_turnover_fiat=Decimal(stats['turnover_fiat']), daily_pnl_fiat=Decimal(stats['pnl_fiat']), open_trades=int(stats['open_trades']), kill_switch=self.repository.kill_switch_enabled())

    def paper_once(self, fiat: str | None = None, asset: str | None = None) -> dict:
        fiat, asset, buy_ads, sell_ads, opportunities = self.market.scan_objects(fiat, asset)
        if not opportunities:
            self.repository.append_event('PAPER_NO_OPPORTUNITY', payload={'fiat': fiat, 'asset': asset})
            return {'status': 'NO_OPPORTUNITY', 'pair': f'{asset}/{fiat}'}
        op = opportunities[0]
        trade = self.paper.execute(op, self._risk_context())
        self.repository.save_paper_trade(trade)
        self.repository.append_event('PAPER_TRADE', entity_id=trade.trade_id, payload={'state': trade.state.value, 'profit_fiat': str(trade.realized_profit_fiat), 'buy_ad_no': op.buy_ad_no, 'sell_ad_no': op.sell_ad_no})
        return {'status': trade.state.value, 'trade_id': trade.trade_id, 'pair': f'{asset}/{fiat}', 'profit_fiat': str(trade.realized_profit_fiat), 'buy_cost_fiat': str(trade.buy_cost_fiat), 'sell_revenue_fiat': str(trade.sell_revenue_fiat)}

    def capabilities(self) -> dict:
        if not self.settings.binance_auth_configured:
            return {'auth_configured': False, 'public_market': True, 'personal_order_history': False, 'ad_management_eligibility': False, 'live_money_actions': False, 'next_step': 'Set BINANCE_API_KEY and BINANCE_API_SECRET in the local environment to probe read-only account capabilities.'}
        with BinanceAuthClient(self.settings.binance_api_base, self.settings.binance_api_key or '', self.settings.binance_api_secret or '', self.settings.request_timeout_seconds, self.settings.binance_recv_window_ms) as client:
            result = client.capability_probe()
        result['public_market'] = True
        result['live_money_actions'] = False
        return result

    def sync_account_orders(self, rows: int = 50) -> dict:
        if not self.settings.binance_auth_configured:
            return {'status': 'AUTH_NOT_CONFIGURED', 'saved': 0}
        with BinanceAuthClient(self.settings.binance_api_base, self.settings.binance_api_key or '', self.settings.binance_api_secret or '', self.settings.request_timeout_seconds, self.settings.binance_recv_window_ms) as client:
            payload = client.list_order_history(rows=min(100, max(1, rows)))
        saved = self.repository.save_account_orders(payload)
        self.repository.append_event('ACCOUNT_ORDER_SYNC', payload={'saved': saved})
        return {'status': 'OK', 'saved': saved}

    def status(self) -> dict:
        return {'mode': 'paper/read-only', 'money_movement': False, 'kill_switch': self.repository.kill_switch_enabled(), 'auth_configured': self.settings.binance_auth_configured, 'paper': self.repository.paper_stats(), 'phases': {'1_market_scanner': 'implemented', '2_opportunity_engine': 'implemented', '3_merchant_scoring': 'implemented', '4_paper_trading': 'implemented', '5_authenticated_account_api': 'implemented_read_only', '6_order_state_machine': 'implemented_no_live_order_placement', '7_idempotency': 'implemented', '8_banking': 'adapter_and_proposals_only', '9_payment_matching': 'implemented', '10_inventory': 'implemented', '11_dynamic_ads': 'pricing_proposals_only_non_merchant', '12_risk_engine': 'implemented', '13_circuit_breakers': 'implemented', '14_reconciliation': 'implemented', '15_dashboard': 'implemented', '16_event_logging': 'implemented', '17_deployment': 'docker_and_ci', '18_loop': 'paper/read_only_only'}}
