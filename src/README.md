# The code — a curated extract

**English** · magyarul lent

This folder holds about forty files out of ~1,150: the parts the chapters talk about. It is a
reading set, not a runnable system — the full platform depends on its databases, queues, OCR,
three machines and the network between them. Code comments are partly in Hungarian, as written
during the project; tags such as `S182` or `DA-K6` point to the session log and the review finding
behind a change. The production domain and storage vendor are replaced with placeholders. Tax numbers in examples and tests are synthetic (checksum-valid) replacements.

| chapter | read |
|---|---|
| [Parsing engine](../docs/en/02-parsing-engine.md) — ingress check | `ingress/` |
| — QR oracle | `pdf_parser/qr_barcode_engine_v2.py` |
| — schemas as data | `schemas/masters/`, `parsing/schemas/` |
| — the pipeline and the line-item ladder | `parsing/heuristic_engine.py`, `parsing/profiles/base.py` |
| — local LLM with circuit breaker | `parsing/llm/local_client.py` |
| — validation rules | `orchestration/constitution.py` |
| — **the identity gate** (QR vs visual, bands, document confidence) | `parsing/identity/` |
| — the review desk's commit gate | `services/desk_gate.py` |
| [Data path](../docs/en/03-data-path.md) — upload relay to the NAS | `vps/sync/nas_sftp.py` |
| — hand-over and status push on the PC | `dispatch_watcher.py` |
| — hash-chained event log | `services/batch_events_service.py` |
| — pseudonymisation engine | `services/pseudonymization_engine.py` |
| [Platform](../docs/en/04b-platform.md) — one scope resolver | `services/authz/` |
| [Billing](../docs/en/04c-billing.md) — append-only ledger (DB trigger) | `alembic/versions/20260502_000001_billing_ledger.py`, `services/billing_ledger_service.py` |
| — graduated pricing | `services/billing_pricing.py` |
| — reverse-charge gate | `services/tax_treatment.py` |

**The identity gate's tests run standalone:**

```bash
python -m venv .venv && .venv/bin/pip install pytest
PYTHONPATH=src .venv/bin/python -m pytest tests/parsing/identity -q
```

---

## A kód — válogatott kivonat (magyarul)

Ez a mappa a ~1 150 fájlból körülbelül negyvenet tartalmaz: azokat, amelyekről a fejezetek
szólnak. Olvasásra szolgál, nem futtatható rendszer — a teljes platform az adatbázisaira, a
feladatsoraira, az OCR-re, a három gépre és a köztük lévő hálózatra épül. A kódkommentek részben
magyarok, ahogy a projekt alatt születtek. A példákban és a tesztekben szereplő adószámok
szintetikus (ellenőrzőösszegre érvényes) helyettesítők. A fejezet → fájl térkép a fenti táblában;
a [magyar fejezetek](../docs/hu/) ugyanezekre a fájlokra hivatkoznak.
