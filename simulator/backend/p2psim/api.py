from __future__ import annotations

import asyncio
import json
from decimal import Decimal

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .auth import verify_signed_request
from .config import get_settings
from .database import Database
from .domain import CreateOrderRequest, FaultKind, SimulatorError
from .engine import SimulatorEngine

settings = get_settings()
db = Database(settings.database_url)
engine = SimulatorEngine(db, settings)

app = FastAPI(title="P2P Simulator", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys([settings.frontend_origin, "http://127.0.0.1:5173", "http://localhost:5173"])),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-MBX-APIKEY", "Last-Event-ID"],
)


@app.exception_handler(SimulatorError)
async def simulator_error_handler(_: Request, exc: SimulatorError):
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": str(exc)})


def apply_fault(name: str, *, after=None):
    fault = engine.consume_fault(name)
    if not fault:
        return None
    kind = fault["kind"]
    if kind == "HTTP_429":
        raise HTTPException(status_code=429, detail="simulated rate limit")
    if kind == "HTTP_500":
        raise HTTPException(status_code=500, detail="simulated server failure")
    if kind == "TIMEOUT_BEFORE":
        raise HTTPException(status_code=504, detail="simulated timeout before processing")
    if kind == "TIMEOUT_AFTER" and after is not None:
        result = after()
        raise HTTPException(status_code=504, detail={"message": "simulated timeout after commit", "committed_entity": result.get("order_no")})
    return fault


class CreateOrderBody(BaseModel):
    ad_no: str
    payment_method: str
    fiat_amount: Decimal | None = None
    asset_amount: Decimal | None = None
    expected_price: Decimal | None = None
    bot_trade_id: str | None = None


class ScenarioBody(BaseModel):
    scenario: str


class DisputeBody(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class SpeedBody(BaseModel):
    speed: float


class AdvanceBody(BaseModel):
    seconds: float = Field(ge=0)


class PriceBody(BaseModel):
    price: Decimal = Field(gt=0)


class ShockBody(BaseModel):
    pct: Decimal


class FreezeBody(BaseModel):
    frozen: bool


class FaultBody(BaseModel):
    kind: FaultKind
    remaining: int = Field(default=1, ge=1, le=1000)
    payload: dict = Field(default_factory=dict)


class ResolveBody(BaseModel):
    winner: str


class ChatBody(BaseModel):
    sender: str
    body: str
    idempotency_key: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "simulator": True, "simulation": engine.status()}


@app.get("/ready")
def ready():
    return {"ready": True, "reconciliation": engine.reconcile_balances()}


@app.get("/bapi/c2c/v1/public/c2c/agent/check-version")
def check_version(version: str = "2.0.0"):
    return {"success": True, "data": {"compatible": True, "version": version, "simulator": True}}


@app.get("/bapi/c2c/v1/public/c2c/agent/trade-methods")
def trade_methods(fiat: str = "JOD"):
    return {"success": True, "data": engine.trade_methods(fiat)}


@app.get("/bapi/c2c/v1/public/c2c/agent/ad-list")
def ad_list(
    fiat: str,
    asset: str,
    tradeType: str,
    limit: int = Query(default=20, ge=1, le=20),
    tradeMethodIdentifiers: list[str] = Query(default=[]),
):
    fault = apply_fault("public_ad_list")
    if fault and fault["kind"] == "MALFORMED":
        return {"success": True, "data": [{"adv": {"price": "not-a-number"}}]}
    return engine.public_ads(fiat=fiat, asset=asset, trade_type=tradeType, limit=limit, payment_methods=tradeMethodIdentifiers)


@app.post("/sim/api/v1/orders")
def create_order(body: CreateOrderBody, idempotency_key: str = Header(alias="Idempotency-Key")):
    fault = engine.consume_fault("order_create")
    req = CreateOrderRequest(
        ad_no=body.ad_no,
        payment_method=body.payment_method,
        idempotency_key=idempotency_key,
        fiat_amount=body.fiat_amount,
        asset_amount=body.asset_amount,
        expected_price=body.expected_price,
        bot_trade_id=body.bot_trade_id,
    )
    if fault and fault["kind"] == "TIMEOUT_BEFORE":
        raise HTTPException(status_code=504, detail="simulated timeout before order commit")
    result = engine.create_order(req)
    if fault and fault["kind"] == "TIMEOUT_AFTER":
        raise HTTPException(status_code=504, detail={"message": "simulated timeout after order commit", "order_no": result["order_no"]})
    if fault and fault["kind"] == "HTTP_500":
        raise HTTPException(status_code=500, detail="simulated order-create failure")
    return result


