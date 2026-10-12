**English** · [Magyar](../hu/00-at-a-glance.md) · [↑ README](../../README.md)

# At a glance

## The system on one picture

```mermaid
flowchart TB
    P([Pedro<br/>business owner]) -->|upload PDF| CF[Cloudflare<br/>WAF + bot protection]
    CF --> EDGE

    subgraph VPS["Public VPS — relays only, never processes"]
        EDGE[edge app<br/>upload · webhooks · push]
        PORTAL[portal app<br/>owner + accountant UI]
        PDB[(portal DB<br/>masked projection)]
        PORTAL --- PDB
    end

    EDGE -->|Tailscale| NAS[(NAS<br/>encrypted storage)]
    NAS -->|LAN| PIPE

    subgraph PC["On-prem PC — the only place raw data is processed"]
        PIPE[ingress check] --> QR[QR / barcode<br/>tax-authority oracle]
        QR --> T2[Tier 2: schema + heuristics<br/>header + line items]
        T2 -.only if unsure.-> T3[Tier 3: local LLM]
        T2 --> GATE{per-field<br/>identity gate}
        T3 --> GATE
        GATE -->|verified| AUTO[auto-approve]
        GATE -->|not verified| DESK[human review desk]
        SOT[(processing DB<br/>source of truth)]
    end

    AUTO --> EXP[export + status]
    DESK --> EXP
    EXP -->|masked status| PDB
    PORTAL --> M([Maria<br/>accountant])
```

## Fourteen decisions that define it

| # | decision | why | price paid |
|---|---|---|---|
| 1 | **No cloud.** Raw invoices are processed only on an on-prem PC; the public VPS relays and shows status. | Data sovereignty is the product promise to small businesses and accountants. | Three machines, encrypted links, local OCR/LLM, a single on-prem processing machine — and, on the public leg, Cloudflare reads uploads in transit (TLS termination for its firewall). |
| 2 | **The tax-authority QR code is the oracle.** Portuguese invoices carry a signed QR with the header values; the visual read is a cross-check, not the source. | A machine-verifiable ground truth beats any confidence score a model reports about itself. | Invoices without a QR (foreign, older) have no oracle — exactly the ones that need help most. |
| 3 | **Tiered extraction:** QR → schema/heuristics → local LLM only as the last resort. | Cheap and deterministic first; the slow model only where needed. | Three code paths to keep consistent. |
| 4 | **Schemas as data.** A master YAML per country + delta YAMLs per invoicing software, auto-selected by the software's certificate number. | A new vendor layout is a YAML file, not a code change. | Coverage grows one software at a time. |
| 5 | **Precision first: the system never guesses.** A wrong line is worse than a missing one. | A missing value is caught in review; a confidently wrong one slips through to the accountant. | Lower automation rate — on purpose. |
| 6 | **Per-field identity gate**, strict at start, loosened only on measured evidence. | Trust is the asset; the gate is where trust is enforced. | For the pilot, automatic approval was switched off in code — every invoice went to review. |
| 7 | **Two apps on the public server:** a thin edge (uploads, webhooks, push) and the portal. | A compromised edge must not reach client data logic. | Two deployables, two dependency sets. |
| 8 | **Three databases = three nodes, not three copies.** The source of truth physically lives on the PC; the public side holds a masked projection. | The public server can be lost without losing — or leaking — the truth. | A synchronisation bridge that had to be designed explicitly. |
| 9 | **Layered links:** Cloudflare in front of the VPS, Tailscale VPS↔NAS, LAN NAS↔PC. A separate WireGuard layer was removed as redundant. | Each hop has one job; nothing on the processing site is reachable from the internet — an external scan (Sep 2026, from the VPS) found zero open TCP ports; the VPS exposed only web and SSH. | An outage of any layer stops the flow — documented fallback: SSH pull. |
| 10 | **The owner pays, the accountant does not.** The accountant is the channel: winning one brings her whole client book. | Revenue = accountants × clients per accountant × invoices × price. No commission either: the accountant is her client's trusted adviser — paying her to recommend us would be a conflict of interest. | Two user groups, two interfaces, an invitation flow between them. |
| 11 | **Pricing: €39/month + graduated per-invoice usage** instead of fixed packages. | Fixed packages created a credit-hoarding trap: unused credits made clients cancel. | Less predictable revenue. |
| 12 | **PII gate — also towards the AI that builds the system.** Client invoice content never reaches an LLM, not even the development agents — and none ever did: there was no live client data, and the development corpus was voluntarily shared public samples. From July 2026 a pre-tool gate enforced it. | The no-cloud promise has to hold for the builder too. | Debugging and schema training on masked data only. |
| 13 | **The money path is split by responsibility:** Stripe only collects payment; every billable event goes into an append-only ledger in our own database; at month end the ledger is aggregated into a CSV for a local invoicing program (ClearAdmin) that issues the legal invoice; payouts to a Wise EUR account. Reverse charge only for an EU VAT number verified in VIES. *Built up to the CSV; the invoicing round trip stayed a design.* | The ledger is the auditable source of truth — a human-review approval or a rejection changes what the client owes, and that cannot live inside a payment provider. | Four systems to reconcile, and a cross-border VAT rule to enforce in code. |
| 14 | **The pipeline bridge is a folder contract, not an API.** The public server drops files on the NAS; a watcher on the PC picks them up; status goes back as a push. Nothing ever calls the PC from outside. | The processing machine needs no open port and no public endpoint; each failure mode has a defined outcome. | Polling latency and marker-file bookkeeping instead of a request/response call. |

Each row is written out as a full decision record in [Decision records](adr.md).

## Four stories worth asking about

- **The bit-exact staircase** — how a 1,482-line task was cut down without changing a single output. → [Platform](04b-platform.md#measured-then-repaired-step-by-step)
- **The 17-day silent backup failure** — 412 failure pings that nobody received. → [Infrastructure](04-infrastructure.md#backup-and-disaster-recovery)
- **The false zero** — a port scan that reported "clean" for the wrong reason. → [Infrastructure](04-infrastructure.md#isolation--stated-then-measured)
- **The number that measured the wrong thing** — line-item rates taken on the lab extractor, not production. → [Metrics](08-metrics.md#the-measurement-lessons)

## Where the effort went

Commit counts per area are a rough measure (one commit can touch several areas):

| area | commits |
|---|---|
| Platform: API, services, databases, background tasks, public server | ~580 |
| Parsing engine + measurement lab | ~270 |
| Tests and QA | ~270 |
| Interfaces: owner, accountant, operator, mobile | ~230 |
| Market, pricing, legal, landing pages | ~70 *(most of this work lives in design notes, not commits)* |
