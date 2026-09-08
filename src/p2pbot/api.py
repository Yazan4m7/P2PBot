from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from .binance_public import BinancePublicClient, BinancePublicError
from .config import get_settings
from .db import Repository
from .service import MarketService

settings = get_settings()
repo = Repository(settings.database_url)
repo.create_schema()
client = BinancePublicClient(settings.binance_mgs_base, settings.request_timeout_seconds)
service = MarketService(settings, repo, client)

app = FastAPI(title="Binance P2P Research Bot — Phases 1-3", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "mode": "read-only", "money_movement": False}


@app.post("/scan")
def scan(
    fiat: str = Query(default=settings.default_fiat, min_length=2, max_length=10),
    asset: str = Query(default=settings.default_asset, min_length=2, max_length=10),
):
    try:
        return service.scan_and_analyze(fiat=fiat, asset=asset)
    except BinancePublicError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/opportunities")
def opportunities(limit: int = Query(default=50, ge=1, le=500)):
    return {"items": repo.recent_opportunities(limit)}