@app.get("/sim/api/v1/orders/{order_no}")
def get_order(order_no: str):
    return engine.get_order(order_no)


@app.get("/sim/api/v1/orders")
def list_orders(limit: int = Query(default=100, ge=1, le=1000)):
    return {"items": engine.list_orders(limit)}


@app.post("/sim/api/v1/orders/{order_no}/send-cash")
def send_cash(order_no: str, body: ScenarioBody, idempotency_key: str = Header(alias="Idempotency-Key")):
    fault = engine.consume_fault("send_cash")
    if fault and fault["kind"] == "TIMEOUT_BEFORE":
        raise HTTPException(status_code=504, detail="simulated timeout before send placeholder")
    result = engine.send_cash(order_no, idempotency_key=idempotency_key, scenario=body.scenario)
    if fault and fault["kind"] == "TIMEOUT_AFTER":
        raise HTTPException(status_code=504, detail="simulated timeout after send placeholder commit")
    return result


@app.post("/sim/api/v1/orders/{order_no}/mark-paid")
def mark_paid(order_no: str, idempotency_key: str = Header(alias="Idempotency-Key")):
    fault = engine.consume_fault("mark_paid")
    if fault and fault["kind"] == "TIMEOUT_BEFORE":
        raise HTTPException(status_code=504, detail="simulated timeout before mark-paid")
    result = engine.mark_paid(order_no, idempotency_key=idempotency_key)
    if fault and fault["kind"] == "TIMEOUT_AFTER":
        raise HTTPException(status_code=504, detail="simulated timeout after mark-paid commit")
    return result


@app.post("/sim/api/v1/orders/{order_no}/verify-cash")
def verify_cash(order_no: str):
    return engine.verify_cash(order_no)


@app.post("/sim/api/v1/orders/{order_no}/release")
def release(order_no: str, idempotency_key: str = Header(alias="Idempotency-Key")):
    fault = engine.consume_fault("release")
    if fault and fault["kind"] == "TIMEOUT_BEFORE":
        raise HTTPException(status_code=504, detail="simulated timeout before release")
    result = engine.release(order_no, idempotency_key=idempotency_key)
    if fault and fault["kind"] == "TIMEOUT_AFTER":
        raise HTTPException(status_code=504, detail="simulated timeout after release commit")
    return result


@app.post("/sim/api/v1/orders/{order_no}/cancel")
def cancel(order_no: str, idempotency_key: str = Header(alias="Idempotency-Key")):
    return engine.cancel(order_no, idempotency_key=idempotency_key)


@app.post("/sim/api/v1/orders/{order_no}/dispute")
def dispute(order_no: str, body: DisputeBody, idempotency_key: str = Header(alias="Idempotency-Key")):
    return engine.open_dispute(order_no, reason=body.reason, idempotency_key=idempotency_key)


@app.get("/sim/api/v1/orders/{order_no}/timeline")
def order_timeline(order_no: str):
    return {"items": engine.order_timeline(order_no)}


@app.get("/sim/api/v1/orders/{order_no}/payments")
def order_payments(order_no: str):
    return {"items": engine.payment_evidence(order_no)}


@app.get("/sim/api/v1/balances")
def balances(account_id: str = "BOT"):
    return {"items": engine.balances(account_id)}


@app.get("/sim/api/v1/events/poll")
def events_poll(after_id: int = 0, limit: int = Query(default=200, ge=1, le=1000)):
    return {"items": engine.events(after_id=after_id, limit=limit)}


@app.get("/sim/api/v1/events")
async def events_stream(request: Request, after_id: int = 0):
    async def generate():
        cursor = after_id
        while not await request.is_disconnected():
            items = engine.events(after_id=cursor, limit=100)
            if items:
                for item in items:
                    cursor = item["id"]
                    yield f"id: {item['id']}\nevent: {item['event_type']}\ndata: {json.dumps(item)}\n\n"
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/sim/api/v1/orders/{order_no}/chat")
def send_chat(order_no: str, body: ChatBody):
    return engine.send_chat(order_no, sender=body.sender, body=body.body, idempotency_key=body.idempotency_key)


