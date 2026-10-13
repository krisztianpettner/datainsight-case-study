**English** · [Magyar](../hu/07-security-and-isolation.md) · [↑ README](../../README.md)

# Security and isolation

> **In one sentence:** isolation is enforced at one point and proven by tests, privacy holds even
> towards the AI that built the system, and the perimeter was attacked from outside before it was
> called closed.

## Tenant isolation — one enforcement point

- **One scope resolver** answers every "may this user see this client's data?" question — not
  filters scattered across routes.
- **Accountant access is a link plus consent.** Maria sees a client only if the accountant–client
  link exists and the client consented.
- **Blocked attempts are evidence.** A cross-tenant request is refused with 403 *and* logged as a
  blocked access attempt.
- **Introduced under characterisation tests:** 14 tests capturing the old behaviour plus 3
  differential-oracle tests comparing old and new answers — zero regressions at switch-over.
  Cross-tenant tests target the accountant paths explicitly (access by link, profiling with consent).
- **One person, one identity.** Users exist in three databases; an identity map pins one person to
  one identity across them.
- **Open items were ranked, not ignored:** consent as a hard gate rather than a formality,
  fail-closed on identity mismatch, a database-level role constraint — and the database bridge that
  depended on them was blocked until they were decided.

## Who can see what

| data | where it lives | who can see it |
|---|---|---|
| raw PDF | NAS outbox → PC, until 48 h after release | the pipeline; the operator during review |
| extracted values | PC processing database | the operator; the owner and his accountant through their exports |
| decision record | PC processing database | values redacted — names, scores and hashes only |
| status | VPS portal database (projection) | the owner; his accountant, if linked and consented |
| job record | VPS edge database | the edge app (upload bookkeeping) |

*The operator* is an internal role on our side of the service — not the accountant. Where the data
physically travels, and what each network leg can read, is in [Data path](06-data-path.md#what-crosses-which-boundary).

## The perimeter — stated, then measured

The principle: **default drop, whitelist only; the processing machines are never reachable from
the internet.** In front of the API, nginx keeps separate rate limits for general traffic,
authentication (5 per minute) and registration (10 per minute).

A principle is only a claim until someone attacks it. On 11 September 2026 I scanned the site from
the outside (from the VPS, SYN scan of the top-100 TCP ports): **zero open TCP ports on the
processing site**, UDP silently dropped, and the port-scan trap caught the scan within 20 seconds.
The VPS showed only web ports and SSH. The first two scans taught a lesson about measurement
itself: both returned a "clean zero" for the wrong reason (a scan-method artefact and a misread
trap window) — the recipe was fixed before the result was trusted.

## Privacy towards the builder

The system was built by AI agents, and the no-cloud promise had to hold for them too. **No client
invoice ever reached a model:** the pilot configuration never held live client data, the
development corpus was voluntarily shared public sample invoices, and from July 2026 a pre-tool
gate enforced the rule mechanically.

For debugging and schema training there is a **pseudonymisation engine**: an HMAC-keyed,
character-by-character transform that keeps format and length (a tax number stays a valid-looking
tax number) while the value is gone. QR payloads and PDF metadata are masked too, and a leak check
compares output against input before anything is released. The key (salt) is checked at start-up;
if the shipped placeholder were ever left in place, the profiling feed that relies on it switches
itself off rather than emit guessable hashes.

## Integrity — an audit trail that cannot be quietly edited

Every processing event is appended to an event log where each entry carries the hash of the
previous one. Five services read from it — status, audit report, audit anchor, destruction
sweep, portal projection — so they all tell the same story.

## Designed vs built — honestly

| designed | built |
|---|---|
| Cloudflare in front, origin hidden | the VPS origin was still reachable directly, around Cloudflare's firewall — found by the external scan; rated medium and left open when the project closed |
| scheduled verification of the hash chain | verification exists, not scheduled |
| consent as a hard gate, fail-closed identity checks | ranked and specified; the bridge that needed them was held back |
