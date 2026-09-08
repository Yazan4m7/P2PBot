from p2psim.api import engine


def snapshot():
    ads = engine.public_ads(fiat="JOD", asset="USDT", trade_type="BUY", limit=20, payment_methods=[])["data"]
    return [(x["adv"]["adNo"], x["adv"]["price"], x["advertiser"]["merchantNo"], x["advertiser"]["monthOrderCount"]) for x in ads]


def test_same_seed_same_initial_market():
    engine.reset(seed=777)
    first = snapshot()
    engine.reset(seed=777)
    second = snapshot()
    assert first == second


def test_different_seed_changes_merchant_metrics():
    engine.reset(seed=777)
    first = snapshot()
    engine.reset(seed=778)
    second = snapshot()
    assert first != second


def test_price_tick_reproducible_by_seed():
    engine.reset(seed=91)
    p1 = [engine.market_tick()["price"] for _ in range(5)]
    engine.reset(seed=91)
    p2 = [engine.market_tick()["price"] for _ in range(5)]
    assert p1 == p2


def test_virtual_clock_pause_and_advance():
    engine.pause()
    before = engine.clock.now()
    result = engine.advance(600)
    after = engine.clock.now()
    assert (after - before).total_seconds() == 600
    assert result["status"] == "PAUSED"
