from datetime import datetime, timezone
from decimal import Decimal

from p2pbot.domain import Opportunity
from p2pbot.risk import RiskContext, RiskPolicy


def op(score=90.0):
    return Opportunity(buy_ad_no='b', sell_ad_no='s', buy_merchant_no='m1', sell_merchant_no='m2', asset='USDT', fiat='JOD', asset_amount=Decimal('100'), buy_price=Decimal('0.70'), sell_price=Decimal('0.71'), gross_profit_fiat=Decimal('1'), net_profit_fiat=Decimal('0.8'), net_roi_pct=Decimal('1.1'), buy_merchant_score=score, sell_merchant_score=score, common_payment_methods=('BANK',), observed_at=datetime.now(timezone.utc))


def policy():
    return RiskPolicy(max_trade_fiat=Decimal('500'), max_daily_turnover_fiat=Decimal('5000'), max_daily_loss_fiat=Decimal('50'), max_open_trades=3, max_merchant_exposure_fiat=Decimal('500'), min_merchant_score=75, stale_market_seconds=45, max_price_jump_pct=3)


def test_risk_allows_normal_trade():
    assert policy().evaluate(op(), RiskContext()).allowed


def test_risk_blocks_kill_switch_and_low_score():
    decision = policy().evaluate(op(50), RiskContext(kill_switch=True))
    assert not decision.allowed
    assert 'kill_switch_enabled' in decision.reasons
    assert 'merchant_score_below_minimum' in decision.reasons
