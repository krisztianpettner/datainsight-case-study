"""
BillingLedgerService — BLOKK 7 #2 (L2 vízió Iter 28 SoT 2026-04-28).

Append-only writer for billing events. Every billing-relevant transition in
the pipeline calls one of the entry-point methods below. Hónap végi
aggregáció (tasks/billing_aggregation.py) per-Pedro SUM-ot olvas és
ClearAdmin invoice-ot generál; Stripe = csak fizetés-intéző (SEPA DD),
MeterEvent KIVEZETÉS pipeline-ban.

5 entry-point (per SoT §3):

    ┌────────────────────────────┬────────────────┬──────────────┐
    │ Pipeline esemény           │ event_type     │ amount_change│
    ├────────────────────────────┼────────────────┼──────────────┤
    │ Tier 0/1/2/3 → AUTO_APPROVE│ parsing_auto_  │ +1           │
    │                            │ approve        │              │
    │ HITL Ops approve           │ hitl_approve   │ +1           │
    │ HITL Ops reject            │ (NO ROW —      │ —            │
    │                            │  ClientAction- │              │
    │                            │  Log audit)    │              │
    │ Manual adjustment          │ manual_adj     │ ±X           │
    │ Refund (Stripe chargeback) │ refund         │ -X           │
    └────────────────────────────┴────────────────┴──────────────┘

Idempotency: every write expects an ``idempotency_key``. The service checks
for existing row first; on collision, returns the existing row WITHOUT a
duplicate INSERT. Composite natural keys are produced by the helpers
``make_pipeline_idem_key()`` and ``make_manual_idem_key()``.

Transaction policy: this service does NOT commit. The caller owns the
transaction (Risk R3 in SoT §10: parsing-completion + ledger-write must be
atomi to avoid drift on partial pipeline crash).
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Union

from sqlalchemy.orm import Session

from db.models_client import BillingLedger

logger = logging.getLogger("billing_ledger")


# ─── Event type constants ────────────────────────────────────────────────────

EVENT_PARSING_AUTO_APPROVE = "parsing_auto_approve"
EVENT_HITL_APPROVE = "hitl_approve"
EVENT_HITL_REJECT = "hitl_reject"  # informational — no ledger row written
EVENT_MANUAL_ADJ = "manual_adj"
EVENT_REFUND = "refund"
EVENT_SELF_BILLING_INJECT_META = "self_billing_inject_meta"

VALID_EVENT_TYPES = {
    EVENT_PARSING_AUTO_APPROVE,
    EVENT_HITL_APPROVE,
    EVENT_MANUAL_ADJ,
    EVENT_REFUND,
    EVENT_SELF_BILLING_INJECT_META,
}


# ─── Idempotency-key helpers ─────────────────────────────────────────────────


def make_pipeline_idem_key(
    batch_file_id: int, event_type: str, dt: Optional[datetime] = None
) -> str:
    """Time-less natural key for pipeline events — one row per (file, event_type) lifetime.

    Format: ``{batch_file_id}:{event_type}`` (NO time component).

    BLOKK 7.5 (#4) revízió: a korábbi minute-precision design (``{...}:{minute_iso}``)
    drift-veszélyt hordozott — ha ghost-recovery 1 perccel a crash után fut,
    KÜLÖNBÖZŐ minute-key keletkezett és duplikált ledger-row jött létre egy
    fájlra. A time-less key garantálja: egy `batch_file × event_type` LIFETIME
    egyetlen ledger-row — soha nem lehet dupla.

    NB: a ``dt`` paraméter már nem használatos; megtartva backward-compat-szempontból
    (signature stabil), a value silently ignorált.
    """
    return f"{batch_file_id}:{event_type}"


def make_manual_idem_key(operator: str, dt: Optional[datetime] = None) -> str:
    """Composite natural key for Ops-driven manual adjustments.

    Format: ``manual:{operator}:{YYYY-MM-DDTHH:MM:SS}`` (UTC, second precision
    so the same operator can issue distinct adjustments at sub-minute cadence).
    """
    if dt is None:
        dt = datetime.utcnow()
    ts_iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
    return f"manual:{operator}:{ts_iso}"


# ─── Internal write primitive ────────────────────────────────────────────────


def _write_event(
    db: Session,
    *,
    client_user_id: int,
    batch_file_id: Optional[int],
    event_type: str,
    pipeline_stage: Optional[str],
    amount_change: Decimal,
    idempotency_key: str,
    reason: Optional[str] = None,
    source_event_id: Optional[int] = None,
    created_by: str = "system",
    details: Optional[dict] = None,
) -> BillingLedger:
    """Idempotent INSERT — returns existing row on key collision.

    Caller MUST commit the transaction afterwards. The model itself is
    DB-trigger-protected (BEFORE UPDATE/DELETE) so even buggy callers can not
    silently mutate ledger history.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"invalid event_type: {event_type!r}")

    existing = (
        db.query(BillingLedger).filter(BillingLedger.idempotency_key == idempotency_key).first()
    )
    if existing is not None:
        logger.info(
            "billing_ledger idempotent hit: key=%s event=%s id=%d",
            idempotency_key,
            event_type,
            existing.id,
        )
        return existing

    row = BillingLedger(
        client_user_id=client_user_id,
        batch_file_id=batch_file_id,
        event_type=event_type,
        pipeline_stage=pipeline_stage,
        amount_change=amount_change,
        currency="EUR",
        reason=reason,
        idempotency_key=idempotency_key,
        source_event_id=source_event_id,
        created_by=created_by,
        details=details,
    )
    db.add(row)
    db.flush()  # populate row.id before returning, but caller commits
    logger.info(
        "billing_ledger write: key=%s event=%s amount=%s client=%d",
        idempotency_key,
        event_type,
        amount_change,
        client_user_id,
    )
    return row


