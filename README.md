**English** · [Magyar](README.hu.md)

# Dat[AI]nsight — an invoice-processing platform, built and closed

**[Krisztián Pettner](https://github.com/krisztianpettner)** · systems architect · [LinkedIn](https://www.linkedin.com/in/krisztian-pettner/)

> A no-cloud document-processing service for Portuguese small businesses and their accountants.
> One person, 6+ months of active work, 1,564 commits. The engine and the platform ran in pilot
> configuration; header extraction worked, line items did not reach the bar, and the business did
> not take off. This repository is the record of **how it was designed and why** — not a product.

## In 30 seconds

**The idea.** A small-business owner (*Pedro*) uploads his supplier invoices. The system reads them,
checks them, and delivers them structured to his accountant (*Maria*), who closes the month.
Pedro pays (€39/month + per-invoice usage); Maria uses it free and brings her clients.
*Pedro and Maria are personas built from market research, not real people.*

**The hard constraints that shaped everything:**

| constraint | consequence in the architecture |
|---|---|
| **No cloud** — invoices are processed only on own hardware, no external AI | parsing, OCR and a local LLM run on an on-prem PC; the public server relays without storing invoices ([what crosses which boundary](docs/en/03-data-path.md#what-crosses-which-boundary)) |
| **Strict tenant isolation** — one client never sees another client's data | a single scope resolver behind every route; the public side holds a masked projection |
| **Trust over automation** — a wrong value reaching the accountant is unrecoverable | a per-field identity gate: auto-approve only what an independent source verifies, everything else to human review |
| **One person** | I designed the architecture; an AI agent team wrote the code to that design; I held the constraints, the gates, the review and the measurement |

**What it is made of:** a tiered PDF parsing engine anchored to the Portuguese tax-authority QR
code; an identity gate that routes each invoice to auto-approval or a human review desk; a
two-sided product (owner + accountant); a three-machine pipeline bridge (public server → NAS →
on-prem PC) joined by encrypted links; and a money path from card payment to an append-only ledger.

**How it ended.** Invoice **line items** — the part the accountant actually needs — stayed largely
in human review. Cold outreach reached 127 accounting firms (~240 e-mails with follow-ups) and
brought no human reply. I closed the project in October 2026. → [Post-mortem](docs/en/09-post-mortem.md)

## Verify one claim in two minutes

The identity gate — the part that decides which values may be trusted — runs standalone:

```bash
python -m venv .venv && .venv/bin/pip install pytest
PYTHONPATH=src .venv/bin/python -m pytest tests/parsing/identity -q
# 51 passed   (2026-10-12)
```

## Reading paths

| time | read |
|---|---|
| **15 minutes** | this page → [At a glance](docs/en/00-at-a-glance.md) → [Post-mortem](docs/en/09-post-mortem.md) |
| **45 minutes** | + [Parsing engine](docs/en/02-parsing-engine.md), [Data path](docs/en/03-data-path.md), [Billing](docs/en/04c-billing.md), [Metrics](docs/en/08-metrics.md) |
| **deep dive** | [Decision records](docs/en/adr.md) → [Code map](src/README.md) → the tests |

Unfamiliar term? → [Glossary](docs/en/glossary.md)

## The numbers

| | |
|---|---|
| Duration | late 2025 → Sep 2026 — 6+ months of active work, with a summer break |
| Repository history | Oct 2025 → Sep 2026 |
| Commits | 1,564 (peak: 320 in May 2026) |
| Python | ~249k lines, of which ~75k tests (3,690 test functions) |
| Frontend | ~28k lines (React) — owner and accountant portal, internal tools; plus a Flutter app and a Streamlit operator console |
| Runtime | 18 Docker services · 3 databases · 22 YAML extraction schemas |
| Design record | 70 architecture documents · 182 session logs · ~300 decision/lesson notes |

## Where to look

| if you are wondering… | read |
|---|---|
| what this is, on one page | [At a glance](docs/en/00-at-a-glance.md) |
| why it failed and what I learned | [Post-mortem](docs/en/09-post-mortem.md) |
| how a PDF becomes trusted data | [Parsing engine](docs/en/02-parsing-engine.md) |
| where the data travels, who can see it, what crosses which boundary | [Data path](docs/en/03-data-path.md) |
| how the three machines and the links fit | [Infrastructure](docs/en/04-infrastructure.md) · [Platform](docs/en/04b-platform.md) |
| how money moved: payment → ledger → legal invoice | [Billing](docs/en/04c-billing.md) |
| who pays, who brings the clients, and why | [Two-sided product](docs/en/05-two-sided-product.md) |
| how the value thesis and pricing evolved | [Market and pricing](docs/en/06-market-and-pricing.md) |
| what I decided myself, and how I led an AI agent team | [How I worked](docs/en/07-how-i-worked.md) |
| every number, with date and source | [Metrics](docs/en/08-metrics.md) |
| the fourteen decisions in full | [Decision records](docs/en/adr.md) |
| the code behind the chapters | [Code map](src/README.md) — a curated extract, ~40 files |

---

*Code in this repository was written by AI agents (Claude) to my design. The architecture is mine —
above all the pipeline bridge across three machines, from the public relay through the NAS
hand-over to on-prem processing and the masked status back. So are the constraints, the decisions
and their record.*

<sub>© 2026 Krisztián Pettner. Shared for review; all rights reserved.</sub>
