# P2P Simulator Master Plan

## Purpose

Build a deterministic, Binance-P2P-like simulator whose primary job is to **train, exercise, break, and validate P2PBot end to end without real money or irreversible crypto actions**.

The simulator is not just a visual clone. It must provide:

- a realistic P2P market,
- realistic order lifecycles,
- deterministic counterparties,
- balance and reservation accounting,
- payment placeholders,
- timeouts and disputes,
- failure injection,
- a browser UI similar to the workflow of a P2P exchange,
- API contracts that the existing bot can consume,
- reproducible test scenarios.

The current bot already has public P2P scanning, merchant scoring, opportunity selection, a trade state machine, risk rules, persistence, paper execution, payment mocks, and a dashboard. The simulator must exercise those concrete features rather than inventing unrelated framework code.

## Non-goals

- No connection to a real bank.
- No unattended fiat transfer.
- No real crypto release.
- No attempt to impersonate or bypass Binance permissions.
- No undocumented Binance production endpoint is assumed to exist.
- No pixel-perfect trademark clone is required; workflow fidelity matters more than branding.

Bank boundaries remain explicit placeholders:

```text
<send cash function here>
<verify cash received function here>
```

## Repository placement

Keep the simulator in the same repository initially, but isolate it as a separate service so bot production code does not become simulator-specific.

Proposed structure:

```text
P2PBot/
├─ src/p2pbot/                     existing bot
├─ tests/                          existing bot tests
├─ simulator/
│  ├─ backend/
│  │  ├─ p2psim/
│  │  │  ├─ app.py
│  │  │  ├─ config.py
│  │  │  ├─ domain/
│  │  │  ├─ market/
│  │  │  ├─ ads/
│  │  │  ├─ orders/
│  │  │  ├─ balances/
│  │  │  ├─ counterparties/
│  │  │  ├─ payments/
│  │  │  ├─ disputes/
│  │  │  ├─ realtime/
│  │  │  ├─ scenarios/
│  │  │  ├─ faults/
│  │  │  ├─ api/
│  │  │  └─ persistence/
│  │  └─ tests/
│  ├─ frontend/
│  │  ├─ src/features/market/
│  │  ├─ src/features/orders/
│  │  ├─ src/features/chat/
│  │  ├─ src/features/wallet/
│  │  ├─ src/features/admin/
│  │  └─ e2e/
│  └─ README.md
├─ integration_tests/
│  └─ simulator_bot/
└─ docs/
```

Backend: FastAPI + SQLAlchemy + PostgreSQL, matching the bot's Python ecosystem.

Frontend: React + TypeScript + Vite. Components stay feature-local; no design-system explosion.

Realtime: WebSocket or SSE only where a concrete feature requires server-driven changes.

No Redis/Celery/event-bus dependency is added unless a completed feature demonstrates a real need.

---

# 1. Foundational simulation model

## SIM-001 Simulation instance

**Behavior:** every run has a simulation id, seed, creation time, current simulated time, status, and configuration snapshot.

**Where:** `simulator/backend/p2psim/scenarios/simulation.py`, table `simulations`.

**Needs:** immutable seed, active/paused/finished status, config hash.

**Failures:** invalid seed/config; simultaneous reset/start.

**Tests:** same seed/config creates identical initial market and counterparty assignments.

## SIM-002 Deterministic random source

One PRNG owned by the simulation context; child streams derived deterministically for market, merchants, order behavior and faults.

**Where:** `scenarios/random_source.py`.

Never call module-global `random` from feature code.

## SIM-003 Virtual simulation clock

**Behavior:** normal realtime, paused time, accelerated time, and test-only explicit advance.

**Where:** `scenarios/clock.py`.

Used only because order expiry, merchant delay, ad expiry, market ticks and disputes all genuinely require controllable time.

**Invariant:** all simulator domain timestamps originate from this clock.

## SIM-004 Scheduler

Persist scheduled domain events such as `ORDER_EXPIRE`, `COUNTERPARTY_MARK_PAID`, `SELLER_RELEASE`, `PRICE_TICK`.

**Where:** `scenarios/scheduler.py`, table `scheduled_events`.

**Recovery:** after process restart, due events are claimed transactionally and replayed exactly once.

## SIM-005 Scenario snapshot/export

Export seed + config + clock + event log sufficient to reproduce a failure.

## SIM-006 Scenario reset

Atomic reset of scenario-owned state, forbidden while a reset is already running.

## SIM-007 Simulation pause/resume

Pause scheduler-driven events without corrupting deadlines.

## SIM-008 Speed multiplier

1x/10x/100x for soak testing without waiting real minutes.

---

# 2. Reference data

## REF-001 Assets

