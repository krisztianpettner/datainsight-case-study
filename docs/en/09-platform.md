**English** · [Magyar](../hu/09-platform.md) · [↑ README](../../README.md)

# The platform

> **In one sentence:** a layered service platform around the engine — and a running fight to
> keep the layers honest while an AI team wrote the code at speed.

## The layering rule

```mermaid
flowchart LR
    R[route<br/>HTTP only] --> S[service<br/>business logic · transactions · integrations]
    S --> D[data access<br/>CRUD only]
    S --> X[external<br/>Stripe · mail · NAS · local LLM]
```

- **Routes** declare the endpoint, validate input, inject dependencies, call a service, raise 4xx.
- **Services** own the business decisions, the transactions, the retries and every external call.
- **Data access** does create/read/update/delete — nothing else.
- Dependencies are injected, not imported as globals, so a service can be tested without a server.

**Why it mattered more than usual:** AI agents write a working endpoint fastest by putting the
query straight into the route. Fast, and wrong — business rules end up scattered across 70 files.

## Measured, then repaired step by step

An architecture drift audit in May 2026 checked the code against the rule. Re-measured for this
record: **55 of 70 route files** still talk to the database directly — the drift was larger than
the audit's first estimate.

The response was a staircase, not a rewrite:

| step | what | status |
|---|---|---|
| 1–4 | preparatory moves, ending with the ingress check extracted into its own package | done |
| before launch | the billing retry loop taken out of the pipeline — billable events now go to a ledger service | done |
| 5a | baseline for the Portuguese pipeline: 10 reference invoices, all bit-exact, before touching anything | done |
| 5b | the 418-line persistence block moved from the task into its own service — the task shrank from 1,482 to 1,106 lines, outputs bit-exact | done |
| 6 | the remaining route-level drift | deferred until after launch |
| — | **new code:** every new route must follow the rule, with a devil's-advocate review at plan time and before commit | enforced |

The point is not the count; it is the order. Freeze the behaviour (bit-exact baseline), move one
block, prove nothing changed, commit — then the next.

## The surfaces

| surface | for | stack |
|---|---|---|
| client web app | Pedro (owner) and Maria (accountant) — 40 screens, see [The client interface](03-client-interface.md) | React 19, Vite |
| internal web app | schema creation and development tools | React 19, Vite, Tailwind, Vitest, Playwright |
| mobile app | Pedro — push notifications, status | Flutter, Firebase Cloud Messaging |
| operator console | the operator — KPIs, queues | Streamlit |

## Tests

3,690 test functions in total; the ~3,000 in the `tests/` tree are organised by layer — API, architecture, dispatch,
ingress, OCR, parsing, privacy, profiles, QR adapters, queues, routing, services, tasks — plus
integration tests that run in the full processing container. Unit tests run in a thin
development container; anything that needs Java (Tabula), OpenCV/Tesseract or the task queue runs
where those live.

## Designed vs built — honestly

| designed | built |
|---|---|
| request-ID middleware for tracing a request across logs | not built |
| a suite of architecture invariant tests | 2 tests (status casing, migration firewall) |
| "23 end-to-end browser tests" in an older status document | 2 Playwright specs in the repository |
| route layer free of direct database access | true for new code; 55 legacy route files deferred |
