# P2P Simulator Backend

Deterministic, persistent Binance-P2P-like simulator for P2PBot.

```bash
pip install -e ".[dev]"
p2psim serve --port 8090
```

Browser UI: `http://127.0.0.1:8090/simulator`

The service has no production money integration. Payment seams are synthetic:

- `<send cash function here>` -> `/sim/api/v1/orders/{order}/send-cash`
- `<verify cash received function here>` -> `/sim/api/v1/orders/{order}/verify-cash`

Fake authenticated API fixture:

- key: `SIMULATOR_TEST_KEY`
- secret: `SIMULATOR_TEST_SECRET`

Never use production credentials with this service.
