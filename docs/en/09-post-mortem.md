**English** · [Magyar](../hu/09-post-mortem.md) · [↑ README](../../README.md)

# Post-mortem

> **In one sentence:** the need was real and header extraction worked — but I started selling
> too late, through a single untested channel, with a technical core that had not yet solved the hardest part.

## What happened

| when | what |
|---|---|
| Late 2025 – Mar 2026 | Engine and first platform: tiered parsing, schemas, validation rules. ~270 commits. |
| Apr – May 2026 | Platform build-out: two-sided portal, billing, deployment refactor, security. Peak: 320 commits in May. |
| May 2026 | First honest measurement of line items (on the lab extractor): **19 %** of measurable invoices fully reconciled. |
| Jun – Jul 2026 | Human-review desk, confidence gate, data isolation; outreach machinery built. |
| Jul – Aug 2026 | Pilot launch: cold outreach to accounting firms in Portugal. ~240 emails, **0 human replies**. |
| Aug 2026 | Second measurement on a larger golden set: **10.3 %** reconciled; on the clean subset, **57 %** of invoices yielded no line items at all. |
| Sep 2026 | Market re-reading: the "missing invoice list" already exists in the leading accounting software. |
| Oct 2026 | Project closed. |

## Why it failed — three causes, in order of weight

### 1. The demand was real — reaching the buyer was the problem

The need was not guessed. It came from market research and common sense: the president of the
Portuguese accountants' professional body put it in numbers ([source](08-metrics.md#sources)) — *20 to 30 % of an accountant's time goes into chasing
documents*. Small businesses may still issue plain PDF invoices until the end of 2026, and foreign
invoices never appear in the state's e-invoice data at all.

What did not work was **getting to the accountants and earning their attention**. Sales started only
after the product was built, through essentially one channel — cold email. By then the
whole bet rested on a channel that had never been tested.

### 2. The technical core did not reach the level the promise needed

The header of a Portuguese invoice is already sent to the tax authority — the accountant gets it
anyway. The value was in the **line items**, and that is the problem the whole document-AI industry
has not solved reliably. My measurements said so early (19 % in May, 10.3 % in August on a harder set — measured on the candidate lab extractor, not the production ladder),
and I chose precision over coverage: never guess, send to review. That was correct for trust — but it
meant the human desk carried most of the work, and the "silent" automation never arrived.

### 3. The corner was more crowded than it looked

The large document-AI vendors moved up-market, and the small-accountant corner looked free. But the
accountants' own software kept adding pieces of the same promise — in September I found that the
"missing invoices" list already exists in the leading Portuguese accounting program, in its €9-a-month plan ([source](08-metrics.md#sources)).
A newcomer has to be clearly better on the part that is left, and that part was the line items.

### On the outreach numbers

~240 emails, zero replies — not a verdict. At 120 delivered first contacts and a 1 % true reply rate,
zero replies happen in roughly 30 % of cases. What *was* measurably wrong: a 5.5 % bounce rate,
emails of ~250 words where 20–100 work, and one or two contacts where most replies come from the
second to sixth. The channel was never tested at a size that could fail cleanly.

## What I would do differently

1. **Start selling in month one, in parallel with building.** Test two or three channels early and
   small, so the build follows what the market answers.
2. **Measure the hard problem first.** The line-item rate was the business, and I measured it
   only after the platform was built. It should have been the first experiment.
3. **Choose a market I know from the inside — or find a real person who does.** Someone who sees
   the accountants' daily work and can open the first doors.
4. **Ship a smaller first slice that can be sold** — the part that already works — and let the
   rest follow paying users.
5. **Keep the architecture discipline — it was not the problem.** The constraints, the decision
   record and the measurement habit are what made it possible to see the failure clearly.

## What it gave me

> *It did not go live. But it was a joy to build — and while I was building it, I was being built.*

- Designing a system end to end under hard constraints: data sovereignty, tenant isolation, trust.
- Running a 6+-month, single-person project with an AI agent team — and learning where the
  human has to hold the line: direction, constraints, gates, review, measurement.
- Saying "this measurement says no" — and acting on it.