@app.get("/sim/api/v1/orders/{order_no}/chat")
def chat_history(order_no: str):
    return {"items": engine.chat_history(order_no)}


@app.get("/sapi/v1/c2c/orderMatch/listUserOrderHistory")
def auth_order_history(request: Request, page: int = 1, rows: int = 20, tradeType: str | None = None):
    verify_signed_request(request, expected_api_key=settings.test_api_key, expected_secret=settings.test_api_secret, required=settings.auth_required)
    return engine.personal_order_history(page=page, rows=rows, trade_type=tradeType)


@app.get("/sapi/v1/c2c/orderMatch/getUserOrderSummary")
def auth_order_summary(request: Request):
    verify_signed_request(request, expected_api_key=settings.test_api_key, expected_secret=settings.test_api_secret, required=settings.auth_required)
    return engine.order_summary()


@app.post("/sapi/v1/c2c/agent/orderMatch/getUserOrderDetail")
def auth_order_detail(request: Request, orderNumber: str):
    verify_signed_request(request, expected_api_key=settings.test_api_key, expected_secret=settings.test_api_secret, required=settings.auth_required)
    return {"data": engine.get_order(orderNumber)}


@app.get("/sapi/v1/c2c/agent/ads/getAvailableAdsCategory")
def auth_ad_categories(request: Request):
    verify_signed_request(request, expected_api_key=settings.test_api_key, expected_secret=settings.test_api_secret, required=settings.auth_required)
    return {"data": [{"asset": settings.default_asset, "fiat": settings.default_fiat, "tradeTypes": ["BUY", "SELL"]}]}


@app.get("/sim/admin/status")
def admin_status(): return engine.status()
@app.post("/sim/admin/pause")
def admin_pause(): return engine.pause()
@app.post("/sim/admin/resume")
def admin_resume(): return engine.resume()
@app.post("/sim/admin/speed")
def admin_speed(body: SpeedBody): return engine.set_speed(body.speed)
@app.post("/sim/admin/advance")
def admin_advance(body: AdvanceBody): return engine.advance(body.seconds)
@app.post("/sim/admin/market/tick")
def admin_tick(): return engine.market_tick()
@app.post("/sim/admin/market/price")
def admin_price(body: PriceBody): return engine.set_reference_price(body.price)
@app.post("/sim/admin/market/shock")
def admin_shock(body: ShockBody): return engine.price_shock(body.pct)
@app.post("/sim/admin/market/freeze")
def admin_freeze(body: FreezeBody): return engine.freeze_market(body.frozen)
@app.get("/sim/admin/market/history")
def admin_history(limit: int = 100): return {"items": engine.price_history(limit)}
@app.get("/sim/admin/ads")
def admin_ads(): return {"items": engine.list_ads_admin()}
@app.post("/sim/admin/ads/{ad_no}/close")
def admin_close_ad(ad_no: str): return engine.close_ad(ad_no)
@app.post("/sim/admin/ads/{ad_no}/pause")
def admin_pause_ad(ad_no: str): return engine.pause_ad(ad_no, True)
@app.post("/sim/admin/ads/{ad_no}/activate")
def admin_activate_ad(ad_no: str): return engine.pause_ad(ad_no, False)
@app.post("/sim/admin/ads/{ad_no}/reprice")
def admin_reprice(ad_no: str, body: PriceBody): return engine.reprice_ad(ad_no, body.price)
@app.post("/sim/admin/orders/{order_no}/payment")
def admin_force_payment(order_no: str, body: ScenarioBody): return engine.force_payment(order_no, body.scenario)
@app.post("/sim/admin/orders/{order_no}/expire")
def admin_expire(order_no: str): return engine.force_expire(order_no)
@app.post("/sim/admin/orders/{order_no}/resolve")
def admin_resolve(order_no: str, body: ResolveBody): return engine.resolve_dispute(order_no, winner=body.winner)
@app.get("/sim/admin/scheduled-events")
def admin_scheduled(): return {"items": engine.scheduled_events()}
@app.post("/sim/admin/scheduler/run")
def admin_scheduler_run(): return {"processed": engine.run_due_events()}
@app.post("/sim/admin/faults/{name}")
def admin_set_fault(name: str, body: FaultBody): return engine.set_fault(name, body.kind, remaining=body.remaining, payload=body.payload)
@app.get("/sim/admin/faults")
def admin_faults(): return {"items": engine.faults()}
@app.get("/sim/admin/events")
def admin_events(after_id: int = 0): return {"items": engine.events(after_id=after_id)}
@app.get("/sim/admin/metrics")
def admin_metrics(): return engine.metrics()
@app.get("/sim/admin/replay")
def admin_replay(): return engine.export_replay()
@app.post("/sim/admin/reset")
def admin_reset(seed: int | None = None): return engine.reset(seed=seed)


