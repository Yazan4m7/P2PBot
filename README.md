# Binance P2P Bot — Phases 1–3

A **read-only** implementation of:

1. **Market scanner** — downloads public Binance P2P ads for BUY/SELL.
2. **Opportunity engine** — pairs feasible buy/sell ads and calculates gross/net spread after configurable slippage, platform fees and bank fees.
3. **Merchant scoring** — scores merchant quality from completion rate, order history, release time, payment-method compatibility and merchant type.

It does **not** create orders, mark orders paid, release crypto, withdraw funds or access a bank account.

## Requirements

- Python 3.12+
- SQLite works out of the box. PostgreSQL is supported by installing the optional `postgres` dependency and changing `DATABASE_URL`.

## Install

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
pip install -e ".[dev]"
copy .env.example .env
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Test

```bash
pytest
```

## One live scan

```bash
p2pbot scan --fiat JOD --asset USDT
```

## Continuous scanner

```bash
p2pbot run --fiat JOD --asset USDT --interval 10
```

Every scan stores ad snapshots, merchant observations and detected opportunities in the configured database.

## API

```bash
uvicorn p2pbot.api:app --reload
```

Endpoints:

- `GET /health`
- `POST /scan?fiat=JOD&asset=USDT`
- `GET /opportunities?limit=50`

## Important configuration

Edit `.env`:

```dotenv
MIN_COMPLETION_RATE=95
MIN_MERCHANT_ORDERS=20
MIN_NET_ROI_PCT=0.20
MAX_TRADE_FIAT=500
SLIPPAGE_BPS_PER_LEG=5
PLATFORM_FEE_BPS_PER_LEG=0
FIXED_BANK_FEE_BUY=0
FIXED_BANK_FEE_SELL=0
PREFERRED_PAYMENT_METHODS=
```

Payment-method values must be the exact identifiers Binance returns for the selected fiat. Leaving the setting blank accepts any method.

## Database tables

- `merchants`
- `ad_snapshots`
- `opportunities`

## Notes on BUY/SELL

The implementation follows Binance's current public P2P agent API semantics: `BUY` means the user is buying the crypto asset; `SELL` means the user is selling it. An opportunity therefore requires `SELL price > BUY price` after costs.

## Public Binance endpoints used

- `/bapi/c2c/v1/public/c2c/agent/ad-list`
- `/bapi/c2c/v1/public/c2c/agent/trade-methods`
- `/bapi/c2c/v1/public/c2c/agent/check-version`

No credentials are used by phases 1–3.
