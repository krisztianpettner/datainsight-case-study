"""BatchEventsService — M7 (BLOKK 15.7 NAP 5, Iter 24 Monitoring Hub SoT).

Pipeline-szakaszok ezen a service-en keresztül írnak event-et a `batch_events`
táblába. 3 fogyasztó (Ops Streamlit / Pedro web / Mobile) ugyanezt az SoT-ot
olvassa pull-pattern-nel.

Transaction policy: ez a service NEM commit-ol. A caller felelős a tranzakcióért
(konzisztens a `billing_ledger_service` mintával — a pipeline crash esetén a
rendezetlen state ne okozzon ledger-write + event-write drift-et).
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models_client import BatchEvent

logger = logging.getLogger("batch_events")

# ─── S175 §10/3: tamper-evident append-only hash-chain ──────────────────────
# Global, id-ordered chain over batch_events. entry_hash links each row to the
# previous; verify_chain() detects any in-place tampering. The DB trigger
# (migration 20260620_000001) blocks UPDATE/DELETE; the external RFC-3161 anchor
# (§10/6) is the final defence against a privileged operator who could otherwise
# re-compute the chain. Hash input is narrow + string-only (job_id/pdf_sha256 from
# details) so JSONB round-trip is stable and client_id/batch_id stay OUT of the hash
# (so account-deletion SET NULL never breaks it — legal-lock 12.A/1).
GENESIS_HASH = "0" * 64
_CHAIN_LOCK_KEY = 0x42455641  # "BEVA" — batch-events audit chain serialisation


def _chain_entry_hash(
    *, prev_hash: str, event_type: str, job_id: str, pdf_sha256: str, created_at_iso: str
) -> str:
    """sha256 over the canonical, string-only chain payload (constitution pattern)."""
    canonical = json.dumps(
        {
            "prev_hash": prev_hash,
            "event_type": event_type,
            "job_id": job_id,
            "pdf_sha256": pdf_sha256,
            "created_at": created_at_iso,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row_chain_hash(prev_hash: str, row: BatchEvent) -> str:
    """Recompute a stored row's entry_hash from its persisted fields (verify_chain)."""
    details = row.details or {}
    return _chain_entry_hash(
        prev_hash=prev_hash,
        event_type=row.event_type,
        job_id=str(details.get("job_id") or ""),
        pdf_sha256=str(details.get("pdf_sha256") or ""),
        created_at_iso=row.created_at.isoformat() if row.created_at else "",
    )


# ─── Event-type constants (Iter 24 SoT §4 + Iter 28 HITL bővítés) ──────────


EVENT_UPLOADED = "UPLOADED"
EVENT_QUEUED = "QUEUED"
EVENT_PROCESSING_STARTED = "PROCESSING_STARTED"
EVENT_QR_PARSED = "QR_PARSED"
EVENT_OCR_DONE = "OCR_DONE"
EVENT_VALIDATED = "VALIDATED"
EVENT_HITL_FLAGGED = "HITL_FLAGGED"
EVENT_HITL_RESOLVED = "HITL_RESOLVED"
EVENT_COMPLETED = "COMPLETED"
EVENT_ERROR = "ERROR"
EVENT_RELEASED = "RELEASED"
EVENT_EXPORTED = "EXPORTED"

# S175 — raw-PDF lifecycle audit events (the tamper-evident registry, plan §3).
# NAS_STORED carries the received file's pdf_sha256 (proof of WHICH file we held);
# NAS_DESTROYED re-hashes at destruction (the two bracket the retention window).
# NAS_DESTROY_FAILED + operator-alert when the §10/5 sweep cannot delete (DA-K4).
EVENT_NAS_STORED = "NAS_STORED"
EVENT_NAS_DESTROYED = "NAS_DESTROYED"
EVENT_NAS_DESTROY_FAILED = "NAS_DESTROY_FAILED"

