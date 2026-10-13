**English** · [Magyar](../hu/05-trust.md) · [↑ README](../../README.md)

# Trust — the identity gate, the review desk, the lab

> **In one sentence:** no value reaches the accountant on the machine's word alone — each field is
> checked against an independent source, a person sees everything else, and every claim about
> accuracy is measured against a fixed golden set.

## The identity gate — where trust is decided

Every field has an entry in a **field catalogue**: its canonical name, its QR slot, its visual
slots, its type, whether it is critical, and how it can be verified:

| class | verified by | example |
|---|---|---|
| **a** | an independent source (QR, checksum) | tax numbers, totals, date, ATCUD |
| **b** | arithmetic between fields | net + VAT = gross |
| **c** | nothing — read-only | supplier name, free text |

For each field the engine compares the QR reading with the visual reading (amounts within 2 cents)
and gives it a band:

- 🟢 **green** — the two independent sources agree;
- 🟠 **amber** — one source only, or a soft disagreement;
- 🔴 **red** — a hard rule is broken (veto).

The document's confidence is the **minimum over its critical, verifiable fields** — one doubtful
total is enough to stop it. No verifiable critical field means confidence zero.

**In the pilot configuration, automatic approval was switched off in code.** Every invoice went to the review
desk, and the gate decided *what the operator has to look at*, not *whether anyone looks*. The plan
was to loosen field by field, only on measured evidence — start strict, loosen only where measurements allow.

## The review desk

The desk is an internal tool on the PC. *The operator* is a role on our side of the service — not
the accountant, who only ever sees the result. The service was designed to be run by **one operator
with a deputy**: everything else was automatic, and only three things needed a person — this
review, supervision of the system, and the semi-automatic customer support (machine translation
and answers that learn from earlier cases). The desk shows the operator one field at a time,
ordered by risk:

- **green fields are skipped** — the cursor does not even stop;
- for tax numbers and totals the input cell starts **empty**, so the operator types what she sees
  instead of confirming what the machine suggested (anti-anchoring);
- on commit, **the same validators that judged the machine judge the human** — a tax number typed
  into the wrong party's field is refused unless explicitly overridden.

The operator's time per invoice, not the auto-approve rate, was the north-star metric: as long as
trust is being built, everything is reviewed, so the question is how fast.

## The measurement lab

- A **golden set** of 203 annotated invoices (public sample invoices, not client data). Its
  *clean subset* — 134 invoices — leaves out those with no net-total anchor, multi-invoice
  bundles and non-invoices.
- A **QR-anchored metric** for line items: do the extracted lines add up to the invoice's net
  total? Each invoice ends as *reconciled*, *sum off*, or *empty*.
- An eight-phase improvement loop — orient, measure, triage, diagnose, spike, fix, verify, record —
  where every change is kept or dropped by measured effect.
- ⚠️ **What the numbers measure.** The line-item rates in this repository (19 % in May; 10.3 % in
  August — 10 of the 97 invoices with a ground truth among the 101 measured before the run was stopped) were measured on the **lab extractor** — a table-recognition model evaluated as the
  candidate next layer — not on the production ladder above. I found this mismatch myself, late;
  it is recorded as one of the lessons on measurement.

## Designed vs built — honestly

| designed | built |
|---|---|
| automatic approval above a confidence threshold | disabled in the pilot configuration; an opt-in "safe auto-approve" path existed behind a flag |
| loosen the gate field by field, on measured evidence | the change protocol and the golden-set check existed; no field was loosened before the project closed |
