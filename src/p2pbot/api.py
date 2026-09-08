from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from .binance_auth import BinanceAuthError
from .binance_public import BinancePublicClient, BinancePublicError
from .config import get_settings
from .db import Repository
from .service import BotService, MarketService

settings = get_settings()
repo = Repository(settings.database_url)
repo.create_schema()
client = BinancePublicClient(settings.binance_mgs_base, settings.request_timeout_seconds)
market = MarketService(settings, repo, client)
bot = BotService(settings, repo, market)

app = FastAPI(title='Binance P2P Research Bot', version='0.2.0')


@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'paper/read-only', 'money_movement': False}


@app.get('/status')
def status():
    return bot.status()


@app.post('/scan')
def scan(fiat: str = Query(default=settings.default_fiat, min_length=2, max_length=10), asset: str = Query(default=settings.default_asset, min_length=2, max_length=10)):
    try:
        return market.scan_and_analyze(fiat=fiat, asset=asset)
    except BinancePublicError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post('/paper/run')
def paper_run(fiat: str = Query(default=settings.default_fiat, min_length=2, max_length=10), asset: str = Query(default=settings.default_asset, min_length=2, max_length=10)):
    try:
        return bot.paper_once(fiat=fiat, asset=asset)
    except BinancePublicError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get('/paper/trades')
def paper_trades(limit: int = Query(default=50, ge=1, le=500)):
    return {'items': repo.recent_paper_trades(limit), 'stats': repo.paper_stats()}


@app.get('/opportunities')
def opportunities(limit: int = Query(default=50, ge=1, le=500)):
    return {'items': repo.recent_opportunities(limit)}


@app.get('/events')
def events(limit: int = Query(default=100, ge=1, le=1000)):
    return {'items': repo.recent_events(limit)}


@app.get('/capabilities')
def capabilities():
    try:
        return bot.capabilities()
    except BinanceAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post('/account/orders/sync')
def sync_orders(rows: int = Query(default=50, ge=1, le=100)):
    try:
        return bot.sync_account_orders(rows)
    except BinanceAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get('/account/orders')
def account_orders(limit: int = Query(default=50, ge=1, le=500)):
    return {'items': repo.recent_account_orders(limit)}


@app.post('/kill-switch/{enabled}')
def kill_switch(enabled: bool):
    repo.set_state('kill_switch', 'true' if enabled else 'false')
    repo.append_event('KILL_SWITCH', severity='WARNING' if enabled else 'INFO', payload={'enabled': enabled})
    return {'kill_switch': enabled}


@app.get('/dashboard', response_class=HTMLResponse)
def dashboard():
    return '''<!doctype html><html><head><meta charset="utf-8"><title>P2PBot</title><style>body{font-family:system-ui;margin:32px;max-width:1100px}pre{background:#f5f5f5;padding:16px;overflow:auto}button{padding:8px 12px;margin-right:8px}</style></head><body><h1>P2PBot dashboard</h1><p>Mode: paper/read-only. No money movement.</p><button onclick="load()">Refresh</button><button onclick="paper()">Run paper cycle</button><h2>Status</h2><pre id="status"></pre><h2>Recent paper trades</h2><pre id="trades"></pre><script>async function load(){status.textContent=JSON.stringify(await (await fetch('/status')).json(),null,2);trades.textContent=JSON.stringify(await (await fetch('/paper/trades?limit=10')).json(),null,2)} async function paper(){await fetch('/paper/run',{method:'POST'});await load()} load();</script></body></html>'''
