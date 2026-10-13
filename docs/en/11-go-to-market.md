**English** · [Magyar](../hu/11-go-to-market.md) · [↑ README](../../README.md)

# Go-to-market and pricing

> **In one sentence:** pricing moved from packages to a graduated meter, and selling was set up as a
> measurement machine with thresholds fixed in advance — which never received enough data to decide.
>
> *Why the value thesis moved, and what the product was for, is in [The problem and the market](01-problem-and-market.md).*

## Pricing — from packages to a graduated meter

**The trap.** The first model sold fixed packages (€175 / €495 / €1,500 per month for 100 / 300 /
1,000 invoices). A pricing simulation (March 2026, before any client existed) showed the trap: clients
rarely use exactly their allowance, credits pile up, and a client sitting on unused credits asks
"why pay this month?" — a built-in reason to cancel. *The product would have worked against itself.*

**Four models were compared:** fixed packages · pure usage · hybrid with a chosen band · hybrid
with automatic graduated bands. **Chosen: €39 platform fee + graduated usage** — 1–60 invoices
€1.75, 61–120 €1.65, 121–300 €1.55, 301+ €1.45. The price falls on its own as volume grows; nothing
is pre-paid, nothing is wasted. €49 was the calculated optimum; €39 was shown as the launch price.

**The later benchmark** compared per-document prices: pure extraction tools charge a fraction of
ours. Conclusion: do not compete on extraction price — **sell the human-verified result**, not the
reading. A banded monthly package was the next idea; it stayed open.

## The accountant × owner combination

- **Revenue = accountants × clients per accountant × invoices per client × price.** The lever is
  the first two: win one accountant, invite her whole book in bulk. The invoice count is an
  output, not a lever.
- **Near-zero acquisition cost** through the accountant channel — the route the incumbents also took.
- **The accountant as co-provider:** she stands between the owner and the authorities; we are
  infrastructure for both. She uses it free; only the owner pays.

## Unit economics — what had to be true

- **Exception-based review, not full review:** the model auto-accepts what it can verify; people
  handle the rest. Below ~200 invoices a month, hybrid human-plus-machine wins; above ~500,
  automation does. Our small clients (12–70 a month) sit in the hybrid zone.
- **North-star metric from day one: human minutes per invoice over time.** If it falls with
  volume, the model scales; if it stays flat, the margin is labour margin.
- **Hardware as a fixed cost:** no cloud means the processing machine amortises with volume. A
  GPU machine for local vision-language models was planned — financed from revenue, not before it.
- **A second market as an option:** the US has no e-invoice system, so extraction keeps its full
  value there — but the no-cloud differentiator does not travel. "Mutate later", not a pivot.

## Go-to-market as a measurement machine

- A **channel map** — cold e-mail, follow-up, forums, accounting-software partners, the
  professional body, content, paid — opened in **waves with exit gates**, not dates: stay on one
  channel until it produces a payer or its reply rate is provably below 1 % after 150 contacts.
- **List building with a law of evidence:** a guessed domain cannot confirm itself — an independent
  signal is required (the company number on the page, the professional-register entry).
- **Census, not sampling;** a confidence interval on every rate; **decision thresholds written down
  before looking at the data;** a bounce gate before every send.
- Outcome: ~240 e-mails, no human reply — below the size at which the channel could fail cleanly.
  → [Post-mortem](12-post-mortem.md)

## The legal layer

Drafted for launch, the client-facing ones also in Portuguese: data processing agreement with an accountant
addendum, terms, privacy and cookie policies, acceptable use, consent management, account
deletion protocol, subprocessor list, retention summary, records of processing, two data
protection impact assessments (profiling; deletion and transfer), legitimate-interest assessments
(profiling; cold outreach), incident response plan, NDAs.

## Ideas worth keeping

1. **The missing-invoice list as the core,** predicted from the client's own history — it moves
   the accountant's surprise from after the month to during it.
2. **"The month arrives closed"** — a service definition, not a software feature.
3. **The accountant as the targeting mechanism** for an entry point that is invisible from outside.
4. **Graduated metering** instead of packages — no credit trap.
5. **A law of evidence for sales lists,** and decision thresholds fixed before the data.
