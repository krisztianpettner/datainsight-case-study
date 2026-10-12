"""
qr_reconcile.py — S182: a QR mint VALIDÁTOR (nem 1.0-pontforrás).

A `candidates` dict-ből EGY kanonikus mezőre (a `field_catalog` slot-aliasán át) kigyűjti a
QR-olvasatot ÉS a vizuális (tier2/ocr/llm) olvasatot, és a `normalize_compare.compare`-rel
összeveti. A QR az AT-hitelesített, gépi-olvasatú per-dokumentum oracle → ha a vizuális
EGYEZIK vele, az erős azonosság-bizonyíték; ha ELTÉR, AUTOMATIKUS piros zászló (a QR a
hiteles, tehát az eltérés majdnem biztosan OCR/parse-hiba). → ez oldja fel az
`feedback_anti_pseudo_metric_qr_checksum` aggályt: a QR nem ad pontot magától, MEGERŐSÍT.

A WEAK-klaszter (utility/multi-doc) sajátja, hogy EGY sloton TÖBB, egymással NEM egyező
QR-candidate van (konszolidált multi-doc) → ezt `multi_qr` jelzi (multi-doc = NEM tiszta →
nem auto-grade). A vizuális oldal zajos lehet (sok candidate) → match-ANY a QR ellen.

Pure stdlib, dep-mentes. Pure-unit tesztelhető szintetikus candidate-szettekkel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

from parsing.identity import normalize_compare as nc
from parsing.identity.field_catalog import CatalogEntry
from parsing.identity.normalize_compare import Verdict

_QR_SOURCE = "qr"


@dataclass
class Reconcile:
    field: str                      # kanonikus mező-név
    verifiable_class: str           # "a"|"b"|"c" (a katalógusból)
    field_type: str
    qr_value: Any                   # a (single) QR-olvasat, vagy None
    visual_value: Any               # a MATCH-elő (vagy első) vizuális olvasat, vagy None
    verdict: Verdict                # a reconcile kimenete (INSUFFICIENT ha nincs 2 független olvasat)
    independent: bool               # volt-e EGY-egy QR ÉS vizuális olvasat
    multi_qr: bool = False          # ≥2 egyet-nem-értő QR-candidate (multi-doc jel)
    n_qr: int = 0
    n_visual: int = 0


def _collect(candidates: dict, slots: List[str], *, want_qr: bool) -> List[Any]:
    """A megadott slotokból kigyűjti a candidate-értékeket, source-szerint szűrve."""
    out: List[Any] = []
    for slot in slots:
        for cand in (candidates.get(slot) or []):
            src = (getattr(cand, "source", "") or "").lower()
            is_qr = src == _QR_SOURCE
            if want_qr and is_qr:
                out.append(getattr(cand, "value", None))
            elif (not want_qr) and (not is_qr):
                out.append(getattr(cand, "value", None))
    return out


def _distinct_canonical(field_type: str, values: List[Any]) -> List[Any]:
    """A kanonikusan KÜLÖNBÖZŐ értékek (None-ok kiszűrve)."""
    seen = []
    for v in values:
        cv = nc.canonicalize(field_type, v)
        if cv is None:
            continue
        if cv not in [nc.canonicalize(field_type, s) for s in seen]:
            seen.append(v)
    return seen


def reconcile_field(entry: CatalogEntry, candidates: dict) -> Reconcile:
    """Egy kanonikus mező QR↔vizuális reconcile-ja a slot-aliasán át."""
    ft = entry.field_type
    # QR-olvasat csak a qr_slots-ból; vizuális a visual_slots ÉS a qr_slots nem-qr forrásaiból
    qr_raw = _collect(candidates, entry.qr_slots, want_qr=True)
    visual_raw = _collect(candidates, list({*entry.visual_slots, *entry.qr_slots}), want_qr=False)

    qr_distinct = _distinct_canonical(ft, qr_raw)
    visual_distinct = _distinct_canonical(ft, visual_raw)

    # QR „nincs adat" sentinel (pl. atcud anchor='0' = nincs ATCUD): NEM QR-olvasat → ne MISMATCH-eljen.
    if entry.qr_absent:
        qr_distinct = [v for v in qr_distinct
                       if nc.canonicalize(ft, v) not in entry.qr_absent]

    base = dict(
        field=entry.canonical, verifiable_class=entry.verifiable_class, field_type=ft,
        n_qr=len(qr_distinct), n_visual=len(visual_distinct),
    )

    # ── multi-doc: ≥2 egyet-nem-értő QR-candidate egy sloton ──
    if len(qr_distinct) > 1:
        return Reconcile(qr_value=qr_distinct[0], visual_value=(visual_distinct[0] if visual_distinct else None),
                         verdict=Verdict.MISMATCH, independent=bool(visual_distinct),
                         multi_qr=True, **base)

    qr_val = qr_distinct[0] if qr_distinct else None

    # ── csak egy oldal van → nincs független reconcile ──
    if qr_val is None or not visual_distinct:
        return Reconcile(qr_value=qr_val,
                         visual_value=(visual_distinct[0] if visual_distinct else None),
                         verdict=Verdict.INSUFFICIENT, independent=False, **base)

    # ── két független olvasat → match-ANY a QR ellen ──
    best = Verdict.MISMATCH
    matched_visual = visual_distinct[0]
    for vv in visual_distinct:
        v = nc.compare(ft, qr_val, vv)
        if v == Verdict.MATCH:
            best, matched_visual = Verdict.MATCH, vv
            break
        if v == Verdict.POSSIBLE and best == Verdict.MISMATCH:
            best, matched_visual = Verdict.POSSIBLE, vv
    return Reconcile(qr_value=qr_val, visual_value=matched_visual,
                     verdict=best, independent=True, **base)