USDT initially; schema supports additional assets without generic asset framework work until actually needed.

Fields: symbol, decimals, enabled.

## REF-002 Fiat currencies

JOD initially; amount precision and display precision are explicit.

## REF-003 Payment methods

Identifiers must resemble the identifiers consumed by `BinancePublicClient` because it filters `tradeMethodIdentifiers`.

Fields: identifier, display name, enabled, fiat compatibility.

## REF-004 Price tick rules

Per asset/fiat pair tick and amount precision.

## REF-005 Order limits

Pair/payment-specific default min/max ranges used when generating ads.

## REF-006 Seed fixtures

A canonical JOD/USDT dataset for deterministic contract tests.

---

# 3. Simulated identities and merchants

## ID-001 Bot test user

Single primary account representing the bot/operator.

## ID-002 Merchant identity

Merchant id/no, nickname, type, creation age, verification status.

## ID-003 Merchant 30-day metrics

Completion rate, order count, average release time; values deliberately map to fields parsed by the existing bot.

## ID-004 Merchant payment methods

Which methods each merchant supports.

## ID-005 Merchant balances

Asset/fiat inventory relevant to whether the merchant can actually fill an ad.

## ID-006 Merchant behavior profile assignment

Persistent profile selected deterministically from the simulation seed.

## ID-007 Reliable fast merchant profile

High completion, short response/release delays.

## ID-008 Reliable slow merchant profile

Completes but approaches timeouts.

## ID-009 Canceller profile

Cancels with configured probability before payment.

## ID-010 Ghost profile

Stops responding and forces expiry/manual handling.

## ID-011 Payment-mismatch profile

Can produce wrong amount/name/reference through simulator payment events.

## ID-012 Dispute-prone profile

Escalates selected orders into dispute state.

## ID-013 Volatile-ad merchant

Frequently changes price/availability or removes ads.

## ID-014 Merchant availability schedule

Optional periods online/offline so behavior changes by simulated time.

## ID-015 Merchant metrics evolution

Completed/cancelled simulated orders update metrics rather than leaving merchant scores forever static.

---

# 4. Market-price engine

## MKT-001 Pair reference price

Persistent reference price for USDT/JOD.

## MKT-002 Price tick

Deterministic movement model with configured drift/volatility.

## MKT-003 Spread regime

Normal, tight, wide, one-sided and shock regimes.

## MKT-004 Regime transition

Scheduled deterministic regime changes.

## MKT-005 Manual price override

Admin can set exact reference price for a scenario.

## MKT-006 Price shock

Inject N% jump in one tick to test the bot's anomaly rule.

## MKT-007 Stale market

Freeze updates while API remains available.

## MKT-008 Price history

Persist ticks for diagnosis and opportunity-duration measurement.

## MKT-009 Reproducible replay

Given seed/event sequence, price history is repeatable.

---

# 5. Advertisement domain

## ADS-001 Ad entity

Fields required by bot parsing: ad number, side, asset, fiat, price, available asset, min/max fiat, payment methods, merchant, status, timestamps.

## ADS-002 BUY ad semantics

Match the semantics expected by the bot and public P2P contract exactly; document with contract tests to prevent inversion.

## ADS-003 SELL ad semantics

Same requirement for sell-side meaning.

## ADS-004 Ad creation

Merchant creates an ad from profile, inventory and reference price.

## ADS-005 Available quantity

Cannot exceed unreserved merchant inventory.

## ADS-006 Min transaction amount

Validated against max and availability.

## ADS-007 Max transaction amount

Cannot imply more asset than available.

## ADS-008 Payment method list

At least one compatible method.

## ADS-009 Ad activation

Only active ads appear in public market.

## ADS-010 Ad pause

Paused ad remains persisted but cannot accept new orders.

## ADS-011 Ad deletion/closure

Existing open orders survive; new orders are rejected.

## ADS-012 Price update

New price affects future orders only; existing order stores price snapshot.

## ADS-013 Quantity reduction after fill

Order reservation immediately removes reserved quantity from publicly available amount.

## ADS-014 Quantity return after cancellation

Reservation is returned exactly once.

## ADS-015 Ad exhaustion

Zero fillable quantity automatically makes ad unavailable.

## ADS-016 Ad replenishment

Scenario can top up inventory and reactivate ads.

## ADS-017 Automatic repricing

Merchant profile can move price relative to reference/tick.

## ADS-018 Price race

Ad may change between bot scan and order submission; order API validates current ad and returns explicit changed-price result.

## ADS-019 Ad disappearance race

Selected ad can disappear before submission.

## ADS-020 Duplicate ads/merchant

Multiple ads by same merchant supported so bot filters are tested against realistic market data.

