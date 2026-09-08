# P2PBot

Binance P2P market research and paper-automation service, configured by default for USDT/JOD.

## Phase status

| Phase | Status |
|---|---|
| 1 Market scanner | Implemented: public P2P ads + persistence |
| 2 Opportunity engine | Implemented: spread, limits, slippage, fees, ROI |
| 3 Merchant scoring | Implemented |
| 4 Paper trading | Implemented: complete simulated lifecycle + P&L |
| 5 Authenticated Binance | Implemented read-only: personal P2P history + capability probe |
| 6 Order state machine | Implemented; no undocumented live order placement |
| 7 Idempotency | Implemented with persistent keys |
| 8 Banking | Adapter boundary and transfer proposals only |
| 9 Payment matching | Implemented: amount/currency/time/status/name verification |
| 10 Inventory | Implemented |
| 11 Dynamic ads | Pricing proposals; live merchant writes not assumed |
| 12 Risk engine | Implemented |
| 13 Circuit breakers | Persistent kill switch implemented |
| 14 Reconciliation | Implemented |
| 15 Dashboard | Implemented at `/dashboard` |
| 16 Event logging | Implemented |
| 17 Deployment | Docker/PostgreSQL + GitHub CI |
| 18 Continuous loop | Read-only scanning and paper execution |

The repository deliberately does not automate Binance/banking UI clicks, unattended fiat transfers, or crypto release. The account capability probe determines which documented authenticated P2P features the configured Binance API key actually has.

## Install

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

Linux/macOS: activate `.venv/bin/activate` and copy `.env.example` to `.env`.

## Tests

```bash
pytest
```

The suite covers public parsing/client behavior, opportunity logic, merchant scoring, signed SAPI requests, capability probing, state transitions, risk controls, payment verification, inventory, reconciliation, paper execution, event logging, idempotency and the kill switch.

## Public scanner

```bash
p2pbot scan --fiat JOD --asset USDT
p2pbot run --fiat JOD --asset USDT --interval 10
```

## Paper execution

```bash
p2pbot paper --fiat JOD --asset USDT
p2pbot paper-run --fiat JOD --asset USDT --interval 10
p2pbot paper-trades
```

## Optional authenticated account sync

A Binance browser login is not an API credential. For read-only personal P2P history/capability probing, create an API key with the minimum required permissions and set these only in your local environment or secret manager:

```dotenv
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
```

Then run:

```bash
p2pbot capabilities
p2pbot sync-orders --rows 50
```

Do not commit real keys.

## API and dashboard

```bash
uvicorn p2pbot.api:app --host 0.0.0.0 --port 8000
```

Main endpoints:

- `GET /health`
- `GET /status`
- `POST /scan`
- `POST /paper/run`
- `GET /paper/trades`
- `GET /opportunities`
- `GET /events`
- `GET /capabilities`
- `POST /account/orders/sync`
- `GET /account/orders`
- `POST /kill-switch/true`
- `POST /kill-switch/false`
- `GET /dashboard`

## Docker

```bash
docker compose up --build
```

This starts the API and PostgreSQL. Live money actions remain disabled.
