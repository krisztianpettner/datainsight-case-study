**English** · [Magyar](../hu/glossary.md) · [↑ README](../../README.md)

# Glossary

| term | meaning here |
|---|---|
| **Pedro** | persona: a small-business owner who uploads invoices and pays. Built from market research, not a real person. |
| **Maria** | persona: his accountant, who uses the service free and closes the month. Built from market research, not a real person. |
| **NIF** | Portuguese tax identification number (9 digits, with a check digit). |
| **ATCUD** | the unique code every Portuguese invoice carries, registered with the tax authority. |
| **AT QR code** | the signed QR code on Portuguese invoices; carries issuer and customer NIF, date, number, ATCUD, VAT and totals. Here: the **oracle**. |
| **e-Fatura** | the Portuguese system through which invoice headers and VAT are reported to the state — without line items. |
| **VIES** | the EU service that confirms whether a VAT number is active; required evidence for reverse charge. |
| **reverse charge** | cross-border EU B2B rule: the buyer, not the seller, accounts for the VAT. |
| **line items** | the individual rows of an invoice — product, quantity, unit price, VAT rate. The hard part. |
| **golden set** | 203 annotated sample invoices used to measure extraction. |
| **HITL** | human in the loop: a person reviews what the machine could not verify. Here: the **review desk**. |
| **tier 1 / 2 / 3** | QR and templates / schemas and heuristics / local LLM — tried in that order. |
| **master / delta schema** | a country-level YAML / a per-invoicing-software YAML on top of it. |
| **on-prem** | on hardware I own, not in a cloud. |

## The five "gates" — one word, five different things

| gate | what it decides | chapter |
|---|---|---|
| **identity gate** | per field: do two independent sources agree (green / amber / red), and is the document confident enough to skip review | [Parsing engine](02-parsing-engine.md) |
| **commit gate** | on the review desk: the same validators judge what the operator types | [Parsing engine](02-parsing-engine.md#the-review-desk) |
| **PII gate** | no client invoice content reaches an LLM, including the development agents | [Data path](03-data-path.md#privacy-towards-the-builder) |
| **day-opening gate** | no code edit, commit or send until the session's opening routine has run | [How I worked](07-how-i-worked.md) |
| **exit gate** (go-to-market) | when to leave one sales channel for the next | [Market and pricing](06-market-and-pricing.md) |