---

# 6. Public market API compatibility

The easiest integration path is to make the simulator serve the exact public endpoint shapes already consumed by `BinancePublicClient`, allowing `BINANCE_MGS_BASE` to point at the simulator without rewriting market logic.

## API-PUB-001 Version endpoint

`GET /bapi/c2c/v1/public/c2c/agent/check-version`

## API-PUB-002 Trade methods endpoint

`GET /bapi/c2c/v1/public/c2c/agent/trade-methods?fiat=JOD`

## API-PUB-003 Ad list endpoint

`GET /bapi/c2c/v1/public/c2c/agent/ad-list`

Supports the concrete parameters the bot currently sends:

- `fiat`
- `asset`
- `tradeType`
- `limit`
- repeated `tradeMethodIdentifiers`

## API-PUB-004 Response field fidelity

Emit fields the existing parser understands: `adNo`, `price`, `surplusAmount`, `minSingleTransAmount`, `maxSingleTransAmount`, trade methods and merchant metrics.

## API-PUB-005 Limit validation

1..20, matching current client expectations.

## API-PUB-006 Payment-method filtering

Repeated identifiers behave as documented by simulator contract.

## API-PUB-007 Empty market

Valid success response with zero ads.

## API-PUB-008 Malformed/fault mode

Admin fault scenario can intentionally produce a malformed response for parser-hardening tests.

## API-PUB-009 Latency mode

Per-endpoint deterministic latency injection.

## API-PUB-010 HTTP 429/5xx mode

Used to prove retry/backoff behavior.

---

# 7. P2P market browser UI

The UI must be realistic enough for human validation and optional browser E2E tests; it is not the bot's primary integration mechanism.

## UI-MKT-001 P2P market page shell

Asset/fiat, Buy/Sell tabs, filters, ad list, top navigation state.

## UI-MKT-002 Buy/Sell tabs

Switch changes query side without losing relevant filters.

## UI-MKT-003 Fiat selector

JOD default.

## UI-MKT-004 Asset selector

USDT default.

## UI-MKT-005 Amount filter

Shows only ads whose min/max can accept entered fiat amount.

## UI-MKT-006 Payment-method filter

One or more identifiers.

## UI-MKT-007 Merchant filter/search

Search nickname/id for debugging.

## UI-MKT-008 Price column

Correct precision and direction semantics.

## UI-MKT-009 Available column

Reflect reservations in realtime.

## UI-MKT-010 Limits column

Min-max fiat display.

## UI-MKT-011 Payment method badges

Only actual methods for the ad.

## UI-MKT-012 Merchant statistics

Completion rate/order count/release time.

## UI-MKT-013 Action button

Buy/Sell action consistent with current side.

## UI-MKT-014 Pagination/refresh

Stable ordering under price updates.

## UI-MKT-015 Live updates

Rows update after market ticks without full page reload.

## UI-MKT-016 Ad removed state

A disappearing ad is removed cleanly; open order pages remain valid.

## UI-MKT-017 Empty state

Explicit no-ad message.

## UI-MKT-018 API error state

Distinguish loading, empty, error and stale data.

## UI-MKT-019 Mobile layout

Useful but secondary; page remains operable at phone width.

---

# 8. Order creation

## ORD-001 Order entity

Order number, ad snapshot, buyer, seller, side, asset amount, fiat amount, unit price, payment method, status, deadlines, behavior profile, timestamps.

## ORD-002 Unique order number

Deterministic format optional; uniqueness enforced at DB level.

## ORD-003 Order price snapshot

Price immutable after order creation.

## ORD-004 Amount snapshot

Asset and fiat totals immutable except explicit correction scenarios, which produce separate events rather than silently mutating terms.

## ORD-005 Validate active ad

Reject paused/closed/exhausted ad.

## ORD-006 Validate amount against min

## ORD-007 Validate amount against max

## ORD-008 Validate amount against availability

## ORD-009 Validate payment method

Selected method must belong to ad.

## ORD-010 Reserve seller asset

Atomic with order creation.

## ORD-011 Reserve buyer capacity when model requires it

Avoid oversubscription in simulated account balances.

## ORD-012 Order payment deadline

Created from simulation clock and configured timeout.

## ORD-013 Counterparty profile snapshot

Assignment stored on order so a restart does not change behavior.

## ORD-014 Idempotent create

Same client idempotency key returns same order, never double-reserves.

## ORD-015 Concurrent fills

Two requests racing for last liquidity: only a valid quantity can succeed.

## ORD-016 Price-changed rejection

Optional expected-price value lets bot detect stale opportunity before locking order.

## ORD-017 Ad-gone rejection

Explicit code distinguishable from network error.

