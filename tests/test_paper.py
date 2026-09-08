from datetime import datetime, timezone
from decimal import Decimal

from p2pbot.domain import Opportunity, TradeState
from p2pbot.paper import PaperExecutionEngine
from p2pbot.risk import RiskContext, RiskPolicy


def test_paper_engine_completes_without_external_actions():
    op = Opportunity(buy_ad_no='b', sell_ad_no='s', buy_merchant_no='m1', sell_merchant_no='m2', asset='USDT', fiat='JOD', asset_amount=Decimal('100'), buy_price=Decimal('0.70'), sell_price=Decimal('0.71'), gross_profit_fiat=Decimal('1'), net_profit_fiat=Decimal('0.8'), net_roi_pct=Decimal('1.1'), buy_merchant_score=95, sell_merchant_score=95, common_payment_methods=('BANK',), observed_at=datetime.now(timezone.utc))
    policy = RiskPolicy(Decimal('500'), Decimal('5000'), Decimal('50'), 3, Decimal('500'), 75, 45, 3)
    trade = PaperExecutionEngine(policy).execute(op, RiskContext())
    assert trade.state == TradeState.COMPLETED
    assert trade.realized_profit_fiat == Decimal('0.8')
