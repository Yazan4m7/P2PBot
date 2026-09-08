# Feature Implementation Protocol

This project is implemented **feature by feature**, not by creating a large generic framework first.

The purpose of this protocol is to prevent shallow components, placeholder abstractions, utility classes with no concrete owner, and broad refactors that accidentally weaken already-working behavior.

## Rule 1 — One feature is the unit of thought

When implementing a feature, consider only:

1. the user-visible behavior of that feature,
2. the domain state required by that feature,
3. the existing code that directly participates in that feature,
4. the exact integration points the feature must call,
5. the feature's failure/recovery behavior,
6. the tests required to prove the feature.

Do **not** opportunistically redesign unrelated modules while working on a feature.

## Rule 2 — Every feature gets a feature brief before code

For every leaf feature, write down:

- **Purpose** — what concrete behavior is being added.
- **Actor** — bot, simulated user, simulated counterparty, operator, or scheduler.
- **Trigger** — what starts it.
- **Inputs** — exact data required.
- **Outputs** — exact state/result produced.
- **Invariants** — things that must never become false.
- **State transitions** — only the states relevant to this feature.
- **Persistence** — tables/fields this feature owns or mutates.
- **API surface** — endpoints/methods this feature requires.
- **UI surface** — screen/control/state if the feature is visible.
- **External boundary** — Binance-like API, bank placeholder, timer, etc.
- **Failure cases** — network loss, timeout, stale data, duplicate request, restart, invalid input, race.
- **Recovery behavior** — what happens after each failure.
- **Idempotency key** — when the feature can be retried.
- **Observability** — events, logs, metrics that prove what happened.
- **Tests** — happy path, edge cases, failure cases, restart/concurrency where relevant.
- **Definition of done** — observable acceptance criteria.

No feature is complete because a class or endpoint merely exists.

## Rule 3 — No generic abstraction without demonstrated need

A shared abstraction is created only when at least one of these is true:

- two already-implemented features need the same invariant or protocol,
- an external boundary must have multiple implementations (for example real market vs simulator),
- testability requires a stable seam around nondeterministic behavior such as time or randomness,
- persistence/concurrency semantics require a common transaction boundary.

Otherwise keep the code feature-specific and close to the feature that owns it.

Examples:

- Good: `SimulationClock` because order expiry, merchant delay, price ticks and timeout tests all require controllable time.
- Good: an order persistence transaction because reservation + order creation must be atomic.
- Bad: `BaseService`, `GenericRepository`, `AbstractManager`, `CommonUtils`, or dozens of tiny UI atoms created before concrete features require them.

## Rule 4 — Complete vertical slices

A feature is implemented as a vertical slice when applicable:

`domain rule -> persistence -> service behavior -> API -> UI -> events -> tests`

Do not stop after only the database, only the API, or only the UI unless the feature brief explicitly says that is the complete scope.

## Rule 5 — Feature-local tests first

For each feature:

1. write/extend focused unit tests for its rules,
2. add service/repository tests for persistence and idempotency,
3. add API contract tests if it exposes HTTP behavior,
4. add UI/E2E tests if user interaction matters,
5. add restart/concurrency/chaos tests only when those failures are meaningful for that feature,
6. run the feature's focused test set,
7. run the full suite before commit.

A feature with only a happy-path test is not production complete.

## Rule 6 — Determinism in the simulator

Every stochastic simulator behavior must be reproducible from:

- scenario id,
- seed,
- simulated clock,
- recorded event sequence.

Tests must never depend on wall-clock waiting or uncontrolled randomness.

## Rule 7 — State belongs in persistent domain records

Anything needed to recover after a process restart must not exist only in Python memory or browser state.

Examples that must be persisted when implemented:

- open simulated orders,
- reserved asset/fiat,
- order deadlines,
- counterparty behavior assignment,
- scheduled scenario events,
- payment placeholder status,
- release status,
- dispute state,
- idempotency claims,
- market scenario configuration when reproducibility matters.

## Rule 8 — Atomicity is specified per feature

For every state-changing feature, explicitly identify what must commit together.

Examples:

- order creation + balance reservation,
- cancellation + reservation release,
- crypto release + asset movement + order state transition,
- completed order + final ledger movements,
- ad fill + available quantity reduction.

If these can be partially committed, the feature is not complete.

## Rule 9 — Failure injection is a feature requirement, not an afterthought

When the simulator feature models an external interaction, it must eventually support relevant failure variants such as:

- delay,
- timeout before response,
- timeout after server-side success,
- duplicate request,
- duplicate event,
- stale response,
- HTTP 429/5xx,
- disconnect/reconnect,
- process restart between state changes.

The exact variants are chosen from the feature's real failure model, not added generically everywhere.

## Rule 10 — Commit boundaries follow completed features

Prefer one commit per completed leaf feature or tightly coupled feature slice.

Each commit should answer:

- what behavior is now possible,
- what invariants are enforced,
- what failures are covered,
- what tests prove it.

Avoid commits named only `refactor`, `helpers`, `components`, or `cleanup` unless that work is independently necessary and verified.

## Working sequence for every feature

1. Read the master plan entry.
2. Inspect only the files directly relevant to the feature.
3. Write/update the feature brief if discoveries change requirements.
4. Implement the smallest complete vertical slice.
5. Test every specified behavior and failure mode.
6. Inspect the resulting diff specifically for accidental generic abstractions.
7. Run focused tests.
8. Run the full suite.
9. Commit.
10. Move to the next feature and repeat from a clean mental context.

This protocol applies even if the master feature inventory grows into hundreds or thousands of leaf features.