## ORD-018 Order-created event

Contains enough data for audit but no secrets.

---

# 9. Order state machine

Simulator states must be richer than the current paper shortcut because its purpose is to make every intermediate state observable.

## ORD-ST-001 Created
## ORD-ST-002 Awaiting payment
## ORD-ST-003 Payment initiated/placeholder called
## ORD-ST-004 Buyer marked paid
## ORD-ST-005 Payment evidence pending
## ORD-ST-006 Payment verified
## ORD-ST-007 Awaiting crypto release
## ORD-ST-008 Crypto released
## ORD-ST-009 Completed
## ORD-ST-010 Cancel requested
## ORD-ST-011 Cancelled
## ORD-ST-012 Expired
## ORD-ST-013 Dispute opened
## ORD-ST-014 Under review
## ORD-ST-015 Resolved buyer
## ORD-ST-016 Resolved seller
## ORD-ST-017 Manual intervention
## ORD-ST-018 Failed technical state

For every transition:

- define allowed source states,
- define actor allowed to trigger it,
- define required evidence,
- persist transition and side effects atomically,
- emit one domain event,
- make retry idempotent where appropriate.

---

# 10. Buying crypto flow

This flow represents the bot buying USDT from a P2P seller.

## BUY-001 Select seller ad
## BUY-002 Create buy order
## BUY-003 Display seller payment details
## BUY-004 Call `<send cash function here>` placeholder

Simulator implementation returns a controlled placeholder result such as success, delayed acknowledgment, timeout-before-success, timeout-after-success or failure. No real transfer occurs.

## BUY-005 Mark paid

Allowed only before deadline and after required placeholder state.

## BUY-006 Seller detects paid marker

Counterparty scheduler sees event after configured delay.

## BUY-007 Seller behavior decides release/dispute/ghost

## BUY-008 Seller release

Moves reserved simulated USDT to bot balance atomically.

## BUY-009 Completion

Final balances/order metrics updated.

## BUY-010 Buyer cancellation before payment

Returns reservations.

## BUY-011 Cancellation after marked paid

Blocked or routed to manual/dispute according to simulator rule.

## BUY-012 Payment timeout

Expires order and releases reservations exactly once.

## BUY-013 Seller slow release

Order remains open and observable.

## BUY-014 Seller non-release

Transitions into timeout/manual/dispute scenario.

## BUY-015 Duplicate mark-paid request

Idempotent.

## BUY-016 Lost mark-paid response

Server may succeed but client sees timeout; retry must recover current state.

---

# 11. Selling crypto flow

This flow represents the bot selling USDT to a buyer.

## SELL-001 Select buyer ad
## SELL-002 Create sell order
## SELL-003 Reserve bot USDT
## SELL-004 Buyer counterparty starts payment behavior
## SELL-005 Buyer marks paid
## SELL-006 Simulator emits payment evidence
## SELL-007 Call `<verify cash received function here>` placeholder

Returns controlled verification states; it never touches a real bank.

## SELL-008 Verification success

Only verified result enables simulated release.

## SELL-009 Verification pending

Order stays open.

## SELL-010 Verification mismatch

Manual review/dispute; never auto-release.

## SELL-011 Release simulated USDT

Atomic asset movement from reserved balance to counterparty.

## SELL-012 Complete sell order

Credit simulated fiat balance if configured to represent bank result.

## SELL-013 Buyer falsely marks paid

No payment evidence; order does not release.

## SELL-014 Wrong amount

No release.

## SELL-015 Wrong sender/name/reference

Scenario-dependent manual review.

## SELL-016 Duplicate payment evidence

Must not create double credit or double release.

## SELL-017 Buyer payment after order expiry

Explicit late-payment/manual-review scenario.

## SELL-018 Release request retry

Idempotent; asset moves once.

---

# 12. Payment placeholder subsystem

The user requested banking be treated as complete externally; therefore simulator only provides stable seams.

## PAY-001 Send-cash request object

Order number, amount, currency, recipient details, idempotency key.

## PAY-002 Send-cash result object

`SUCCESS`, `PENDING`, `FAILED`, `UNKNOWN_AFTER_TIMEOUT`.

## PAY-003 Verify-cash request object

Expected amount/currency/counterparty/time window/reference.

## PAY-004 Verify-cash result object

`VERIFIED`, `WAITING`, `MISMATCH`, `AMBIGUOUS`.

