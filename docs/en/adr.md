**English** · [Magyar](../hu/adr.md) · [↑ README](../../README.md) · [At a glance](00-at-a-glance.md)

# Architecture decision records

Fourteen decisions that shaped the system, in a fixed form: **context · decision · rejected
alternatives · consequences · status**. Numbers match [At a glance](00-at-a-glance.md).

---

### ADR-01 — No cloud processing

- **Context.** The customers are small businesses and their accountants; the data is their
  suppliers, prices and margins. Trust is the product.
- **Decision.** Raw invoices are processed only on hardware I own; no external AI service ever
  sees client data. A public server may relay and show status, never process.
- **Rejected.** Cloud OCR/LLM APIs (better accuracy, no hardware) — they would make the core promise false.
- **Consequences.** Three machines, tunnels, local OCR and a small local model; a single on-prem
  processing machine; fixed costs that only amortise with volume.
- **Status.** Held for the whole project. → [Infrastructure](04-infrastructure.md)

### ADR-02 — The tax-authority QR code is the oracle

- **Context.** A model's own confidence score cannot certify its output.
- **Decision.** For Portuguese invoices the signed QR payload is the source of truth for header
  values; the visual reading is a cross-check.
- **Rejected.** Trusting extraction confidence alone.
- **Consequences.** Machine-verifiable trust for ~79 % of the golden set; no oracle for invoices without a QR.
- **Status.** Held. → [Parsing engine](02-parsing-engine.md)

### ADR-03 — Tiered extraction, the local model last

- **Decision.** QR → schema and heuristics → table-extraction ladder → local LLM only if everything else is empty.
- **Rejected.** LLM-first extraction (slow on local hardware, unverifiable).
- **Consequences.** Several code paths to keep consistent; each output row records which method produced it.
- **Status.** Held.

### ADR-04 — Schemas as data

- **Decision.** A master YAML per country, a delta YAML per invoicing software, selected by the
  software certificate number in the QR, with the issuer's tax number as fallback.
- **Rejected.** Vendor logic in Python code.
- **Consequences.** A new layout is a YAML file; coverage grows one software at a time. A planned
  layout-fingerprint fallback was built but never wired in.
- **Status.** Held.

### ADR-05 — Precision first: never guess

- **Decision.** If a value cannot be read with certainty, it is not produced; the field goes to review.
- **Rejected.** Best-effort output with low-confidence flags.
- **Consequences.** A lower automation rate by design. A missing value is caught; a confident wrong value reaches the accountant.
- **Status.** Held.

### ADR-06 — A per-field confidence gate, strict first

- **Decision.** Each field is classified by how it can be verified (independent source /
  arithmetic / none) and banded green–amber–red; the document is as confident as its weakest
  critical field. For the pilot, automatic approval was switched off in code; loosening only on
  measured evidence, field by field.
- **Rejected.** A single document-level threshold.
- **Consequences.** The review desk carried all invoices during the pilot; the north-star became
  operator minutes per invoice.
- **Status.** Held; never loosened — the pilot did not produce the evidence.

### ADR-07 — Two apps on the public server

- **Decision.** A thin edge app (uploads, push, mail webhooks) and a portal app (users' data), separate dependencies.
- **Rejected.** One API app.
- **Consequences.** A compromised edge cannot reach client logic; two deployables.
- **Status.** Held. (The payment webhook ended up in the portal app, where its database lives — documented.)

### ADR-08 — Three databases as three nodes

- **Decision.** Edge DB and portal DB on the public server, the processing DB — the source of
  truth — on the PC; the public side holds a masked projection.
- **Rejected.** One shared database reachable from the public server.
- **Consequences.** The public server can be lost without losing or leaking the truth; a bridge
  had to be designed; a fix against the wrong database "succeeds" with zero rows.
- **Status.** Held.

### ADR-09 — Layered links, nothing on the processing site exposed

- **Decision.** Cloudflare in front of the public server, Tailscale between it and the NAS, LAN inside.
- **Removed.** A separate WireGuard tunnel — built first, then removed as redundant (Tailscale already is WireGuard).
- **Consequences.** Zero open TCP ports on the processing site, measured from outside (Sep 2026); any link failing stops the flow — fallback: SSH pull.
- **Status.** Held.

### ADR-10 — The owner pays, the accountant does not — and earns no commission

- **Decision.** The business owner is the only payer; the accountant uses the service free and
  invites her clients.
- **Rejected.** Charging accountants; paying accountants a referral commission.
- **Why no commission.** The accountant is her client's trusted adviser and the judge of our
  output; paying her to recommend us would be a conflict of interest — it would make the system unethical.
- **Consequences.** Two user groups, two interfaces, a one-way invitation flow with consent records.
- **Status.** Held.

### ADR-11 — Graduated usage pricing

- **Context.** Fixed packages created a credit-hoarding trap: unused credits led to cancellations.
- **Decision.** €39 platform fee + graduated per-invoice price (€1.75 → €1.45).
- **Rejected.** Fixed packages; pure usage; self-selected bands.
- **Consequences.** Fair to small clients, less predictable revenue; later benchmarking showed the
  per-document price only makes sense for a human-verified result.
- **Status.** Implemented; a banded monthly package stayed an open idea.

### ADR-12 — The PII gate applies to the builder too

- **Decision.** Client invoice content never reaches an LLM — including the AI agents developing
  the system. Debugging and schema training use character-identical pseudonymised data or value-free fingerprints.
- **Rejected.** "Just this once for debugging."
- **History.** No client invoice ever reached a model: there was no live client data, and the development corpus was voluntarily shared public samples. The gate was made mechanical (a pre-tool hook) in July 2026.
- **Consequences.** A pseudonymisation engine and a training routine on masked data; slower debugging.
- **Status.** Held.

### ADR-13 — The money path split by responsibility

- **Decision.** Stripe collects payment; an append-only ledger in our database decides what is
  owed; a monthly CSV feeds a local invoicing program for the legal invoice; payouts to a EUR account.
- **Rejected.** Stripe invoicing (the issuer is a Hungarian company); online invoicing services;
  Stripe's usage meter as the source of truth.
- **Consequences.** Billing truth stays auditable on our own database; four systems to reconcile; reverse
  charge enforced in code with VIES evidence.
- **Status.** Built up to the CSV; the invoicing round trip stayed a design. → [Billing](04c-billing.md)

### ADR-14 — The pipeline bridge is a folder contract, not an API

- **Context.** The processing machine must never be reachable from the internet, but uploads arrive on a public server.
- **Decision.** The public server streams each upload over SSH (inside Tailscale) into a per-client outbox folder on the NAS. A watcher on the PC picks files up, processes them, and pushes status back to the portal. Nothing ever calls the PC.
- **Rejected.** A queue or HTTP API exposed by the PC (an inbound endpoint into the processing site); processing on the public server.
- **Consequences.** No open port and no public endpoint on the processing site; each failure mode has a defined outcome — stability wait, marker files against double parsing, idempotent upsert after a crash, duplicate gate, best-effort status push, decision persisted before status. Cost: polling latency and marker-file bookkeeping.
- **Status.** Held. → [Data path](03-data-path.md#the-bridge--how-it-fails-safely)
