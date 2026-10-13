**English** · [Magyar](README.hu.md)

# Dat[AI]nsight — an invoice-processing platform, built and closed

**[Krisztián Pettner](https://github.com/krisztianpettner)** · systems architect · [LinkedIn](https://www.linkedin.com/in/krisztian-pettner/)

> A no-cloud document-processing service for Portuguese small businesses and their accountants.
> One person, about a year of work, 1,564 commits. The engine, the platform and the client
> interface were built and deployed, ready for a pilot; header extraction worked, line items did
> not reach the bar, and the pilot never got its first user. This repository is the record of
> **how it was designed and why** — not a product.

## In 30 seconds

**The idea.** A small-business owner (*Pedro*) uploads his supplier invoices. The system reads them,
checks them, and delivers them structured to his accountant (*Maria*), who closes the month.
Pedro pays (€39/month + per-invoice usage); Maria uses it free and brings her clients.
*Pedro and Maria are personas built from market research, not real people.*

**The hard constraints that shaped everything:**

| constraint | consequence in the architecture |
|---|---|
| **No cloud** — invoices are processed only on own hardware, no external AI | parsing, OCR and a local LLM run on an on-prem PC; the public server relays without storing invoices ([what crosses which boundary](docs/en/06-data-path.md#what-crosses-which-boundary)) |
| **Strict tenant isolation** — one client never sees another client's data | a single scope resolver behind every route; the public side holds a masked projection |
| **Trust over automation** — a wrong value reaching the accountant is unrecoverable | a per-field identity gate: auto-approve only what an independent source verifies, everything else to human review |
| **One person** | I designed the architecture; an AI agent team wrote the code to that design; I held the constraints, the gates, the review and the measurement |

**What it is made of:** a tiered PDF parsing engine anchored to the Portuguese tax-authority QR
code; an identity gate that routes each invoice to auto-approval or a human review desk; a
two-sided product with a complete client interface (owner + accountant); a three-machine pipeline
bridge (public server → NAS → on-prem PC) joined by encrypted links; and a money path from card
payment to an append-only ledger.

**How it ended.** The demand was real, but selling started late, through one channel: cold
e-mail to 127 accounting firms (~240 e-mails with follow-ups) brought no human reply. And invoice
**line items** — the part the accountant actually needs — stayed largely in human review. I closed
the project in October 2026. → [Post-mortem](docs/en/12-post-mortem.md)

## Verify one claim in two minutes

The identity gate — the part that decides which values may be trusted — runs standalone:

```bash
python -m venv .venv && .venv/bin/pip install pytest
PYTHONPATH=src .venv/bin/python -m pytest tests/parsing/identity -q
# 51 passed   (2026-10-12)
```

## The chapters

Short on time? Read [00](docs/en/00-at-a-glance.md) and [12](docs/en/12-post-mortem.md) — fifteen minutes.

| # | chapter | answers | code |
|---|---|---|---|
| 00 | [At a glance](docs/en/00-at-a-glance.md) | the whole system on one picture, and the fourteen decisions in one line each | |
| 01 | [The problem and the market](docs/en/01-problem-and-market.md) | why line items, not headers — and how the value thesis moved | |
| 02 | [Product and users](docs/en/02-product-and-users.md) | who pays, who brings the clients, how they are linked | |
| 03 | [The client interface](docs/en/03-client-interface.md) | what the owner and the accountant actually saw, screen by screen | |
| 04 | [Parsing engine](docs/en/04-parsing-engine.md) | how a PDF becomes structured data | [`src/parsing`](src/parsing), [`src/ingress`](src/ingress) |
| 05 | [Trust](docs/en/05-trust.md) | which values may be trusted, what the human reviewer sees, how accuracy was measured | [`src/parsing/identity`](src/parsing/identity) |
| 06 | [Data path](docs/en/06-data-path.md) | where an invoice travels across three machines, and how the bridge fails safely | [`src/dispatch_watcher.py`](src/dispatch_watcher.py) |
| 07 | [Security and isolation](docs/en/07-security-and-isolation.md) | tenant isolation, who can see what, privacy towards the AI builder, the perimeter scan | [`src/services/authz`](src/services/authz) |
| 08 | [Infrastructure and operations](docs/en/08-infrastructure.md) | the three nodes and four links, deployment, backup, monitoring | |
| 09 | [Platform](docs/en/09-platform.md) | the layering rule, and how drift was repaired step by step | |
| 10 | [Billing](docs/en/10-billing.md) | payment → ledger → legal invoice | [`src/services`](src/services) |
| 11 | [Go-to-market and pricing](docs/en/11-go-to-market.md) | pricing, unit economics, selling as a measurement machine | |
| 12 | [Post-mortem](docs/en/12-post-mortem.md) | why it failed, and what I would do differently | |
| 13 | [How I worked](docs/en/13-how-i-worked.md) | what I decided myself, and how I led an AI agent team | |
| A | [Decision records](docs/en/a-decision-records.md) | the fourteen decisions in full | |
| B | [Metrics](docs/en/b-metrics.md) | every number, with date and source | |
| C | [Glossary](docs/en/c-glossary.md) | the terms used here | |

The code in [`src/`](src/README.md) is a curated extract of about forty files, for reading, not running.

## The numbers

| | |
|---|---|
| Duration | Oct 2025 → Sep 2026; most of the work from March 2026 |
| Commits | 1,564 (peak: 320 in May 2026) |
| Python | ~249k lines, of which ~75k tests (3,690 test functions) |
| Frontend | ~28k lines — the client web app (40 screens), internal tools; plus a Flutter app and a Streamlit operator console |
| Runtime | 18 Docker services · 3 databases · 22 YAML extraction schemas |
| Design record | 70 architecture documents · 182 session logs · ~300 decision/lesson notes |

---

*Code in this repository was written by AI agents (Claude) to my design. The architecture is mine —
above all the pipeline bridge across three machines, from the public relay through the NAS
hand-over to on-prem processing and the masked status back. So are the constraints, the decisions
and their record.*

<sub>© 2026 Krisztián Pettner. Shared for review; all rights reserved.</sub>