## PAY-005 Successful outgoing payment scenario
## PAY-006 Failed outgoing payment scenario
## PAY-007 Unknown-after-timeout outgoing scenario
## PAY-008 Delayed payment scenario
## PAY-009 Correct incoming payment scenario
## PAY-010 Missing incoming payment
## PAY-011 Wrong amount
## PAY-012 Wrong currency
## PAY-013 Wrong counterparty
## PAY-014 Duplicate payment record
## PAY-015 Pending/not-final payment
## PAY-016 Late payment
## PAY-017 Payment evidence persistence
## PAY-018 Payment idempotency

Current `MockPaymentEnvironment` can seed behavior ideas, but the simulator implementation must be persistent, order-linked and restart-safe instead of relying on in-memory lists.

---

# 13. Balances, reservations and ledger

A simulator that only changes order status without accounting cannot expose double-spend bugs.

## BAL-001 Bot fiat balance
## BAL-002 Bot asset balance
## BAL-003 Merchant fiat balance where relevant
## BAL-004 Merchant asset balance
## BAL-005 Available balance
## BAL-006 Reserved balance
## BAL-007 Reservation record
## BAL-008 Reserve on order create
## BAL-009 Release reservation on cancel/expire
## BAL-010 Consume reservation on completion
## BAL-011 Asset transfer ledger entry
## BAL-012 Fiat simulation ledger entry
## BAL-013 Immutable ledger id
## BAL-014 No negative available balance invariant
## BAL-015 No reservation larger than source balance
## BAL-016 Sum of available + reserved = owned balance invariant
## BAL-017 Exactly-once settlement
## BAL-018 Rebuild balance from ledger test
## BAL-019 Concurrent order reservation test
## BAL-020 Restart between reservation and next order transition

---

# 14. Counterparty behavior engine

## CP-001 Behavior definition

Feature-specific probabilities/delays/actions, persisted by profile version.

## CP-002 Response delay
## CP-003 Payment delay
## CP-004 Release delay
## CP-005 Cancellation probability
## CP-006 Dispute probability
## CP-007 False-paid probability
## CP-008 Wrong-payment probability
## CP-009 Ghost probability
## CP-010 Ad repricing frequency
## CP-011 Ad withdrawal frequency
## CP-012 Maximum concurrent orders
## CP-013 Balance depletion behavior
## CP-014 Behavior event scheduling
## CP-015 Deterministic decision record

Every randomized decision records the sampled decision so replay does not depend on resampling.

---

# 15. Order details UI

## UI-ORD-001 Order header/status
## UI-ORD-002 Order number
## UI-ORD-003 Asset amount
## UI-ORD-004 Fiat total
## UI-ORD-005 Locked price
## UI-ORD-006 Counterparty identity/stats
## UI-ORD-007 Payment method/details
## UI-ORD-008 Countdown timer from simulation clock
## UI-ORD-009 Send-cash placeholder action state
## UI-ORD-010 Mark-paid button
## UI-ORD-011 Verify-cash placeholder state
## UI-ORD-012 Release action in simulated sell flow
## UI-ORD-013 Cancel action
## UI-ORD-014 Dispute action
## UI-ORD-015 Timeline/history
## UI-ORD-016 Error/retry state
## UI-ORD-017 Reconnect after page refresh
## UI-ORD-018 Terminal completed/cancelled/expired screen

---

# 16. Chat simulation

Chat is not required for the first bot API integration, but it matters for realistic P2P manual fallback testing.

## CHAT-001 Order-scoped thread
## CHAT-002 Human user message
## CHAT-003 Counterparty canned/deterministic reply
## CHAT-004 Delayed reply
## CHAT-005 System messages for payment/release/cancel
## CHAT-006 Message timestamps from simulation clock
## CHAT-007 Persisted history
## CHAT-008 Realtime delivery
## CHAT-009 Duplicate-send idempotency
## CHAT-010 Chat unavailable fault

No generic social/messaging platform features.

---

# 17. Dispute and manual-review simulation

## DSP-001 Open dispute
## DSP-002 Dispute reason
## DSP-003 Evidence metadata
## DSP-004 Freeze normal completion transitions
## DSP-005 Admin resolve for buyer
## DSP-006 Admin resolve for seller
## DSP-007 Reservation settlement after resolution
## DSP-008 Dispute timeout
## DSP-009 Event/audit trail
## DSP-010 Bot-visible manual-review state

---

# 18. Notifications and realtime events

## RT-001 Order status event
## RT-002 Market ad changed event
## RT-003 Payment marker event
## RT-004 Payment verified/mismatch event
## RT-005 Release event
## RT-006 Expiry event
## RT-007 Dispute event
## RT-008 Reconnect with last-event cursor
## RT-009 Duplicate event tolerance
## RT-010 UI fallback polling if realtime channel fails

Only add realtime infrastructure needed by these concrete events.

---

# 19. Authenticated/read API compatibility for bot tests