# S178 §B-lánc F5 — delivery-proof: a client-authenticated download of a processed
# result file. Closes the lifecycle (received → processed → DELIVERED → destroyed).
# K1 (chain-slot semantics): the `pdf_sha256` chain slot is the content-hash of the
# event's SUBJECT ARTEFACT (the raw PDF for NAS_STORED/NAS_DESTROYED; the delivered
# RESULT FILE for DELIVERED). The hash FUNCTION is unchanged → the existing chain stays
# intact; only the audit-report labelling must be event-type-aware (audit_report_service).
EVENT_DELIVERED = "DELIVERED"

VALID_EVENT_TYPES = {
    EVENT_UPLOADED,
    EVENT_QUEUED,
    EVENT_PROCESSING_STARTED,
    EVENT_QR_PARSED,
    EVENT_OCR_DONE,
    EVENT_VALIDATED,
    EVENT_HITL_FLAGGED,
    EVENT_HITL_RESOLVED,
    EVENT_COMPLETED,
    EVENT_ERROR,
    EVENT_RELEASED,
    EVENT_EXPORTED,
    EVENT_NAS_STORED,
    EVENT_NAS_DESTROYED,
    EVENT_NAS_DESTROY_FAILED,
    EVENT_DELIVERED,
}


def _worker_id() -> str:
    """Best-effort worker hostname/task-id (hostname + Celery prefork-PID)."""
    pid = os.getpid()
    host = os.environ.get("HOSTNAME", "unknown")
    return f"{host}:{pid}"


