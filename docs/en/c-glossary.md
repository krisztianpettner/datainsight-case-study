**English** · [Magyar](../hu/c-glossary.md) · [↑ README](../../README.md)

# Glossary

| term | meaning here |
|---|---|
| **Pedro** | persona: a small-business owner who uploads invoices and pays. Built from market research, not a real person. |
| **Maria** | persona: his accountant, who uses the service free and closes the month. Built from market research, not a real person. |
| **pilot configuration** | the settings prepared for the first real users — above all, automatic approval switched off. **There were no pilot users:** outreach brought no customer, so "pilot" here never means live client data. |
| **operator** | the internal role on our side of the service, designed for one person with a deputy: reviews invoices at the review desk, supervises the system, watches the semi-automatic support, and invites accountants onto the platform. Not the accountant. |
| **NIF** | Portuguese tax identification number (9 digits, with a check digit). |
| **ATCUD** | the unique code every Portuguese invoice carries, registered with the tax authority. |
| **AT QR code** | the signed QR code on Portuguese invoices; carries issuer and customer NIF, date, number, ATCUD, VAT and totals. |
| **oracle** | an independent source the engine does not have to take on trust — here the AT QR code. |
| **e-Fatura** | the Portuguese system through which invoice headers and VAT are reported to the state — without line items. |
| **VIES** | the EU service that confirms whether a VAT number is active; required evidence for reverse charge. |
| **reverse charge** | cross-border EU B2B rule: the buyer, not the seller, accounts for the VAT. |
| **line items** | the individual rows of an invoice — product, quantity, unit price, VAT rate. The hard part. |
| **tier 1 / 2 / 3** | (1) the QR payload · (2) schemas and heuristics for the header, plus the line-item ladder · (3) a local LLM, only if the ladder yields nothing. |
| **ladder** | the ordered list of table-extraction layers for line items; the first layer that yields rows wins. |
| **master / delta schema** | a country-level YAML / a per-invoicing-software YAML on top of it. |
| **golden set** | 203 annotated public sample invoices used to measure extraction. |
| **clean subset** | the 134 invoices of the golden set that can be measured cleanly — without those that have no net-total anchor, the multi-invoice bundles and the non-invoices. |
| **HITL** | human in the loop: a person reviews what the machine could not verify. Here: the **review desk**. |
| **north-star metric** | the one number a phase is steered by — here, the operator's minutes per invoice. |
| **projection** | a read-mostly copy of what the users may see, held on the public server; the source of truth stays on the PC. |
| **bit-exact staircase** | refactoring one block at a time behind a frozen baseline, proving each step changes no output. |
| **drift list** | a numbered list of every difference between the live deployment and its documents, each with a status. |
| **shepherd** | my role towards the AI agents: direction, constraints, gates, review, measurement — not typing the code. |
| **law of evidence** | a sales-list rule: a guessed domain cannot confirm itself; an independent signal is required. |
| **on-prem** | on hardware I own, not in a cloud. |

## The five "gates" — one word, five different things

| gate | what it decides | chapter |
|---|---|---|
| **identity gate** | per field: do two independent sources agree (green / amber / red), and is the document confident enough to skip review | [Trust](05-trust.md#the-identity-gate--where-trust-is-decided) |
| **commit gate** | on the review desk: the same validators judge what the operator types | [Trust](05-trust.md#the-review-desk) |
| **PII gate** | no client invoice content reaches an LLM, including the development agents | [Security](07-security-and-isolation.md#privacy-towards-the-builder) |
| **day-opening gate** | no code edit, commit or send until the session's opening routine has run | [How I worked](13-how-i-worked.md) |
| **exit gate** (go-to-market) | when to leave one sales channel for the next | [Go-to-market](11-go-to-market.md#go-to-market-as-a-measurement-machine) |