The existing `BinanceAuthClient` is read-only. Simulator can mirror those shapes for integration testing without claiming they are live Binance write APIs.

## API-AUTH-001 Test API key fixture
## API-AUTH-002 Signature verification mode optional

Useful for testing the bot's HMAC code; can also expose a no-auth local mode for frontend development.

## API-AUTH-003 Personal order history

Mirror `/sapi/v1/c2c/orderMatch/listUserOrderHistory` response fields used by repository sync.

## API-AUTH-004 User order summary

Mirror `/sapi/v1/c2c/orderMatch/getUserOrderSummary`.

## API-AUTH-005 Agent detail read fixture

Mirror detail shape for simulated orders when useful.

## API-AUTH-006 Available ad categories fixture

Allows capability-probe tests.

## API-AUTH-007 Invalid signature
## API-AUTH-008 Expired timestamp
## API-AUTH-009 recvWindow failure
## API-AUTH-010 Invalid API key

---

# 20. Simulator execution API for the bot

Do **not** invent a fake Binance production endpoint and later confuse it with official support. Use an explicitly simulator-owned execution API.

Proposed namespace:

```text
POST /sim/api/v1/orders
GET  /sim/api/v1/orders/{order_no}
POST /sim/api/v1/orders/{order_no}/mark-paid
POST /sim/api/v1/orders/{order_no}/cancel
POST /sim/api/v1/orders/{order_no}/release
POST /sim/api/v1/orders/{order_no}/dispute
```

## EXEC-001 Create order
## EXEC-002 Read order
## EXEC-003 Mark paid
## EXEC-004 Cancel
## EXEC-005 Release
## EXEC-006 Open dispute
## EXEC-007 Idempotency header
## EXEC-008 Explicit error codes
## EXEC-009 Current-state response on duplicate action
## EXEC-010 Server-side event ids

When this feature is implemented in the bot, create a **specific execution seam** because the bot genuinely needs two implementations: simulator now and any legitimate official execution integration later. Do not create a generic all-purpose exchange framework.

---

# 21. Bot integration features

## BOT-INT-001 Simulator market mode

Configuration points `BINANCE_MGS_BASE` to simulator public API. Existing parsing/analysis code should work unchanged.

## BOT-INT-002 Simulator execution mode

New explicit simulator execution client.

## BOT-INT-003 Full buy lifecycle orchestration

Bot opportunity -> risk -> simulator create order -> `<send cash function here>` -> mark paid -> wait for asset -> inventory update.

## BOT-INT-004 Full sell lifecycle orchestration

Bot opportunity/ad strategy -> simulator order -> wait payment -> `<verify cash received function here>` -> simulator release -> completion.

## BOT-INT-005 Durable active-trade record

Current `PaperTrade` jumps through all states in one function. Full simulator integration requires a persisted active trade whose state advances across multiple worker cycles.

## BOT-INT-006 Resume after restart

Bot queries persisted active trades/orders and continues from safe current state.

## BOT-INT-007 External order reconciliation

If simulator order state advances while bot is offline, bot reconciles rather than blindly replaying actions.

## BOT-INT-008 Duplicate create protection
## BOT-INT-009 Duplicate mark-paid protection
## BOT-INT-010 Duplicate release protection
## BOT-INT-011 Unknown-result recovery

After timeout, query order state before retrying irreversible-looking simulator action.

## BOT-INT-012 Stale ad recovery
## BOT-INT-013 Price-change recovery
## BOT-INT-014 Order-expired recovery
## BOT-INT-015 Counterparty cancellation recovery
## BOT-INT-016 Dispute/manual-review routing
## BOT-INT-017 Kill-switch behavior with open orders

Kill switch stops new trades but does not abandon already-open obligations; open-order handling policy must be explicit.

## BOT-INT-018 Inventory-aware next action
## BOT-INT-019 P&L from actual simulated fills, not scan quote
## BOT-INT-020 Event correlation across bot and simulator ids

---

# 22. Admin/scenario console

This is a testing control surface, not an exchange feature.

## ADM-001 View current simulation seed/time/status
## ADM-002 Pause/resume
## ADM-003 Advance time
## ADM-004 Change speed
## ADM-005 Set reference price
## ADM-006 Trigger price shock
## ADM-007 Freeze market
## ADM-008 Remove selected ad
## ADM-009 Reprice selected ad
## ADM-010 Force counterparty action
## ADM-011 Force payment success
## ADM-012 Force payment mismatch
## ADM-013 Force order expiry
## ADM-014 Force dispute
## ADM-015 Enable endpoint latency fault
## ADM-016 Enable HTTP failure fault
## ADM-017 Enable lost-response fault
## ADM-018 Restart-recovery scenario marker
## ADM-019 View scheduled events
## ADM-020 View immutable event timeline
## ADM-021 Export replay bundle
## ADM-022 Reset simulation