# ─── Public entry-points ─────────────────────────────────────────────────────


def parsing_auto_approve(
    db: Session,
    *,
    client_user_id: int,
    batch_file_id: int,
    pipeline_stage: str,
    idempotency_key: Optional[str] = None,
    details: Optional[dict] = None,
) -> BillingLedger:
    """Tier 0/1/2/3 → Constitution AUTO_APPROVE (Silent1000 cél: 95%+).

    Writes ``+1`` row. ``pipeline_stage`` discriminator: tier0_qr / tier1_template
    / tier2_heuristic / tier3_llm / constitution. Idempotency key auto-derived
    if not given.
    """
    if idempotency_key is None:
        idempotency_key = make_pipeline_idem_key(batch_file_id, EVENT_PARSING_AUTO_APPROVE)
    return _write_event(
        db,
        client_user_id=client_user_id,
        batch_file_id=batch_file_id,
        event_type=EVENT_PARSING_AUTO_APPROVE,
        pipeline_stage=pipeline_stage,
        amount_change=Decimal("1"),
        idempotency_key=idempotency_key,
        details=details,
    )


def hitl_approve(
    db: Session,
    *,
    client_user_id: int,
    batch_file_id: int,
    operator: str = "ops",
    idempotency_key: Optional[str] = None,
    details: Optional[dict] = None,
) -> BillingLedger:
    """HITL Ops → APPROVE: a faktúra "tényleg feldolgozott", Pedro fizet.

    UX-szempontból azonos az auto-approve-pal (faktura `Aceito` mindkettő esetén).
    """
    if idempotency_key is None:
        idempotency_key = make_pipeline_idem_key(batch_file_id, EVENT_HITL_APPROVE)
    return _write_event(
        db,
        client_user_id=client_user_id,
        batch_file_id=batch_file_id,
        event_type=EVENT_HITL_APPROVE,
        pipeline_stage="hitl_workshop",
        amount_change=Decimal("1"),
        idempotency_key=idempotency_key,
        created_by=f"ops_user:{operator}",
        details=details,
    )


def hitl_reject(
    db: Session,
    *,
    client_user_id: int,
    batch_file_id: int,
    operator: str = "ops",
    reason: Optional[str] = None,
) -> None:
    """HITL Ops → REJECT: NEM ír ledger-be (Pedro nem fizet feldolgozhatatlanért).

    Per Iter 28 SoT §3+§7: HITL reject = "NINCS bejegyzés" a billing-ledger-be.
    Az audit-trail a ClientActionLog-ba megy (nem ennek a service-nek a dolga).
    Ez a függvény dokumentált API-symmetry céllal létezik — None-t ad vissza.

    Visual indicator: ``Faktura Rejeitado + Avisos "re-enviar" gomb`` (FE-oldal).
    """
    logger.info(
        "billing_ledger hitl_reject (no-op): client=%d file=%d operator=%s reason=%s",
        client_user_id,
        batch_file_id,
        operator,
        reason,
    )
    return None


