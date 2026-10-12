#!/usr/bin/env python3
"""Dispatch Watcher — monitors NAS sync client sync folder for new PDFs.

This is the PC-side counterpart to the VPS dispatch mode.
When a PDF arrives in the outbox (via NAS sync client sync from NAS),
the watcher triggers the parsing pipeline and writes results to inbox.

Flow:
  NAS outbox/{client_id}/{job_id}_{name}.pdf
    → NAS sync client sync
    → PC watch_dir/{client_id}/outbox/{job_id}_{name}.pdf
    → THIS WATCHER → main_batch_processor.extract_and_process()
    → PC watch_dir/{client_id}/inbox/{job_id}.json
    → NAS sync client sync back to NAS

Usage:
    python dispatch_watcher.py                          # Default watch dir
    python dispatch_watcher.py --watch-dir /path/to/sync
    python dispatch_watcher.py --once                   # Single scan, no watch
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# watchdog backs the continuous watch() mode only. --once / scan_once is a plain
# glob scan and must run in deps-light environments (api/worker image, CI) that
# don't ship watchdog. Guard the import so the module still loads there; watch()
# fails loudly if watchdog is genuinely missing.
try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - exercised in deps-light --once runs
    FileSystemEventHandler = object
    Observer = None

from db.database import SessionLocal  # R3 (S160): PC pdf_parsing_db session for decision-persist
from db.session import init_db  # standalone entry-point bootstraps its own DB manager (S167 Stage 2b)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dispatch_watcher")

# Default NAS sync client sync path (Windows)
DEFAULT_WATCH_DIR = r"D:\app_data\nas-sync\clients"


class PDFHandler(FileSystemEventHandler):
    """Handle new PDF files appearing in outbox directories."""

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".pdf":
            return
        # Only process files in outbox/ subdirectories
        if "outbox" not in path.parts:
            return
        # Already handled (parsed → .done, or dead → .failed): don't re-parse on a
        # NAS re-sync event (S175 §10/1, DA-K4 — keep watch-mode consistent with
        # the poll path). Skip before _wait_for_stable: no point waiting on a no-op.
        if _has_terminal_marker(path):
            return
        # NAS sync client may create temp files first — wait for stable size
        if not _wait_for_stable(path, timeout=30):
            logger.warning("File not stable after 30s, skipping: %s", path)
            return
        logger.info("New PDF detected: %s", path)
        _process_pdf(path)


def _wait_for_stable(path: Path, timeout: int = 30) -> bool:
    """Wait until file size stops changing (NAS sync client sync complete)."""
    prev_size = -1
    elapsed = 0
    while elapsed < timeout:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        if size == prev_size and size > 0:
            return True
        prev_size = size
        time.sleep(1)
        elapsed += 1
    return prev_size > 0


def _parse_job_info(path: Path) -> tuple:
    """Extract client_id and job_id from path.

    Expected: .../clients/{client_id}/outbox/{job_id}_{filename}.pdf
    """
    parts = path.parts
    try:
        outbox_idx = parts.index("outbox")
        client_id = parts[outbox_idx - 1]
        filename = path.stem  # job_id_originalname
        job_id = filename.split("_", 1)[0]  # UUID prefix
        return client_id, job_id
    except (ValueError, IndexError):
        return None, None


# P0 (S156, GDPR/K7): the inbox/{job_id}.json result file is rsynced to the
# VPS filesystem (vps/sync/nas_scripts.push_to_vps → vps_results/). It MUST
# carry ONLY VPS-OK metadata — NEVER raw invoice content. The parsed data
# stays PC-side (the output_file + pdf_parsing_db). Masked decision fields
# (decision_status/confidence/rejection_*) are added later by the bridge (R5a).
# ARCH-DOC: docs/architecture/33-dataflow-and-data-scope.md#3 (data-scope)
_RESULT_VPS_OK_KEYS = frozenset(
    {"status", "job_id", "client_id", "output_file", "processing_time_sec", "processed_at", "error"}
)


def _completed_result_payload(job_id: str, client_id: str, output_file, processing_time_sec: float) -> dict:
    """Build the completed-job result.json payload — VPS-OK metadata ONLY.

    NEVER include raw ``invoice_data`` / parsed content here: this file leaves
    the PC for the VPS filesystem (no-cloud/K7). Keys must stay within
    ``_RESULT_VPS_OK_KEYS`` (guarded by tests/dispatch/test_result_payload_no_pii.py).
    """
    return {
        "status": "completed",
        "job_id": job_id,
        "client_id": client_id,
        "output_file": str(output_file),
        "processing_time_sec": round(processing_time_sec, 2),
        "processed_at": datetime.utcnow().isoformat(),
    }


def _persist_decision_for_job(session_factory, **kwargs) -> dict:
    """R3 (S160) + S188 F1/F2: open a PC DB session, persist the decision, run the PC
    duplicate-decision gate (atcud-only, before HITL) + fallback dup_suspect marking +
    window-sweep, then ALWAYS close (K7). The service never manages the session — this
    dispatch boundary owns its lifecycle; persist + gate + sweep run in ONE session
    (S188 itinerary §2/§3 session-discipline note).

    Returns a dict the caller (`_process_pdf`) uses for its `_push_status`/
    `_persist_desk_cache`/`_push_profiling_feed` branching:
      {"status": <final canonical decision_status>, "confidence": <float>,
       "suppressed": <bool>, "duplicate_of_job_id": Optional[str],
       "previous_date": Optional[str]}
    A missing/non-numeric client_id (CLI path, unparseable NAS segment) makes every gate
    lookup a fail-closed no-op (DA-K3) — the returned status is then just the original
    decision's, unchanged from the pre-S188 behaviour.
    """
    from services.constitution_decision_persistence_service import persist_decision
    from services.duplicate_gate_service import (
        find_final_duplicate,
        find_final_fallback_match,
        mark_dup_suspect,
        suppress_as_duplicate,
        sweep_pending_duplicates,
        trigger_publish_after_sweep,
    )

    job_id = kwargs["job_id"]
    client_id = kwargs.get("client_id")
    db = session_factory()
    try:
        record = persist_decision(db, **kwargs)
        result = {
            "status": record.status,
            "confidence": record.confidence,
            "suppressed": False,
            "duplicate_of_job_id": None,
            "previous_date": None,
        }
        meta = record.meta or {}
        dup_of = find_final_duplicate(
            db, client_id=client_id, atcud_hash=meta.get("atcud_hash"), exclude_job_id=job_id
        )
        if dup_of is not None:
            # S188 F1.2 suppress-ág: a doksi be SEM kerül a HITL-sorba (a record itt még
            # csak most persistált, a desk queue csak a status alapján válogat).
            suppress_as_duplicate(db, record=record, duplicate_of=dup_of)
            result.update(
                {
                    "status": record.status,
                    "suppressed": True,
                    "duplicate_of_job_id": dup_of.job_id,
                    "previous_date": (
                        dup_of.created_at.strftime("%Y-%m-%d") if dup_of.created_at else None
                    ),
                }
            )
        else:
            fb_match = find_final_fallback_match(
                db,
                client_id=client_id,
                fallback_hash=meta.get("fallback_hash"),
                exclude_job_id=job_id,
            )
            if fb_match is not None:
                mark_dup_suspect(db, record=record, matched_job_id=fb_match.job_id, key="fallback")
            if record.status == "AUTO_APPROVE":
                # F2.2 dispatch-oldali sweep-hívási pont: csak SIKERES véglegesedés után.
                swept = sweep_pending_duplicates(db, anchor=record)
                if swept:
                    trigger_publish_after_sweep(swept)
        return result
    finally:
        db.close()


# ── S168 D3: portal_db status mirror (job_id-first push) ────────────────────
# The watcher pushes each file's lifecycle to the portal_app so Pedro SEES the real
# status (processing → completed/review/error) in the upload surface. Best-effort:
# a push failure NEVER blocks parsing (the PC constitution_decisions stays the SoT;
# the next poll round re-pushes). PII-free payload: job_id + masked decision/error
# code only — the raw filename/exception stays PC-ONLY (K7/GDPR).
# ARCH-DOC: docs/architecture/16-deploy-topology.md (nginx /api/vps/dispatch/ → portal_app)
_PORTAL_STATUS_URL = os.getenv(
    "PORTAL_STATUS_URL", "https://portal.example.com/api/vps/dispatch/file-status"
)
# S172 F-B: pseudonymous monthly profiling aggregates → portal_db (SEPARATE channel).
_PORTAL_PROFILING_FEED_URL = os.getenv(
    "PORTAL_PROFILING_FEED_URL", "https://portal.example.com/api/vps/dispatch/profiling-feed"
)
# S175 §10/5: destruction-sweep worklist (released + 48h raw PDFs still to delete).
_PORTAL_DESTRUCTION_DUE_URL = os.getenv(
    "PORTAL_DESTRUCTION_DUE_URL", "https://portal.example.com/api/vps/dispatch/destruction-due"
)
_DEFAULT_PSEUDONYM_SALT = "dat-ai-nsight-default-salt-CHANGE-ME"


def _push_status(job_id: str, phase: str, **fields) -> None:
    """POST a file lifecycle step to the portal bridge (best-effort, never raises)."""
    api_key = os.getenv("VPS_ADMIN_API_KEY", "").strip()
    if not api_key:
        logger.warning("VPS_ADMIN_API_KEY unset — skipping portal status push (job %s)", job_id)
        return
    payload = {"job_id": job_id, "phase": phase}
    payload.update({k: v for k, v in fields.items() if v is not None})
    try:
        import httpx

        # 30s (not 15): the container's first HTTPS call is a cold DNS+TLS handshake
        # that can exceed 15s; subsequent pushes are sub-second. Best-effort anyway.
        resp = httpx.post(
            _PORTAL_STATUS_URL, json=payload, headers={"X-Admin-Key": api_key}, timeout=30.0
        )
        if resp.status_code == 200:
            logger.info("Portal status %s/%s → applied=%s", job_id, phase, resp.json().get("applied"))
        else:
            logger.warning("Portal status %s/%s → HTTP %s: %s", job_id, phase, resp.status_code, resp.text[:200])
    except Exception as exc:  # best-effort — parsing must not depend on portal reachability
        logger.warning("Portal status push %s/%s failed: %s", job_id, phase, exc)


def _aggregate_profiling(unified) -> list:
    """Group an invoice into pseudonymous monthly per-band rows for the profiling feed.

    QR-PRIMARY (S177): the PT fiscal QR carries per-band base+IVA (Portaria 195/2020
    I2-I8), checksum-validated. `unified.qr_iva_bands()` returns those bands IFF they
    reconcile to (gross-tax); we feed them directly — exact, reliable, the right basis
    for a DPI declaration. Only when the QR bands are absent or don't reconcile (non-PT,
    damaged, or multi-region Açores/Madeira QR) do we FALL BACK to line-item summation
    (classified by each line's tax_rate). The two paths never mix on one invoice → no
    double/zero-count (DA K1/K6).

    Returns [] (skips the feed) when:
      - PSEUDONYM_SALT is still the default → would emit guessable hashes (DA K1, fail-closed);
      - the invoice lacks a supplier tax_id or a date (can't key the aggregate).
    One invoice → one supplier_hash + one month (header-derived); rows differ only by iva_code.
    invoice_count=1 per (iva) group so the portal recompute SUMs to the right per-cell count.
    The raw supplier NAME never leaves the PC — only the salted hash + iva + month + EUR sums.
    """
    from services.profiling_engine import classify_iva
    from services.pseudonymizer import PLATFORM_SALT, supplier_hash

    if PLATFORM_SALT == _DEFAULT_PSEUDONYM_SALT:
        logger.error(
            "PSEUDONYM_SALT is the default — skipping profiling feed (would emit guessable "
            "hashes). Set a real PSEUDONYM_SALT in the PC env before the pilot."
        )
        return []
    tax_id = getattr(unified, "tax_id", None)
    date = getattr(unified, "date", None)
    if not tax_id or not date or len(str(date)) < 7:
        return []
    month = str(date)[:7]  # YYYY-MM
    sh = supplier_hash(str(tax_id))

    # Kör1 M4 (D2, S186): a nota de crédito (NC) NEGATÍVAN járul az aggregátumhoz — a
    # jóváírás eddig pluszban adódott a Maria-oldali IVA-nézetbe. Forward-only (DA-K6:
    # régi hónap csak reprocess-re frissül); invoice_count marad +1 (a jóváírás is doc).
    # A kód-normalizálás a vevői exporttal KÖZÖS lexikonon (export_canon) történik.
    from services.export_canon import _doctype_code

    sign = -1.0 if _doctype_code(unified) == "NC" else 1.0

    def _signed_round(v: float) -> float:
        out = round(sign * v, 2)
        return 0.0 if out == 0 else out  # -0.0 kozmetika ellen (DA-K7)

    # QR-PRIMARY: per-band base+IVA straight from the checksum-validated fiscal QR.
    qr_bands = None
    _bands_fn = getattr(unified, "qr_iva_bands", None)
    if callable(_bands_fn):
        try:
            qr_bands = _bands_fn()
        except Exception:  # never let a parse quirk break the feed
            qr_bands = None
    if qr_bands:
        return [
            {
                "supplier_hash": sh, "iva_code": iva, "month": month, "invoice_count": 1,
                "total_net": _signed_round(v["net"]), "total_tax": _signed_round(v["tax"]),
                "total_gross": _signed_round(v["gross"]),
            }
            for iva, v in qr_bands.items()
        ]

    # FALLBACK: line-item summation classified by each line's tax_rate.
    groups: dict = {}
    for item in getattr(unified, "line_items", None) or []:
        iva = classify_iva(getattr(item, "tax_rate", None))
        g = groups.setdefault(iva, {"net": 0.0, "tax": 0.0, "gross": 0.0})
        g["net"] += float(getattr(item, "net_amount", 0) or 0)
        g["tax"] += float(getattr(item, "tax_amount", 0) or 0)
        g["gross"] += float(getattr(item, "gross_amount", 0) or 0)
    return [
        {
            "supplier_hash": sh, "iva_code": iva, "month": month, "invoice_count": 1,
            "total_net": _signed_round(v["net"]), "total_tax": _signed_round(v["tax"]),
            "total_gross": _signed_round(v["gross"]),
        }
        for iva, v in groups.items()
    ]


def _push_profiling_feed(job_id: str, unified) -> None:
    """POST pseudonymous monthly aggregates to the portal (best-effort, never raises).

    SEPARATE from _push_status so a feed failure can NEVER disturb the status channel
    (smaller blast radius). Called after the success status push.
    """
    try:
        rows = _aggregate_profiling(unified)
    except Exception as exc:  # aggregation must never break the dispatch flow
        logger.warning("Profiling aggregation failed for job %s: %s", job_id, exc)
        return
    if not rows:
        return
    api_key = os.getenv("VPS_ADMIN_API_KEY", "").strip()
    if not api_key:
        return
    try:
        import httpx

        resp = httpx.post(
            _PORTAL_PROFILING_FEED_URL,
            json={"job_id": job_id, "rows": rows},
            headers={"X-Admin-Key": api_key},
            timeout=30.0,
        )
        if resp.status_code == 200:
            logger.info("Profiling feed %s → %s", job_id, resp.json())
        else:
            logger.warning(
                "Profiling feed %s → HTTP %s: %s", job_id, resp.status_code, resp.text[:200]
            )
    except Exception as exc:  # best-effort — parsing must not depend on portal reachability
        logger.warning("Profiling feed push %s failed: %s", job_id, exc)


def _mark_failed(pdf_path: Path) -> None:
    """Drop a sibling ``.failed`` marker so the poll loop won't reprocess a dead PDF.

    A terminally-failed PDF stays in outbox (audit / manual retry) but is skipped on
    the next scan — without this, a poll loop re-parses + re-POSTs it forever (DA-A3).
    """
    try:
        pdf_path.with_suffix(pdf_path.suffix + ".failed").touch()
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not write .failed marker for %s: %s", pdf_path, exc)


def _mark_done(pdf_path: Path) -> None:
    """Drop a sibling ``.done`` marker after a successful parse — RETAIN the PDF.

    S175 §10/1: replaces the old parse-time ``unlink()``. The raw PDF stays in outbox
    so the lifecycle downstream of parse can use it (book-keeper D1 "Ver original",
    HITL review, reprocess, audit). The destruction-sweep (S175 §10/5) removes it at
    ``release + 48h``. The marker stops the poll loop re-parsing the retained PDF.
    Mirrors ``_mark_failed`` — swallows its own error so it never falls through to a
    false ``.failed``; if the touch fails, the next scan self-heals via the idempotent
    ``job_id`` upsert.
    """
    try:
        pdf_path.with_suffix(pdf_path.suffix + ".done").touch()
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not write .done marker for %s: %s", pdf_path, exc)


def _has_terminal_marker(pdf_path: Path) -> bool:
    """True if a sibling ``.done`` / ``.failed`` / ``.destroyed`` marker exists.

    Explicit sibling check (NOT a glob — DA-K1) so a marker file can never be mistaken
    for a processable PDF. Used by both the poll path (``scan_once``) and the watch path
    (``on_created``) so neither re-parses an already-handled PDF (DA-K2/K4). ``.destroyed``
    (S175 §10/5) marks a PDF whose bytes are gone but whose destruction fingerprint is kept
    locally for the NAS_DESTROYED POST-retry.
    """
    return (
        pdf_path.with_suffix(pdf_path.suffix + ".done").exists()
        or pdf_path.with_suffix(pdf_path.suffix + ".failed").exists()
        or pdf_path.with_suffix(pdf_path.suffix + ".destroyed").exists()
    )


def _sha256_file(path: Path) -> Optional[str]:
    """SHA-256 hexdigest of a file's bytes (streamed) — the S175 audit receipt fingerprint.

    DA-K7: one entity hashes one copy — the PC hashes the very file it is about to parse
    and retain. Best-effort: a read error returns None (the nas_stored push is then
    skipped) rather than aborting the parse.
    """
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not hash %s: %s", path, exc)
        return None


def _process_pdf(pdf_path: Path, session_factory=SessionLocal):
    """Run parsing pipeline on a single PDF, persist the decision, write result JSON.

    `session_factory` is injected for testability; it defaults to the real PC
    `pdf_parsing_db` factory so the watcher path persists the Constitution decision.
    """
    client_id, job_id = _parse_job_info(pdf_path)
    if not client_id or not job_id:
        logger.error("Cannot parse client/job from path: %s", pdf_path)
        return

    # Determine inbox path (sibling of outbox)
    inbox_dir = pdf_path.parent.parent / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    result_path = inbox_dir / f"{job_id}.json"

    # S175 §10/2: record the received raw PDF in the audit registry BEFORE parse — the
    # pdf_sha256 proves WHICH exact file we hold; the §10/5 NAS_DESTROYED re-hashes at
    # destruction (the two bracket the retention window). Emitted independently of parse
    # outcome (a failed parse still retains the file). Best-effort like every portal push.
    # nas_path is PII-free ({client_id}/{job_id}) — no filename crosses to portal_db.
    pdf_sha256 = _sha256_file(pdf_path)
    if pdf_sha256:
        _push_status(job_id, "nas_stored", pdf_sha256=pdf_sha256, nas_path=f"{client_id}/{job_id}")

    logger.info("Processing job %s for client %s", job_id, client_id)
    _push_status(job_id, "processing")  # D3: Pedro sees the work actually start
    start = datetime.utcnow()

    try:
        # Use the same pipeline as main_batch_processor (QR + Heuristic + Tier3)
        from main_batch_processor import process_single_invoice
        from parsing.heuristic_engine import HeuristicEngine

        try:
            from pdf_parser.qr_barcode_engine_v2 import QRBarcodeEngineV2

            qr_engine = QRBarcodeEngineV2()
        except ImportError:
            qr_engine = None
            logger.warning("QRBarcodeEngineV2 unavailable — Level 0 QR scan skipped")

        engine = HeuristicEngine(threshold=0.3)

        # R3 (S160): request the decision too so we can persist it. Early-failure
        # paths in process_single_invoice still return a bare None (not a tuple),
        # so guard before unpacking.
        outcome = process_single_invoice(
            pdf_path=pdf_path,
            engine=engine,
            qr_engine=qr_engine,
            return_decision=True,
        )

        elapsed = (datetime.utcnow() - start).total_seconds()

        if outcome is None:
            _write_result(result_path, job_id, "failed", error="Processing returned no data")
            _push_status(job_id, "done", error_code="NO_DATA")
            _mark_failed(pdf_path)
            return
        invoice_data, decision = outcome
        if invoice_data is None or decision is None:
            _write_result(result_path, job_id, "failed", error="Processing returned no data")
            _push_status(job_id, "done", error_code="NO_DATA")
            _mark_failed(pdf_path)
            return

        # R3 (S160): persist the Constitution decision to the PC SoT BEFORE signalling
        # completion. result.json is the rsync'd "completed" signal — never emit it if
        # the decision did not land in constitution_decisions (G1). A persist failure
        # falls through to the outer except → "failed" result.json; the PDF stays in
        # outbox and the next scan self-heals via the idempotent upsert (job_id).
        # R5b-1 (S164): persist the vps_clients.id (NAS path segment is a string;
        # the column is the integer vps id). A non-numeric segment is a NAS/config
        # error — store NULL (the decision still persists; the release producer
        # treats NULL as unresolvable, fail-closed) rather than losing the decision.
        try:
            client_id_int = int(client_id)
        except (TypeError, ValueError):
            client_id_int = None
            logger.warning(
                "Non-numeric client_id segment %r for job %s — persisting NULL", client_id, job_id
            )
        # S188 F1.2/F2.2: persist + PC döntés-kapu (atcud gate) + fallback dup_suspect +
        # window-sweep, all in the ONE persist session. `gate_result["suppressed"]` is True
        # iff THIS job's own decision got flipped to REJECTED_DUPLICATE by the gate.
        # `or {}`: a test-double (e.g. tests/dispatch/test_dispatch_watcher_done_marker.py)
        # may monkeypatch this to a bare no-op returning None — degrade to pre-S188 behaviour.
        gate_result = (
            _persist_decision_for_job(
                session_factory,
                job_id=job_id,
                decision=decision,
                unified=invoice_data,
                source_filename=pdf_path.name,
                client_id=client_id_int,
            )
            or {}
        )
        suppressed = gate_result.get("suppressed", False)

        # S178 §B-lánc (33 §8.3): persist the FULL parsed result to the encrypted NAS source store
        # so Pedro/Maria can later download per-(emission-)month files (the build sources it by job_id).
        # ORDER MATTERS (DA-K6): the decision (constitution_decisions, the SoT) is persisted ABOVE FIRST;
        # this runs AFTER it. BEST-EFFORT — a push failure must NEVER break the decision/status flow (a
        # reprocess re-pushes). Skips when client_id is non-numeric (unkeyable). The full invoice_data is
        # PC-ONLY class but the NAS source store is the no-cloud, ENCRYPTED tier (NOT the VPS).
        # S188: stays UNCONDITIONAL even when suppressed — this artifact is the "não é duplicado"
        # reprocess/false-positive lifeline (F4 ops-panel reprocess needs the source to still exist).
        _persist_result_source(job_id, client_id_int, invoice_data)

        # S182 F-V: PC-lokál desk-cache a HITL munkapad prefilljéhez (value_real). BEST-EFFORT,
        # a SoT-decision fölötte már commitolt. PC-only (nem VPS); a PDF-fel együtt törlődik (48h sweep + Art 17).
        # S188: KIMARAD, ha a döntés-kapu elnyomta (suppressed) — a doksi sosem megy desk-re, a
        # cache-nek nincs fogyasztója (F2 "HITL-sorba így be se kerül").
        if not suppressed:
            _persist_desk_cache(job_id, client_id_int, invoice_data, pdf_path)

        # P0 (S156): VPS-OK metadata ONLY — no raw invoice_data leaves the PC.
        # S188: result.json marad "completed" a suppressed ágon is — a job LEFUTOTT, a
        # portál-oldali "review"→"error/Duplicado" váltást a lenti _push_status viszi.
        result = _completed_result_payload(job_id, client_id, result_path, elapsed)
        _write_result(result_path, job_id, "completed", data=result)
        logger.info("Job %s completed in %.1fs → %s", job_id, elapsed, result_path)

        # D3 (S168): mirror the engine decision to the portal so Pedro sees the real
        # outcome (completed/review/Duplicado). The release-gate veil still hides downloadable
        # results until the operator releases — this only drives the lifecycle status.
        # S188 F1.2: decision_status/confidence come from the GATE result (may be the
        # REJECTED_DUPLICATE override, not the raw engine decision) + masked rejection-context
        # (previous_date/duplicate_of_job_id — not PII, K7-OK; §V/1 "a" option) so the portal
        # can render the "já recebida em ..." template instead of a bare "Rejeitado".
        from services.decision_status import to_canonical

        _push_status(
            job_id,
            "done",
            decision_status=gate_result.get("status") or to_canonical(decision.status),
            confidence=float(gate_result.get("confidence") or decision.confidence),
            # S188 fix (walk-lelet): a suppress-ág KÜLDJE a reason_code-ot is — az
            # apply_file_status a set_rejection-t (context + a FE "Duplicado"/"já recebida"
            # render) a `rejection_reason_code == "DUPLICATE"`-hez köti; enélkül Pedro csak
            # csupasz REJECTED_DUPLICATE-et lát (a hard-skip-út közvetlenül írja, ez a D3-út
            # eddig kihagyta).
            rejection_reason_code="DUPLICATE" if suppressed else None,
            previous_date=gate_result.get("previous_date"),
            duplicate_of_job_id=gate_result.get("duplicate_of_job_id"),
        )

        # S172 F-B: feed pseudonymous monthly profiling aggregates to the portal AFTER
        # the status push (separate channel, best-effort — never disturbs the status flow).
        # S188: KIMARAD suppressed dupra — a dupla-számolás torzítaná a havi aggregátumot
        # (a számla adatai már szerepelnek az EREDETI, nem-elnyomott feldolgozásban).
        if not suppressed:
            _push_profiling_feed(job_id, invoice_data)

        # S175 §10/1: RETAIN the processed PDF for the lifecycle (book-keeper D1
        # "Ver original", HITL review, reprocess, audit) instead of unlink()-ing it
        # here — that deleted the raw PDF before anyone downstream of parse could use
        # it ("lábon lövés"). The .done marker stops the poll loop re-parsing it; the
        # destruction-sweep (S175 §10/5) removes it at release + 48h. The decision is
        # already persisted above (G1), so .done means "parse + decision complete".
        _mark_done(pdf_path)

    except Exception as exc:
        logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
        _write_result(result_path, job_id, "failed", error=str(exc))
        _push_status(job_id, "done", error_code="PROCESSING_FAILED")
        _mark_failed(pdf_path)


def _write_result(path: Path, job_id: str, status: str, error: str = "", data: dict = None):
    """Write result JSON atomically (tmp + rename)."""
    result = data or {
        "status": status,
        "job_id": job_id,
        "error": error,
        "processed_at": datetime.utcnow().isoformat(),
    }
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    tmp_path.rename(path)


def _persist_result_source(job_id: str, client_id_int, invoice_data) -> None:
    """S178 §B-lánc: write the full UnifiedInvoiceData as JSONL and push to the encrypted NAS
    source store ({client_id}/{job_id}.jsonl). BEST-EFFORT — never raises (the decision/status
    flow already committed). Skips when client_id is non-numeric (unkeyable on the NAS path)."""
    if client_id_int is None or invoice_data is None:
        return
    tmp = None
    try:
        import tempfile
        from services import nas_sync
        from services.export_service import write_result_jsonl

        # Unique temp (DA-K1): a bare {job_id}_result.jsonl would collide if the same job_id is
        # ever processed concurrently (retry/race) → corrupt JSONL. The NAS filename stays {job_id}.jsonl.
        _fd, _tmp_name = tempfile.mkstemp(prefix=f"{job_id}_", suffix="_result.jsonl")
        os.close(_fd)
        tmp = Path(_tmp_name)
        write_result_jsonl(invoice_data, str(tmp))
        nas_sync.push_result_source(tmp, client_id_int, job_id)
        logger.info("B-lánc source-JSONL pushed for job %s (client %s)", job_id, client_id_int)
    except Exception as exc:  # noqa: BLE001 — best-effort; the SoT/status is unaffected
        logger.warning(
            "B-lánc source-JSONL persist failed (non-blocking) job=%s: %s", job_id, exc
        )
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def _persist_desk_cache(job_id: str, client_id_int, invoice_data, pdf_path: Path) -> None:
    """S182 F-V: PC-LOKÁL desk-cache JSONL a HITL Bancada de Correção prefilljéhez (value_real).

    Hely: ``{client_id}/_desk/{job_id}.jsonl`` (az outbox testvér-fája, AZONOS K7-scope + AZONOS
    nas-sync NAS-tier mint a retained PDF; a VPS-re SOHA nem megy — oda csak az inbox/{job_id}.json,
    maszkolva). A teljes (UNMASKED) UnifiedInvoiceData (``serialize_unified``). Adat-minimalizálás
    (Art 5(1)(c)): a TELJES rekord az operátor kontextus-megjelenítéséhez kell (teljes számla + tételsorok),
    nem csak a flagged subset — lásd docs/legal ROPA §2.21.

    Lifecycle = a retained PDF TÜKRE: itt születik, és a ``_destroy_and_mark`` (release+48h sweep) ÉS a
    fiók-törlés (Art 17, account_deletion_service) törli — GDPR-ekvivalens a PDF-fel. BEST-EFFORT
    (a decision/status SoT fölötte már commitolt → egy cache-hiba SOHA nem törheti meg a flow-t).
    Atomic (DA-K4): temp az AZONOS dir-ben → ``os.replace`` (nincs torn-read párhuzamos reprocess-en).
    """
    if client_id_int is None or invoice_data is None:
        return
    import tempfile

    from services.export_service import write_result_jsonl

    tmp = None
    try:
        desk_dir = pdf_path.parent.parent / "_desk"
        desk_dir.mkdir(parents=True, exist_ok=True)
        dest = desk_dir / f"{job_id}.jsonl"
        _fd, _tmp_name = tempfile.mkstemp(prefix=f"{job_id}_", suffix=".jsonl.tmp", dir=str(desk_dir))
        os.close(_fd)
        tmp = Path(_tmp_name)
        write_result_jsonl(invoice_data, str(tmp))
        os.replace(str(tmp), str(dest))  # atomic same-dir rename
        tmp = None  # consumed
        logger.info("F-V desk-cache written for job %s (client %s)", job_id, client_id_int)
    except Exception as exc:  # noqa: BLE001 — best-effort; the SoT/status is unaffected
        logger.warning("F-V desk-cache persist failed (non-blocking) job=%s: %s", job_id, exc)
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def scan_once(watch_dir: str):
    """Single pass: find all PDFs in outbox dirs, process them."""
    base = Path(watch_dir)
    if not base.exists():
        logger.error("Watch directory does not exist: %s", base)
        return

    # Skip PDFs already handled — a sibling .done marker (parsed, retained for the
    # lifecycle: S175 §10/1) or a .failed marker (terminally dead, kept for audit /
    # manual retry). Without this the poll loop would re-parse + re-POST forever (DA-A3).
    pdfs = [
        p
        for p in base.glob("*/outbox/*.pdf")
        if not _has_terminal_marker(p)
    ]
    logger.info("Found %d unprocessed PDFs in outbox directories", len(pdfs))
    for pdf_path in pdfs:
        _process_pdf(pdf_path)


# ─── S175 §10/5: destruction-sweep (delete retained raw PDF at release+48h) ──
# The PC owns the physical deletion (NAS sync source → the delete "sticks", the NAS
# follows). It asks the portal which files are due (GET /destruction-due, fail-closed), and
# a portal-INDEPENDENT max-retention fail-safe force-deletes any .done PDF older than the
# cap so the 48h promise holds even through a portal outage. Each delete re-hashes the file
# (destruction fingerprint) → POST phase=nas_destroyed → the portal compares it to the
# NAS_STORED receipt (match → NAS_DESTROYED, else NAS_DESTROY_FAILED + alert). The local
# .destroyed sidecar keeps the fingerprint for a POST-retry so a portal hiccup never leaves
# a "deleted but unrecorded" audit gap.


def _destroyed_sidecar(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(pdf_path.suffix + ".destroyed")


def _write_destroyed_sidecar(pdf_path: Path, sha256: str, *, posted: bool = False) -> None:
    """Atomically (temp + os.replace) write the destruction fingerprint sidecar (DA-K2)."""
    sidecar = _destroyed_sidecar(pdf_path)
    tmp = sidecar.with_suffix(sidecar.suffix + ".tmp")
    data = {"sha256": sha256, "destroyed_at": datetime.utcnow().isoformat(), "posted": posted}
    try:
        tmp.write_text(json.dumps(data))
        os.replace(tmp, sidecar)  # atomic on the same filesystem
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not write .destroyed sidecar for %s: %s", pdf_path, exc)


def _read_destroyed_sidecar(pdf_path: Path) -> Optional[dict]:
    sidecar = _destroyed_sidecar(pdf_path)
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text())
    except Exception:  # pragma: no cover - defensive
        return None


def _mark_sidecar_posted(pdf_path: Path) -> None:
    data = _read_destroyed_sidecar(pdf_path) or {}
    if data.get("posted"):
        return
    sha = data.get("sha256")
    if sha:
        _write_destroyed_sidecar(pdf_path, sha, posted=True)


def _destroy_and_mark(pdf_path: Path) -> Optional[str]:
    """Re-hash → delete the raw PDF → write the .destroyed sidecar. Returns the hash.

    Hash BEFORE delete (the fingerprint proves WHICH file we destroyed). On a hash or
    delete error returns None (the caller posts file_absent / skips) rather than leaving a
    half-state. The .done marker is removed (.destroyed is now the terminal marker).
    """
    sha = _sha256_file(pdf_path)
    if sha is None:
        logger.warning("Could not hash before destroy (skipping): %s", pdf_path)
        return None
    try:
        pdf_path.unlink()
    except FileNotFoundError:
        pass  # already gone (race) — we still hold the fingerprint we just computed
    except Exception as exc:
        logger.error("Could not delete %s: %s", pdf_path, exc)
        return None
    _write_destroyed_sidecar(pdf_path, sha, posted=False)
    try:
        pdf_path.with_suffix(pdf_path.suffix + ".done").unlink(missing_ok=True)
    except Exception:  # pragma: no cover - defensive
        pass
    # S182 F-V: the unmasked desk-cache (GDPR-equivalent to the PDF) dies WITH the PDF.
    try:
        _job_id = pdf_path.name.split("_", 1)[0]  # {job_id}_{name}.pdf → job_id (uuid4, no '_')
        (pdf_path.parent.parent / "_desk" / f"{_job_id}.jsonl").unlink(missing_ok=True)
    except Exception:  # pragma: no cover - defensive, best-effort
        pass
    return sha


def _get_destruction_due(retention_hours: int = 48) -> Optional[list]:
    """GET the portal destruction-due worklist. Returns the list, or None on any failure.

    None = fail-closed: the portal is unreachable / unauthorised, so the portal-driven
    deletes are skipped this cycle (never delete blind). An empty list = portal reached,
    nothing due. The max-retention fail-safe runs regardless (it does not call this).
    """
    api_key = os.getenv("VPS_ADMIN_API_KEY", "").strip()
    if not api_key:
        logger.warning("VPS_ADMIN_API_KEY unset — skipping portal-driven destruction sweep")
        return None
    try:
        import httpx

        resp = httpx.get(
            _PORTAL_DESTRUCTION_DUE_URL,
            params={"retention_hours": retention_hours},
            headers={"X-Admin-Key": api_key},
            timeout=30.0,
        )
        if resp.status_code == 200:
            return resp.json().get("due", [])
        logger.warning("destruction-due → HTTP %s: %s", resp.status_code, resp.text[:200])
        return None
    except Exception as exc:  # best-effort — fail-closed on unreachable portal
        logger.warning("destruction-due fetch failed: %s", exc)
        return None


def _destruction_poster(job_id: str, nas_path: str, sha256: Optional[str], file_absent: bool) -> bool:
    """POST phase=nas_destroyed to the portal. Returns True iff the portal applied it."""
    api_key = os.getenv("VPS_ADMIN_API_KEY", "").strip()
    if not api_key:
        return False
    payload = {"job_id": job_id, "phase": "nas_destroyed", "nas_path": nas_path}
    if file_absent:
        payload["file_absent"] = True
    elif sha256:
        payload["pdf_sha256"] = sha256
    try:
        import httpx

        resp = httpx.post(
            _PORTAL_STATUS_URL, json=payload, headers={"X-Admin-Key": api_key}, timeout=30.0
        )
        if resp.status_code == 200:
            return bool(resp.json().get("applied"))
        logger.warning("nas_destroyed %s → HTTP %s: %s", job_id, resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.warning("nas_destroyed POST %s failed: %s", job_id, exc)
        return False


def _outbox_pdf_for(base: Path, client_id: str, job_id: str) -> Optional[Path]:
    """Locate the local synced PDF by job_id (uuid, no '_' → glob is unambiguous, DA-K3)."""
    outbox = base / str(client_id) / "outbox"
    if not outbox.exists():
        return None
    matches = sorted(outbox.glob(f"{job_id}_*.pdf"))
    return matches[0] if matches else None


def _outbox_destroyed_pdf_for(base: Path, client_id: str, job_id: str) -> Optional[Path]:
    """Locate the (gone) PDF path whose ``.destroyed`` sidecar survives, by job_id glob.

    Used when the raw PDF is already deleted but its destruction fingerprint must be
    re-POSTed — the sidecar carries the real filename, so we glob ``{job_id}_*.pdf.destroyed``
    and strip the marker suffix back to the original PDF path.
    """
    outbox = base / str(client_id) / "outbox"
    if not outbox.exists():
        return None
    matches = sorted(outbox.glob(f"{job_id}_*.pdf.destroyed"))
    return matches[0].with_suffix("") if matches else None  # strip .destroyed


def _sweep_one_due(base: Path, item: dict, poster, stats: dict, handled: set) -> None:
    """Destroy (or re-post) one portal due-item. nas_path is PII-free {client_id}/{job_id}."""
    job_id = item.get("job_id")
    nas_path = item.get("nas_path") or ""
    if not job_id or "/" not in nas_path:
        return
    client_id = nas_path.split("/", 1)[0]
    handled.add(job_id)
    pdf_path = _outbox_pdf_for(base, client_id, job_id)

    if pdf_path is not None:
        sha = _destroy_and_mark(pdf_path)
        if sha is None:
            stats["errors"] += 1
            return
        if poster(job_id, nas_path, sha, False):
            _mark_sidecar_posted(pdf_path)
        stats["portal_deleted"] += 1
        return

    # PDF already gone — re-post from the sidecar fingerprint if we have it, else file_absent.
    gone_pdf = _outbox_destroyed_pdf_for(base, client_id, job_id)
    sidecar = _read_destroyed_sidecar(gone_pdf) if gone_pdf is not None else None
    if sidecar and sidecar.get("sha256"):
        if poster(job_id, nas_path, sidecar["sha256"], False):
            _mark_sidecar_posted(gone_pdf)
        stats["retried"] += 1
    else:
        poster(job_id, nas_path, None, True)  # cannot verify — portal emits NAS_DESTROY_FAILED
        stats["file_absent"] += 1


def run_destruction_sweep(
    watch_dir: str,
    *,
    retention_hours: int = 48,
    max_retention_hours: int = 168,
    get_due_fn=None,
    poster=None,
    now: Optional[datetime] = None,
) -> dict:
    """One destruction-sweep pass (S175 §10/5). Injectable get_due_fn/poster for tests.

    1. Portal-driven: delete files the portal lists as released+retention_hours (fail-closed
       — a None due-list skips this step, never deletes blind).
    2. Max-retention fail-safe (portal-INDEPENDENT): force-delete any .done PDF whose mtime is
       older than max_retention_hours so the 48h promise survives a portal outage.
    3. Sidecar-retry: re-POST any .destroyed sidecar whose earlier POST never confirmed.
    """
    now = now or datetime.utcnow()
    get_due_fn = get_due_fn or (lambda: _get_destruction_due(retention_hours))
    poster = poster or _destruction_poster
    stats = {
        "portal_deleted": 0, "failsafe_deleted": 0, "retried": 0,
        "file_absent": 0, "errors": 0, "portal_skipped": False,
    }
    base = Path(watch_dir)
    if not base.exists():
        logger.error("Destruction sweep: watch dir does not exist: %s", base)
        return stats
    handled: set = set()

    # 1. Portal-driven.
    due = get_due_fn()
    if due is None:
        stats["portal_skipped"] = True
        logger.warning("Destruction sweep: portal unreachable — portal-driven deletes skipped")
    else:
        for item in due:
            try:
                _sweep_one_due(base, item, poster, stats, handled)
            except Exception as exc:
                stats["errors"] += 1
                logger.error("Destruction sweep due-item failed: %s", exc, exc_info=True)

    # 2. Max-retention fail-safe (portal-independent).
    cutoff_ts = now.timestamp() - max_retention_hours * 3600
    for pdf_path in base.glob("*/outbox/*.pdf"):
        if not pdf_path.with_suffix(pdf_path.suffix + ".done").exists():
            continue
        if _destroyed_sidecar(pdf_path).exists():
            continue
        try:
            if pdf_path.stat().st_mtime > cutoff_ts:
                continue
        except OSError:
            continue
        client_id, job_id = _parse_job_info(pdf_path)
        if not job_id:
            continue
        handled.add(job_id)
        sha = _destroy_and_mark(pdf_path)
        if sha is None:
            stats["errors"] += 1
            continue
        if poster(job_id, f"{client_id}/{job_id}", sha, False):
            _mark_sidecar_posted(pdf_path)
        stats["failsafe_deleted"] += 1
        logger.info("Fail-safe destroyed (>%dh): %s", max_retention_hours, job_id)

    # 3. Sidecar-retry (POSTs that never confirmed; skip what we just handled).
    for sidecar in base.glob("*/outbox/*.pdf.destroyed"):
        pdf_path = sidecar.with_suffix("")  # strip .destroyed → ..._{name}.pdf
        data = _read_destroyed_sidecar(pdf_path)
        if not data or data.get("posted") or not data.get("sha256"):
            continue
        client_id, job_id = _parse_job_info(pdf_path)
        if not job_id or job_id in handled:
            continue
        if poster(job_id, f"{client_id}/{job_id}", data["sha256"], False):
            _mark_sidecar_posted(pdf_path)
            stats["retried"] += 1

    logger.info("Destruction sweep done: %s", stats)
    return stats


def watch(watch_dir: str):
    """Start filesystem watcher on the sync directory."""
    if Observer is None:
        logger.error("Continuous watch mode requires the 'watchdog' package (not installed). "
                     "Use --once for a single scan, or install watchdog.")
        sys.exit(1)
    base = Path(watch_dir)
    if not base.exists():
        logger.error("Watch directory does not exist: %s", base)
        sys.exit(1)

    handler = PDFHandler()
    observer = Observer()
    observer.schedule(handler, str(base), recursive=True)
    observer.start()
    logger.info("Watching %s for new PDFs (Ctrl+C to stop)", base)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    logger.info("Watcher stopped")


def main():
    parser = argparse.ArgumentParser(description="Dispatch Watcher — PDF processing trigger")
    parser.add_argument(
        "--watch-dir", default=DEFAULT_WATCH_DIR, help="NAS sync client sync directory"
    )
    parser.add_argument("--once", action="store_true", help="Single scan, no continuous watching")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=0,
        help="Poll the outbox every N seconds (DrvFs-safe glob scan; 0 = off). "
        "Preferred over --watch on WSL2/DrvFs where inotify is unreliable.",
    )
    # S175 §10/5 destruction-sweep mode (SEPARATE from the parse modes — run as its own
    # compose service for failure isolation; needs only VPS_ADMIN_API_KEY + the watch dir).
    parser.add_argument("--sweep", action="store_true", help="Run one destruction sweep, then exit")
    parser.add_argument(
        "--sweep-interval", type=int, default=0, help="Loop the destruction sweep every N seconds"
    )
    parser.add_argument("--retention-hours", type=int, default=48, help="release+N → destroy")
    parser.add_argument(
        "--max-retention-hours", type=int, default=168,
        help="Portal-independent fail-safe cap (default 7 days; PP names this maximum)",
    )
    args = parser.parse_args()

    # Destruction-sweep mode: no PC DB / profiler needed (HTTP + filesystem only) → skip
    # init_db + salt validation so the sweep container stays minimal and isolated.
    if args.sweep or (args.sweep_interval and args.sweep_interval > 0):
        if os.getenv("DISABLE_DESTRUCTION_SWEEP") == "1":
            logger.info("Destruction sweep disabled (DISABLE_DESTRUCTION_SWEEP=1)")
            return
        kwargs = dict(
            retention_hours=args.retention_hours, max_retention_hours=args.max_retention_hours
        )
        if args.sweep_interval and args.sweep_interval > 0:
            logger.info("Destruction sweep: every %ds (%s)", args.sweep_interval, args.watch_dir)
            while True:
                try:
                    run_destruction_sweep(args.watch_dir, **kwargs)
                except Exception as exc:  # one bad sweep must not kill the loop
                    logger.error("run_destruction_sweep failed: %s", exc, exc_info=True)
                time.sleep(args.sweep_interval)
        else:
            run_destruction_sweep(args.watch_dir, **kwargs)
        return

    # Standalone process: bootstrap the global DB manager (the FastAPI app does this
    # at startup; the watcher must do it itself before persist_decision opens a session).
    # create_tables=False — the pdf_parsing_db schema is owned by alembic, not the watcher.
    init_db(create_tables=False)

    # F-SH (S170): fail-fast if PSEUDONYM_SALT is default/short — the dispatch service
    # runs the profiler via process_single_invoice (supplier-hash must never use the
    # brute-forceable default salt). Respects the dev-insecure opt-in.
    from services.secrets_validator import validate_pseudonym_salt

    validate_pseudonym_salt()

    if args.poll_interval and args.poll_interval > 0:
        # DrvFs-safe production loop (the worker_fast image ships no watchdog, and
        # inotify doesn't propagate from the Windows host into WSL2 anyway).
        logger.info("Poll mode: scanning %s every %ds", args.watch_dir, args.poll_interval)
        while True:
            try:
                scan_once(args.watch_dir)
            except Exception as exc:  # one bad scan must not kill the loop
                logger.error("scan_once failed: %s", exc, exc_info=True)
            time.sleep(args.poll_interval)
    elif args.once:
        scan_once(args.watch_dir)
    else:
        # Run initial scan, then watch (inotify — host/CI only)
        scan_once(args.watch_dir)
        watch(args.watch_dir)


if __name__ == "__main__":
    main()