Every control emits an admin event so test runs can be reconstructed.

---

# 23. Fault-injection catalogue

Faults are attached only to concrete features where they make sense.

## FLT-001 Public ad API timeout before processing
## FLT-002 Public ad API 429
## FLT-003 Public ad API 500
## FLT-004 Stale ad response
## FLT-005 Malformed ad item
## FLT-006 Order-create timeout before commit
## FLT-007 Order-create timeout after commit
## FLT-008 Duplicate order-create request
## FLT-009 Mark-paid timeout after commit
## FLT-010 Release timeout after commit
## FLT-011 Realtime disconnect
## FLT-012 Duplicate realtime event
## FLT-013 Reordered realtime event
## FLT-014 Scheduler process restart
## FLT-015 API process restart with open order
## FLT-016 Database transient disconnect
## FLT-017 Concurrent final-liquidity race
## FLT-018 Counterparty disappears
## FLT-019 Payment evidence delayed past deadline
## FLT-020 Payment duplicate
## FLT-021 Price moves after scan
## FLT-022 Ad disappears after scan
## FLT-023 Kill switch activates mid-order

Each fault has a deterministic trigger: scenario config, exact next-call trigger, or named test fixture.

---

# 24. Persistence and migrations

## DB-001 Alembic migrations

Replace implicit `create_all` for simulator persistence with versioned schema migrations.

## DB-002 Simulation table
## DB-003 Merchant table
## DB-004 Merchant profile/version table
## DB-005 Payment method table
## DB-006 Market price tick table
## DB-007 Ad table
## DB-008 Order table
## DB-009 Order transition/event table
## DB-010 Balance table
## DB-011 Reservation table
## DB-012 Ledger entry table
## DB-013 Scheduled event table
## DB-014 Payment evidence table
## DB-015 Chat message table
## DB-016 Dispute table
## DB-017 Fault configuration table
## DB-018 Idempotency table
## DB-019 Admin action table
## DB-020 Useful indexes based on actual query paths

Do not add repository classes per table by habit; persistence methods belong to feature transaction boundaries.

---

# 25. Observability

## OBS-001 Structured log with simulation id
## OBS-002 Correlation id per order
## OBS-003 Bot trade id correlation
## OBS-004 Domain event timeline
## OBS-005 Order transition metric
## OBS-006 Active order count
## OBS-007 Completion/cancel/expire/dispute rates
## OBS-008 Counterparty delay metrics
## OBS-009 API error/latency metrics
## OBS-010 Scheduler lag
## OBS-011 Reservation imbalance alarm
## OBS-012 Ledger/balance reconciliation alarm
## OBS-013 Replay bundle on failed E2E test

---

# 26. Simulator security and isolation

Even fake environments should avoid accidental confusion with production.

## SEC-001 Simulator-only banner in UI
## SEC-002 Distinct port/base URL
## SEC-003 Refuse known production Binance host as simulator target
## SEC-004 No production secrets required
## SEC-005 Local test API keys clearly fake
## SEC-006 Admin controls disabled unless simulator mode
## SEC-007 CORS limited to simulator frontend in normal dev configuration
## SEC-008 Input validation on all state-changing endpoints
## SEC-009 Rate-limit simulation separated from real security rate limiting
## SEC-010 Logs redact any future secret-like fields

---

# 27. Testing strategy

## TST-001 Domain transition unit tests
## TST-002 Ad limits/property tests
## TST-003 Reservation atomicity tests
## TST-004 Ledger invariants
## TST-005 Public API contract tests using existing bot parser
## TST-006 Auth read API contract tests using existing bot client
## TST-007 Simulator execution API tests
## TST-008 Deterministic seed tests
## TST-009 Virtual clock tests
## TST-010 Scheduler exactly-once claim tests
## TST-011 Restart recovery tests
## TST-012 Concurrent order-create tests
## TST-013 Lost-response idempotency tests
## TST-014 Counterparty behavior profile tests
## TST-015 Buy lifecycle E2E
## TST-016 Sell lifecycle E2E
## TST-017 Expiry E2E
## TST-018 Cancellation E2E
## TST-019 Dispute E2E
## TST-020 False-paid E2E
## TST-021 Wrong-payment E2E
## TST-022 Ad-disappears-after-scan E2E
## TST-023 Price-changes-after-scan E2E
## TST-024 Kill-switch-mid-order E2E
## TST-025 Bot process restart E2E
## TST-026 Simulator process restart E2E
## TST-027 Database disconnect recovery test
## TST-028 1,000 sequential orders soak test
## TST-029 Concurrent-order soak test
## TST-030 24h accelerated simulation test
## TST-031 Browser market-page E2E
## TST-032 Browser order-page E2E
## TST-033 Admin fault-control E2E
## TST-034 Full bot+simulator test with zero real external services

