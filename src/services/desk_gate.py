# ARCH-DOC: docs/architecture/44-hitl-workbench-data-entry-framework.md#16-mvp
"""S181 — HITL Munkapad commit-gate + mező-osztályozás (DEP-KÖNNYŰ, pure).

Kiemelve a `desk_service`-ből, hogy a determinista mag (field-classify + commit-gate) a DB/SQLAlchemy
betöltése nélkül, claude-dev-ben pure-unit tesztelhető legyen. Csak a `ConfidenceScorer` static-jeit
hívja (stdlib-only modul), lazy importtal. Plan: `.session/S181_keystone_plan.md` §4.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

# Mező-osztály leképezés (field_name → (type, oracle_class)) — v0 service-konstans (plan §6/2).
_NIF_EMITTER = {"tax_id", "nif", "vendor_nif", "nif_emitter", "supplier_nif", "emitter_nif"}
_NIF_ACQUIRER = {"customer_tax_id", "nif_acquirer", "acquirer_nif", "buyer_nif", "customer_nif", "nif_adquirente"}

# S203 P1-1b: PT B2C szentinel ("Consumidor Final") — több ezer számlán ugyanaz az érték,
# SEMMIT nem azonosít → az irány-őr se confirm, se block jelet nem adhat rá (DA-K3).
_CONSUMER_FINAL_NIF = "999999990"
_DATE_FIELDS = {"date", "issue_date", "invoice_date", "due_date", "emission_date"}
_TOTAL_FIELDS = {"total", "total_gross", "gross_total", "total_net", "net_total", "total_tax"}
_NUMBER_FIELDS = {"amount", "unit_price", "qty", "quantity", "iva_rate", "vat_rate"}

_ORACLE = {
    "nif": "nif_mod11", "iban": "iban_mod97", "atcud": "atcud_format",
    "date": "date_format", "total": "number_format", "number": "number_format",
    "line_text": "line_text_format",
}

# EXP-2 (S186): a `line.{n}.{col}` al-tipizálása — a suffix dönti el a validátort. `__deleted__`/
# `__added__` és ismeretlen suffix a mai "line_item"/"none" viselkedésen marad (nincs gépi oracle).
_LINE_TEXT_COLS = {"line_description"}
_LINE_NUMBER_COLS = {
    "line_quantity", "line_unit_price", "line_net_amount",
    "line_vat_rate", "line_vat_amount", "line_total_gross",
}

# EXP-2 (S186): a típus-szemét (rossz NIF/dátum/szám-a-leírásban) trust-kritikus a vevő felé →
# ezekre bukásnál severity="hard" (blokkol, force-fal felülírható). iban/atcud MARAD "soft".
_HARD_TYPES = frozenset({"nif", "date", "total", "number", "line_text"})


def classify_field(field_name: str) -> Tuple[str, str]:
    """field_name → (type, oracle_class). Pure, deterministic (plan §4)."""
    fn = (field_name or "").strip().lower()
    if fn.startswith("line") or ".line" in fn or fn.startswith("_line"):
        # `line.{n}.{col}` al-tipizálás: a leírás szöveg, az összeg-cellák szám; a foglalt kulcsok
        # (__deleted__/__added__) és ismeretlen suffix a mai "line_item"/"none"-on marad.
        suffix = fn.rsplit(".", 1)[-1]
        if suffix in _LINE_TEXT_COLS:
            return "line_text", "line_text_format"
        if suffix in _LINE_NUMBER_COLS:
            return "number", "number_format"
        return "line_item", "none"
    if "iban" in fn:
        return "iban", "iban_mod97"
    if "atcud" in fn:
        return "atcud", "atcud_format"
    if fn in _NIF_EMITTER or fn in _NIF_ACQUIRER or fn.endswith("_nif") or fn.endswith("_tax_id"):
        return "nif", "nif_mod11"
    if fn in _DATE_FIELDS or fn.endswith("_date"):
        return "date", "date_format"
    if fn in _TOTAL_FIELDS:
        return "total", "number_format"
    if fn in _NUMBER_FIELDS or any(k in fn for k in ("price", "amount", "total", "iva", "vat")):
        return "number", "number_format"
    return "text", "none"


def nif_direction(field_name: str) -> Optional[str]:
    """S203 P1-1b: a NIF-mező IRÁNYA (kibocsátó vs vevő) a mező-névből. Pure.

    "emitter" | "acquirer" | None (ismeretlen irány → az őr nem szól, DA-K6)."""
    fn = (field_name or "").strip().lower()
    if fn in _NIF_EMITTER or any(k in fn for k in ("supplier", "vendor", "seller", "emitente", "emitter")):
        return "emitter"
    if fn in _NIF_ACQUIRER or any(k in fn for k in ("customer", "buyer", "acquirer", "adquirente", "cliente")):
        return "acquirer"
    return None


def _norm_nif(v: Any) -> str:
    """Csak-számjegy normalizálás a QR-oldali nyers stringekre ("PT 123456789" → "123456789").
    A beírt érték oldalán a mod-11 check már szigorú 9-számjegyet követel (DA-K7)."""
    if v is None:
        return ""
    return "".join(c for c in str(v) if c.isdigit())


def run_commit_gate(
    field_type: str,
    value: Optional[str],
    *,
    qr_own: Optional[str] = None,
    qr_other: Optional[str] = None,
    direction: Optional[str] = None,
) -> Dict[str, Any]:
    """A beírt érték determinista commit-gate-je (reuse ConfidenceScorer static-ek).

    EXP-2 (S186): a `_HARD_TYPES` bukására severity="hard" (a route 422-re mapeli, a service NEM ír
    force nélkül); minden más típus (iban/atcud) SOFT-FLAG marad (nem blokkol). Üres = 'skip' (valós
    hiányzó érték), valid, provenance human_only. (plan §4, doc 44 §7)
    """
    from pdf_parser.confidence_scorer import ConfidenceScorer as CS  # lazy: stdlib-only modul

    v = (value or "").strip()
    if not v:
        return {"valid": True, "oracle": "none", "severity": "none", "provenance": "human_only"}

    checks: Dict[str, Callable[[str], bool]] = {
        "nif": CS._is_valid_pt_nif,
        "iban": CS._is_valid_pt_iban,
        "atcud": CS._is_valid_atcud,
        "date": CS._is_valid_date,
        "total": CS._is_numeric,
        "number": CS._is_numeric,
        "line_text": lambda x: not CS._is_numeric(x),  # a leírás-cella oracle-je: NEM tiszta szám
    }
    fn = checks.get(field_type)
    if fn is None:  # text / line_item — nincs gépi oracle → felismerés a garancia (v0: pass)
        return {"valid": True, "oracle": "none", "severity": "none", "provenance": "human_only"}

    ok = bool(fn(v))

    # S203 P1-1b IRÁNY-ŐR (DA-korrigált terv): formailag ÉRVÉNYES NIF, ami a QR szerint a
    # MÁSIK FÉL száma = a klasszikus felcserélés-csapda (S198 élő műszak-lelet). A mod-11 ezt
    # átengedné — itt blokkolunk (hard → 422 → force-override a meglévő S186-mintán).
    # Szabályok: a saját-QR-egyezés elsőbbséget élvez; a Consumidor Final szentinel (DA-K3)
    # és a hiányzó QR-adat semmilyen jelet nem ad (pozitív bizonyíték nélkül nincs blokk).
    if field_type == "nif" and ok:
        val, own, other = _norm_nif(v), _norm_nif(qr_own), _norm_nif(qr_other)
        if (
            other
            and other != _CONSUMER_FINAL_NIF
            and val == other
            and val != own
        ):
            side = "a KIBOCSÁTÓ (QR A-mező)" if direction == "acquirer" else "a VEVŐ (QR B-mező)"
            return {
                "valid": False,
                "oracle": "nif_direction_qr",
                "severity": "hard",
                "provenance": "human_only",
                "message": (
                    f"Felcserélés-gyanú: a beírt szám a QR szerint {side} NIF-je, "
                    "nem ezé a mezőé. Ellenőrizd, melyik mezőbe való!"
                ),
            }

    severity = "none" if ok else ("hard" if field_type in _HARD_TYPES else "soft")
    return {
        "valid": ok,
        "oracle": _ORACLE[field_type],
        "severity": severity,
        "provenance": "machine_confirmed" if ok else "human_only",
    }