def emit_event(
    db: Session,
    *,
    batch_id: int,
    event_type: str,
    client_id: Optional[int] = None,
    details: Optional[dict] = None,
    worker_id: Optional[str] = None,
) -> BatchEvent:
    """Append-only INSERT — caller commit-ol.

    Args:
        batch_id: ClientBatch.id (FK CASCADE — batch törlésre el is tűnik)
        event_type: Iter 24 12-érzékelős enum (lásd VALID_EVENT_TYPES)
        client_id: Optional ClientUser.id (FK SET NULL anonymizálás után)
        details: JSONB context (filename, confidence, decision, error_msg, ...)
        worker_id: Optional override; default = hostname:pid

    Raises:
        ValueError: érvénytelen event_type
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"invalid event_type: {event_type!r}")

    # S175 §10/3: append to the tamper-evident hash-chain. Serialise the read-head →
    # link → insert on a global advisory xact-lock so concurrent emits can't fork the
    # chain (held until the caller commits/rolls back; a rolled-back emit leaves no
    # committed row → the chain stays continuous over committed rows). PG-only lock;
    # on sqlite (deps-light unit context) it is skipped — single-threaded, no fork.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK_KEY})
    now = datetime.utcnow()
    head = (
        db.query(BatchEvent.entry_hash)
        .filter(BatchEvent.entry_hash.isnot(None))
        .order_by(BatchEvent.id.desc())
        .limit(1)
        .scalar()
    )
    prev_hash = head or GENESIS_HASH
    _details = details or {}
    entry_hash = _chain_entry_hash(
        prev_hash=prev_hash,
        event_type=event_type,
        job_id=str(_details.get("job_id") or ""),
        pdf_sha256=str(_details.get("pdf_sha256") or ""),
        created_at_iso=now.isoformat(),
    )

    row = BatchEvent(
        batch_id=batch_id,
        client_id=client_id,
        event_type=event_type,
        worker_id=worker_id or _worker_id(),
        details=details,
        created_at=now,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(row)
    db.flush()  # populate row.id, but caller commits

    logger.info(
        "batch_events emit: batch=%s type=%s worker=%s",
        batch_id,
        event_type,
        row.worker_id,
    )
    return row


def verify_chain(db: Session) -> dict:
    """Verify the append-only hash-chain integrity (S175 §10/3).

    Walks the hashed rows in id order, checking each links to the previous row's
    entry_hash AND that its stored entry_hash matches a recompute from its persisted
    fields. id-gaps (e.g. a rolled-back emit) are tolerated — linkage follows the
    ordered result set, not id arithmetic. Returns ``{ok, checked, first_broken_id,
    head_hash}``.
    """
    rows = (
        db.query(BatchEvent)
        .filter(BatchEvent.entry_hash.isnot(None))
        .order_by(BatchEvent.id.asc())
        .all()
    )
    prev = GENESIS_HASH
    for row in rows:
        expected = _row_chain_hash(prev, row)
        if row.prev_hash != prev or row.entry_hash != expected:
            return {"ok": False, "checked": len(rows), "first_broken_id": row.id, "head_hash": prev}
        prev = row.entry_hash
    return {"ok": True, "checked": len(rows), "first_broken_id": None, "head_hash": prev}


def list_events(
    db: Session,
    *,
    batch_id: int,
    since: Optional[datetime] = None,
    limit: int = 200,
) -> list:
    """List events for a batch, optionally filtered by since-cutoff (UTC).

    Returns the RAW rows (ordered ASC by created_at). Used by:
    - GET /api/client/batches/{batch_id}/events?since=ISO  (Pedro/Mobile) — but ONLY
      through `customer_safe_events` (BUG-023 mask; a nyers telemetria sose megy vevőnek).
    - Ops Admin Process Log page (post-pilot SHOULD) — ez MINDENT lát, ezért nem itt szűrünk.
    """
    query = db.query(BatchEvent).filter(BatchEvent.batch_id == batch_id)
    if since is not None:
        query = query.filter(BatchEvent.created_at > since)
    return query.order_by(BatchEvent.created_at.asc()).limit(limit).all()


# ── BUG-023: customer-facing timeline mask (vevői eseménytörténet) ──────────────
# A nyers batch_events sorok belső telemetriát hordoznak (job_id, decision_status,
# NAS-útvonalak, celery/worker-id, operator/e-mail/NIF). Ezek az Ops Admin Process
# Log-ba valók, NEM a vevő idővonalára. Két rétegű maszk (allow-list fegyelem, mint a
# selected_values maszkolásnál — egy jövőbeli új belső kulcs se szivároghasson):

# Vevőnek látható esemény-típusok. A NAS_* (tárolás/megsemmisítés-audit) KIMARAD.
_CUSTOMER_EVENT_TYPES = frozenset({
    EVENT_UPLOADED, EVENT_QUEUED, EVENT_PROCESSING_STARTED, EVENT_QR_PARSED,
    EVENT_OCR_DONE, EVENT_VALIDATED, EVENT_HITL_FLAGGED, EVENT_HITL_RESOLVED,
    EVENT_COMPLETED, EVENT_ERROR, EVENT_RELEASED, EVENT_EXPORTED, EVENT_DELIVERED,
})

# Az EGYETLEN details-kulcs-halmaz, ami átmehet a vevői idővonalra (a saját fájljáról
# szóló, nem-PII, számára értelmes infó). Minden más — job_id, decision/decision_status,
# confidence, NAS-út, worker/celery-id, operator, e-mail, NIF — DROPPOL.
_CUSTOMER_SAFE_DETAIL_KEYS = frozenset({
    "filename", "file_count", "output_format", "total", "ok", "review", "failed",
})


def customer_safe_events(rows: list) -> list:
    """Filter+mask raw BatchEvent rows for the customer-facing timeline (BUG-023).

    Kimarad minden belső-csak esemény-típus (NAS_*), a details a whitelistre szűkül,
    a worker_id (host:pid infra-jel) NULL. Könnyű dict-eket ad vissza a route
    Pydantic-modelljéhez (id, event_type, worker_id, details, created_at).
    """
    out = []
    for r in rows:
        if r.event_type not in _CUSTOMER_EVENT_TYPES:
            continue
        raw = r.details or {}
        safe = {k: raw[k] for k in _CUSTOMER_SAFE_DETAIL_KEYS if k in raw}
        out.append({
            "id": r.id,
            "event_type": r.event_type,
            "worker_id": None,  # host:pid = infra, nem vevői infó
            "details": safe or None,
            "created_at": r.created_at,
        })
    return out