---

# 28. CI and deployment

## DEP-001 Simulator backend test job
## DEP-002 Simulator frontend type/lint/test job
## DEP-003 Bot/simulator contract test job
## DEP-004 Full E2E Docker Compose job
## DEP-005 PostgreSQL integration job
## DEP-006 Determinism/replay job
## DEP-007 Docker image for simulator backend
## DEP-008 Docker image for simulator frontend
## DEP-009 Compose profile `simulator`
## DEP-010 Health/readiness endpoints
## DEP-011 Clean seeded startup command
## DEP-012 Named scenario startup command

---

# 29. Implementation order

The order below minimizes fake scaffolding and delivers complete vertical behavior early.

### Milestone A — deterministic core

1. SIM-001 simulation instance
2. SIM-002 random source
3. SIM-003 virtual clock
4. REF-001..006 reference data
5. ID-001..006 identities/profile assignment
6. MKT-001..009 price engine

**Exit:** deterministic JOD/USDT world exists and can be replayed.

### Milestone B — real market surface

7. ADS-001..020 advertisement domain
8. API-PUB-001..010 public compatibility
9. UI-MKT-001..019 market UI

**Exit:** existing bot scanner can point at simulator and see a realistic changing market; human can browse same market.

### Milestone C — accounting-correct orders

10. BAL-001..020 balances/reservations/ledger
11. ORD-001..018 order creation
12. ORD-ST-001..018 persistent state machine
13. SIM-004 scheduler

**Exit:** orders can be opened/cancelled/expired without corrupting inventory.

### Milestone D — complete buy flow

14. PAY-001..008 outgoing placeholder states
15. BUY-001..016
16. UI-ORD relevant buy controls
17. counterparty seller behaviors

**Exit:** bot can buy simulated USDT through a multi-step order, including delays/timeouts/retries.

### Milestone E — complete sell flow

18. PAY-009..018 incoming verification states
19. SELL-001..018
20. remaining UI-ORD controls
21. buyer counterparty behaviors

**Exit:** bot can sell simulated USDT and only release after controlled verification result.

### Milestone F — realism and recovery

22. RT-001..010 realtime
23. CHAT-001..010
24. DSP-001..010 disputes
25. FLT-001..023 fault injection
26. persistence/restart hardening

**Exit:** realistic adverse flows and restart recovery work.

### Milestone G — bot full-loop integration

27. EXEC-001..010 simulator execution API
28. BOT-INT-001..020 durable bot orchestration
29. authenticated read compatibility
30. reconciliation and P&L against simulated actual fills

**Exit:** one bot process can run end-to-end against simulator with no manual state edits.

### Milestone H — operator/testing surface

31. ADM-001..022 admin console
32. OBS-001..013 observability
33. SEC-001..010 isolation
34. TST full suite
35. DEP CI/deployment

**Exit:** simulator is a repeatable training/chaos environment rather than a demo.

---

# 30. Definition of production-complete simulator

The simulator is complete only when all of the following are true:

1. The existing public scanner can use the simulator by changing base URL only.
2. Market prices, liquidity and merchant behavior are deterministic by seed but nontrivial.
3. Orders consume and return liquidity correctly under cancellation, expiry and completion.
4. Balances/reservations/ledger remain consistent under concurrency and restart.
5. Buy and sell flows require multiple asynchronous state changes; no instant paper shortcut.
6. Payment actions are placeholders with realistic success/failure/unknown states.
7. Selling cannot release simulated asset when verification is missing/mismatched.
8. Duplicate requests and lost responses cannot duplicate orders, payment markers, credits or releases.
9. Bot and simulator can both restart in every important open-order state and recover safely.
10. Price changes/ad disappearance after scan are tested.
11. Counterparty cancellation, ghosting, delays, false-paid, mismatch and disputes are tested.
12. Admin can reproduce a failed run from seed/config/event timeline.
13. At least one accelerated long soak run completes with zero balance/reconciliation invariant failures.
14. Browser UI displays the same state the API exposes.
15. Full bot+simulator E2E runs without Binance credentials, bank access, or real funds.

## Feature expansion rule

The IDs above are not a cap. During implementation, if one item contains multiple independent behaviors, split it into more leaf features **before coding** and apply `FEATURE_IMPLEMENTATION_PROTOCOL.md` separately to each leaf. If that produces hundreds or thousands of features, they are still handled one at a time rather than collapsed into generic code.