@app.get("/simulator", response_class=HTMLResponse)
def simulator_ui():
    return """<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>P2P Simulator</title><style>
body{font-family:system-ui;margin:0;background:#0b0e11;color:#eaecef}header{padding:14px 22px;background:#181a20;display:flex;justify-content:space-between;align-items:center}.banner{color:#f0b90b;font-weight:700}.wrap{padding:20px;max-width:1200px;margin:auto}.tabs button,.controls button{margin:4px;padding:8px 12px;background:#2b3139;color:white;border:0;border-radius:6px;cursor:pointer}.tabs button.active{background:#f0b90b;color:#111}.grid{display:grid;grid-template-columns:1fr;gap:14px}.card{background:#181a20;border-radius:10px;padding:14px;overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #2b3139;text-align:left}button.buy{background:#0ecb81;color:#071}.sell{background:#f6465d;color:white}.muted{color:#848e9c}pre{white-space:pre-wrap}@media(max-width:700px){th:nth-child(4),td:nth-child(4){display:none}.wrap{padding:10px}}
</style></head><body><header><div><b>P2P Simulator</b> <span class='banner'>SIMULATOR ONLY — NO REAL FUNDS</span></div><div id='clock'></div></header>
<div class='wrap'><div class='tabs'><button id='buy' class='active' onclick="side='BUY';loadAds()">Buy USDT</button><button id='sell' onclick="side='SELL';loadAds()">Sell USDT</button></div>
<div class='controls'><button onclick='tick()'>Market tick</button><button onclick='advance()'>Advance 10m</button><button onclick='load()'>Refresh</button></div>
<div class='grid'><div class='card'><h3>USDT/JOD Market</h3><table><thead><tr><th>Merchant</th><th>Price</th><th>Available</th><th>Limits</th><th>Payment</th><th></th></tr></thead><tbody id='ads'></tbody></table></div>
<div class='card'><h3>Latest Orders</h3><pre id='orders'></pre></div><div class='card'><h3>Simulation</h3><pre id='status'></pre></div></div></div>
<script>let side='BUY';async function j(u,o){let r=await fetch(u,o);let x=await r.json();if(!r.ok)throw Error(JSON.stringify(x));return x}async function loadAds(){buy.className=side==='BUY'?'active':'';sell.className=side==='SELL'?'active':'';let x=await j('/bapi/c2c/v1/public/c2c/agent/ad-list?fiat=JOD&asset=USDT&tradeType='+side+'&limit=20');ads.innerHTML=x.data.map(i=>`<tr><td>${i.advertiser.nickName}<div class=muted>${(i.advertiser.monthFinishRate*100).toFixed(1)}% · ${i.advertiser.monthOrderCount} orders</div></td><td>${i.adv.price} JOD</td><td>${i.adv.surplusAmount} USDT</td><td>${i.adv.minSingleTransAmount}-${i.adv.maxSingleTransAmount}</td><td>${i.adv.tradeMethods.map(m=>m.identifier).join(', ')}</td><td><button class='${side==='BUY'?'buy':'sell'}' onclick="create('${i.adv.adNo}', '${i.adv.price}', '${i.adv.tradeMethods[0].identifier}')">${side}</button></td></tr>`).join('')}async function load(){let s=await j('/sim/admin/status');status.textContent=JSON.stringify(s,null,2);clock.textContent=s.simulated_time;orders.textContent=JSON.stringify((await j('/sim/api/v1/orders?limit=5')).items,null,2);await loadAds()}async function tick(){await j('/sim/admin/market/tick',{method:'POST'});load()}async function advance(){await j('/sim/admin/advance',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({seconds:600})});load()}async function create(ad,price,pm){let body={ad_no:ad,payment_method:pm,fiat_amount:'100',expected_price:price};try{let o=await j('/sim/api/v1/orders',{method:'POST',headers:{'content-type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});location.hash=o.order_no;orders.textContent=JSON.stringify(o,null,2)}catch(e){alert(e)}}load();setInterval(()=>load(),5000)</script></body></html>"""
