"""
field_identity.py — S182: a per-mező `identity_estimate` (verifikáció-először becslés)
+ a dokumentum-szintű aggregate.

Ez a vak conf% (QR-jelenlét-proxy) HELYÉRE lépő mutató magja (design §5.1 + a 3-szintű
hierarchia §11 I.+II. szintje; a III. Soft Signals KIZÁRVA a pilotból). A becslés:

  van független (a)/(b) reconcile (QR↔vizuális §4-normalizálva):
      MATCH     → estimate ≈ felső plafon (PROVEN_MATCH)
      POSSIBLE  → közepes (a munkapad-front)
      MISMATCH  → alacsony + hard_veto  (a QR az AT-hiteles → az eltérés OCR/parse-hiba)
  multi-doc (≥2 egyet-nem-értő QR)  → alacsony + hard_veto (NEM tiszta → nem auto-grade)
  NINCS független reconcile (egy-forrású):
      estimate = KALIBRÁLATLAN candidate.confidence, a proven-plafon ALÁ vágva
      (Fázis 1 placeholder; a VALÓDI Mondrian-konformális kalibráció = Fázis 3; H6)

A checksum/aritmetika a `constraint_results`-ból jön (NIFChecksum/FinancialTriangle/
QRConsistency/ATCUDMatch már léteznek — NEM duplikáljuk, beolvassuk → K6 mapping).

⚠️ Az estimate-SZINTEK (0.99/0.60/0.20…) FÁZIS-1 FIX értékek; a Fázis 3 kalibráció
(per-mező-típus α, RAPS/APS) váltja ki őket. A doc-kapu Fázis 1-ben NEM él (H1 auto-approve OFF).

Pure stdlib, dep-mentes. Pure-unit tesztelhető.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, List, Optional

from parsing.identity import field_catalog
from parsing.identity.field_catalog import CatalogEntry, CRITICAL_FIELDS
from parsing.identity.normalize_compare import Verdict
from parsing.identity.qr_reconcile import Reconcile, reconcile_field

# ── Fázis-1 fix estimate-szintek (Fázis 3 kalibráció váltja ki) ────────────
PROVEN_MATCH = 0.99       # független reconcile MATCH
POSSIBLE_EST = 0.60       # független reconcile POSSIBLE (munkapad-front)
MISMATCH_EST = 0.20       # független reconcile MISMATCH / multi-doc
VETO_EST = 0.10           # constraint-hard-veto (checksum/triangle fail)
SINGLE_SOURCE_CAP = 0.95  # egy-forrású plafon (sosem éri el a proven-plafont — H6)
SOFT_CONSTRAINT_CAP = 0.50  # soft constraint (pl. Date Range / medium)

# K6: constraint_name → kanonikus mező, amit vétóz (vagy a result.field-alapú almap)
_CONSTRAINT_FIELD_MAP = {
    "NIF Checksum": {"tax_id": "supplier_nif", "customer_tax_id": "customer_nif"},
    "ATCUD Match": "atcud",
    "QR Consistency": "total_with_vat",
    "Financial Triangle": "total_with_vat",   # critical → a totál-láncot (gross) vétózza = globális hatás
    "Date Range": "issue_date",
    # S190: a vevő országa konstans-elvárás (PT). A constraint `field`-je None, ezért a leképezés
    # a NEVÉBŐL történik → piros sáv a `customer_country`-n, a doc-státusz mozdítása nélkül.
    "Customer Country": "customer_country",
    # S213 (L2): a szállító-NIF sentinel-vétó. Almap-forma, mert a constraint a NYERS slotot
    # adja vissza `field`-ként (QR: tax_id / vizuális: seller_nif) — mindkettő ugyanarra a
    # kanonikus mezőre képez. ⚠️ A `supplier_nif` KRITIKUS → a hard_veto a doc-confot 0.0-ra
    # viszi (a Customer Country-val ellentétben, ami nem kritikus mezőt vétóz). Szándékos.
    "Supplier NIF Sentinel": {"tax_id": "supplier_nif", "seller_nif": "supplier_nif"},
    # S215 (C①): a szállító- és vevő-NIF azonossága. A constraint `field`-je SZÁNDÉKOSAN None
    # (nem tudjuk, melyik a hibás → HITL_FULL), ezért a leképezés a NEVÉBŐL történik — a
    # `Customer Country` mintája szerint.
    # ⚠️ MIÉRT a `supplier_nif`, ha a mérés szerint gyakrabban a VEVŐ a hibás (27-ből 17-ben a
    # szállító helyes)? Mert a piros sáv itt NEM azt állítja, hogy „ez az érték rossz", hanem
    # hogy „a szállító-azonosítás NEM MEGBÍZHATÓ, amíg az ellentmondás fennáll" — és ez mind a
    # 27 esetben igaz, akkor is, ha az érték véletlenül helyes. A `supplier_nif` KRITIKUS, tehát
    # a hard_veto a doc-confot 0.0-ra viszi: egy önmagának ellentmondó fejléc a Fázis 4-ben sem
    # lehet auto-approve (a kapu sarokkő-elve). Az operátort a HITL_FULL viszi a teljes fejléchez,
    # nem ez a sáv — a kettő szétválik (`fields_to_review` ≠ K6-térkép).
    "NIF Direction Ambiguity": "supplier_nif",
}
# HARD (teljes veto) vs SOFT (csak estimate-le) constraintek
# A `customer_country` NEM kritikus mező → a hard_veto piros sávot ad (felszínre hozza a deszken),
# de az `aggregate` doc-conf-ot NEM rántja le (az csak a kritikus mezőket nézi). Ez a „riasztás,
# nem elutasítás" szemantika.
_HARD_CONSTRAINTS = frozenset({"NIF Checksum", "ATCUD Match", "QR Consistency", "Financial Triangle",
                               "Customer Country", "Supplier NIF Sentinel",
                               # S215 (C①): HARD — az azonosság determinisztikus ellentmondás,
                               # nem valószínűségi jel. Kritikus mezőt vétóz → doc-conf 0.0.
                               "NIF Direction Ambiguity"})


@dataclass
class FieldIdentity:
    field: str                       # kanonikus mező-név
    value: Any                       # a kiválasztott érték (QR-elsőbbség, fallback vizuális)
    estimate: float                  # 0–1 (= az ÚJ conf%, per-mező)
    verdict: Verdict
    verifiable_class: str            # "a"|"b"|"c"
    hard_veto: bool                  # checksum/recon/aritmetika fail → kemény piros
    sources: List[str] = dc_field(default_factory=list)
    slots: List[str] = dc_field(default_factory=list)    # a nyers candidates-slotok (I5 write-back)
    breakdown: dict = dc_field(default_factory=dict)      # mely jel adta (debug; runtime-only, K8)
    critical: bool = False


def _max_conf_for_entry(candidates: dict, entry: CatalogEntry) -> float:
    """Az egy-forrású placeholder: a mező slotjainak max candidate.confidence-e."""
    confs = []
    for slot in (entry.qr_slots + entry.visual_slots):
        for cand in (candidates.get(slot) or []):
            c = getattr(cand, "confidence", None)
            if isinstance(c, (int, float)):
                confs.append(float(c))
    return max(confs) if confs else 0.5


def _sources_for_entry(candidates: dict, entry: CatalogEntry) -> List[str]:
    srcs = set()
    for slot in (entry.qr_slots + entry.visual_slots):
        for cand in (candidates.get(slot) or []):
            s = (getattr(cand, "source", "") or "").lower()
            if s:
                srcs.add(s)
    return sorted(srcs)


def compute_field(
    entry: CatalogEntry,
    rec: Reconcile,
    field_crs: List[Any],
    candidates: dict,
) -> FieldIdentity:
    """Egy kanonikus mező identity_estimate-je a reconcile + a rá vonatkozó constraintekből."""
    hard_veto = False
    breakdown = {
        "reconcile": rec.verdict.value,
        "independent": rec.independent,
        "multi_qr": rec.multi_qr,
        "n_qr": rec.n_qr,
        "n_visual": rec.n_visual,
    }

    # 1) reconcile-alapú alap-estimate
    if rec.multi_qr:
        estimate = MISMATCH_EST
        hard_veto = True
        breakdown["note"] = "multi-doc: ≥2 egyet-nem-értő QR-candidate"
    elif rec.independent:
        if rec.verdict == Verdict.MATCH:
            estimate = PROVEN_MATCH
        elif rec.verdict == Verdict.POSSIBLE:
            estimate = POSSIBLE_EST
        else:  # MISMATCH
            estimate = MISMATCH_EST
            hard_veto = True
    else:
        # egy-forrású → kalibrálatlan placeholder (Fázis 1), a proven-plafon alá vágva
        estimate = min(_max_conf_for_entry(candidates, entry), SINGLE_SOURCE_CAP)
        breakdown["placeholder"] = True

    # 2) constraint-override (K6): hard → veto + estimate-floor; soft → estimate-cap
    for cr in field_crs:
        name = getattr(cr, "constraint_name", None)
        if name in _HARD_CONSTRAINTS:
            hard_veto = True
            estimate = min(estimate, VETO_EST)
            breakdown.setdefault("hard_constraints", []).append(name)
        else:
            estimate = min(estimate, SOFT_CONSTRAINT_CAP)
            breakdown.setdefault("soft_constraints", []).append(name)

    value = rec.qr_value if rec.qr_value is not None else rec.visual_value
    return FieldIdentity(
        field=entry.canonical,
        value=value,
        estimate=round(estimate, 4),
        verdict=rec.verdict,
        verifiable_class=entry.verifiable_class,
        hard_veto=hard_veto,
        sources=_sources_for_entry(candidates, entry),
        # dedup: a co-lokált mezőknél (qr_slot==visual_slot) ne legyen duplikátum slot (DA-K2)
        slots=list(dict.fromkeys(entry.qr_slots + entry.visual_slots)),
        breakdown=breakdown,
        critical=entry.critical,
    )


def constraint_target_field(constraint_name: Optional[str]) -> Optional[str]:
    """A K6-térkép NÉV-alapú célmezője — publikus accessor a `field=None` constraintekhez.

    S215 (pre-commit DA, K1): a deszk KÉT FÜGGETLEN csatornán jeleníti meg egy constraint
    hatását — a piros sáv a K6-térképen át jön (`_index_constraints`), az INDOKLÓ SZÖVEG
    viszont a nyers `ConstraintResult.field`-en. Ahol a constraint szándékosan `field=None`
    (mert nem tudja, MELYIK mező a hibás — `NIF Direction Ambiguity`, `Customer Country`),
    ott a szöveg elveszett: az operátor **néma piros dobozt** látott.
    Ez az accessor teszi lehetővé, hogy az indoklás ugyanoda érkezzen, ahol a sáv van.

    Csak a string-formájú (név→mező) bejegyzést adja vissza; a dict-forma a nyers slotból
    képez, ahhoz `field` kell — ott nincs mit visszaadni.
    """
    target = _CONSTRAINT_FIELD_MAP.get(constraint_name)
    return target if isinstance(target, str) else None


def _index_constraints(constraint_results: List[Any]) -> dict:
    """Failed (high/critical/medium) constraintek → kanonikus mező → [ConstraintResult]."""
    by_field: dict = {}
    for cr in (constraint_results or []):
        if getattr(cr, "passed", True):
            continue
        name = getattr(cr, "constraint_name", None)
        target = _CONSTRAINT_FIELD_MAP.get(name)
        if target is None:
            continue
        if isinstance(target, dict):
            canon = target.get(getattr(cr, "field", None))
            if canon:
                by_field.setdefault(canon, []).append(cr)
        else:
            by_field.setdefault(target, []).append(cr)
    return by_field


def compute_all(
    candidates: dict,
    constraint_results: Optional[List[Any]] = None,
    catalog: Optional[List[CatalogEntry]] = None,
) -> List[FieldIdentity]:
    """A teljes per-mező identity-lista a `candidates` + `constraint_results`-ból."""
    entries = catalog if catalog is not None else field_catalog.entries()
    # A tételsor-oszlopok (level="L") a desk tételsor-rétegének sémája (1..n SOR) — egy per-katalógus
    # identity a sorokra értelmetlen, ezért a fejléc-identity reconcile KIHAGYJA őket (S182 designated scope C).
    entries = [e for e in entries if getattr(e, "level", "H") != "L"]
    by_field = _index_constraints(constraint_results or [])
    out: List[FieldIdentity] = []
    for entry in entries:
        rec = reconcile_field(entry, candidates)
        out.append(compute_field(entry, rec, by_field.get(entry.canonical, []), candidates))
    return out


def field_band(fi: "FieldIdentity") -> str:
    """A per-mező ZÖLD/BOROSTYÁN/PIROS sáv — a munkapad + a (Fázis 4) kapu SoT-szabálya.

    Krisztián-döntés (2026-06-29, Fázis 3 mérés #1): a ZÖLD-höz **két egyező független olvasat**
    kell (reconciled MATCH). A **single-source** (csak QR / csak vizuális → verdict INSUFFICIENT) és a
    POSSIBLE → **BOROSTYÁN** (nem auto-átengedhető → HITL). Ok: a Fázis 3 mérés szerint a single-source
    87.9% (a false-green ~74%-a innen), a reconciled 97.8% → a single-source nem auto-grade. „Jöjjenek
    HITL-re, lássam működés közben; false-HITL kezdetnek vállalva." A finomítás (mely single-source
    megbízható) a pilot-tapasztalatból, sebészileg.

      PIROS   ⟺ hard_veto (checksum/recon/aritmetika fail)
      ZÖLD    ⟺ független reconcile MATCH (két egyező forrás)
      BOROSTYÁN ⟺ minden más (single-source/INSUFFICIENT, POSSIBLE) → HITL-front
    """
    if fi.hard_veto:
        return "red"
    if fi.verdict == Verdict.MATCH and (fi.breakdown or {}).get("independent"):
        return "green"
    return "amber"


def aggregate(fields: List[FieldIdentity]) -> float:
    """Doc-szintű conf% = a kötelező (a)/(b) kritikus mezők min-je (K5).

    K2: ha BÁRMELY kritikus mező hard_veto → 0.0 (a constraint-jelet az identity már tartalmazza,
    nincs dupla-büntetés). Fail-closed: ha nincs verifikálható kritikus mező → 0.0.
    A (c) read-only mezők NEM húzzák le a doc-confot (a kalibrálatlan placeholder nem dominálhat).
    """
    crit = [f for f in fields
            if f.field in CRITICAL_FIELDS and f.verifiable_class in ("a", "b")]
    if not crit:
        return 0.0
    if any(f.hard_veto for f in crit):
        return 0.0
    return round(min(f.estimate for f in crit), 4)