def manual_adj(
    db: Session,
    *,
    client_user_id: int,
    amount_change: Union[int, float, Decimal],
    operator: str,
    reason: str,
    batch_file_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    details: Optional[dict] = None,
) -> BillingLedger:
    """Ops Admin korrekció: utólagos credit/debit, duplikátum-credit, vita-megoldás.

    ``amount_change`` lehet pozitív (Pedro javára credit) vagy negatív (terhelés).
    Mandatory ``reason`` — audit-trail compliance (R4 in SoT §10).
    """
    if not reason or not reason.strip():
        raise ValueError("manual_adj requires a non-empty reason (compliance)")
    amount = Decimal(str(amount_change))
    if idempotency_key is None:
        idempotency_key = make_manual_idem_key(operator)
    return _write_event(
        db,
        client_user_id=client_user_id,
        batch_file_id=batch_file_id,
        event_type=EVENT_MANUAL_ADJ,
        pipeline_stage="manual",
        amount_change=amount,
        idempotency_key=idempotency_key,
        reason=reason,
        created_by=f"ops_user:{operator}",
        details=details,
    )


def get_monthly_ledger(
    db: Session,
    *,
    client_user_id: int,
    year: int,
    month: int,
) -> list:
    """Pedro/Ops query: list ledger entries for the given (year, month), newest first.

    Returns all event types written to the ledger: parsing_auto_approve, hitl_approve,
    manual_adj, refund, self_billing_inject_meta. NOT hitl_reject — that one writes no
    ledger row by design (see ``hitl_reject()`` docstring).

    Used by:
    - Pedro web BillingPage ledger-history section (M3 task, BLOKK 15.7 NAP 2)
    - Ops Admin monthly billing review oldal (post-pilot)
    - tasks/billing_aggregation.py monthly aggregation Celery task
    """
    from calendar import monthrange

    if not (1 <= month <= 12):
        raise ValueError(f"month must be 1-12, got {month}")

    start = datetime(year, month, 1)
    last_day = monthrange(year, month)[1]
    # End-exclusive next-month-start to avoid microsecond drift on month-boundary writes
    if month == 12:
        end_exclusive = datetime(year + 1, 1, 1)
    else:
        end_exclusive = datetime(year, month + 1, 1)

    return (
        db.query(BillingLedger)
        .filter(
            BillingLedger.client_user_id == client_user_id,
            BillingLedger.created_at >= start,
            BillingLedger.created_at < end_exclusive,
        )
        .order_by(BillingLedger.created_at.desc())
        .all()
    )


def refund(
    db: Session,
    *,
    client_user_id: int,
    amount_change: Union[int, float, Decimal],
    source_event_id: int,
    idempotency_key: str,
    reason: Optional[str] = None,
    details: Optional[dict] = None,
) -> BillingLedger:
    """Stripe chargeback / refund — negatív amount, source_event_id link a forráshoz.

    ``idempotency_key`` KÖTELEZŐ (általában a Stripe event id, pl. ``stripe:evt_xxx``)
    mert Stripe webhook retry-okra védettség szükséges.

    A ``source_event_id`` az eredeti billing_ledger.id (NOT NULL post-MVP),
    audit-trail-hez szükséges (`amount` reconciliation).
    """
    amount = Decimal(str(amount_change))
    if amount > 0:
        amount = -amount  # refund mindig negative — caller-felüldefiniálás-védő
    return _write_event(
        db,
        client_user_id=client_user_id,
        batch_file_id=None,
        event_type=EVENT_REFUND,
        pipeline_stage=None,
        amount_change=amount,
        idempotency_key=idempotency_key,
        reason=reason,
        source_event_id=source_event_id,
        created_by="webhook:stripe",
        details=details,
    )
