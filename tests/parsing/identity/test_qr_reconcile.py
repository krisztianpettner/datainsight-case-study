"""S182 Fázis 1 — qr_reconcile pure-unit tesztek (szintetikus candidate-szettek)."""
from parsing.identity import field_catalog
from parsing.identity.normalize_compare import Verdict
from parsing.identity.qr_reconcile import reconcile_field
from parsing.models.candidates import FieldCandidate


def _c(value, source, conf=1.0):
    return FieldCandidate(value=value, source=source, confidence=conf)


SUPPLIER = field_catalog.get("supplier_nif")     # qr=tax_id, visual=seller_nif (aliased)
DOCNUM = field_catalog.get("document_number")    # qr=visual=invoice_number (co-located)
GROSS = field_catalog.get("total_with_vat")      # qr=amount, visual=amount_gross
REGION = field_catalog.get("tax_region")         # qr=fiscal_area (QR-only)


def test_aliased_slot_match():
    """QR tax_id ↔ vizuális seller_nif KÜLÖN sloton, azonos érték → independent MATCH."""
    cands = {
        "tax_id": [_c("500000018", "qr")],
        "seller_nif": [_c("500000018", "tier2_schema", 0.93)],
    }
    rec = reconcile_field(SUPPLIER, cands)
    assert rec.independent is True
    assert rec.verdict is Verdict.MATCH
    assert rec.qr_value == "500000018"


def test_colocated_slot_match():
    """document_number: QR + vizuális UGYANAZON kulcson → MATCH."""
    cands = {"invoice_number": [_c("FT 2022/18", "qr"), _c("FT2022/18", "tier2_schema", 0.96)]}
    rec = reconcile_field(DOCNUM, cands)
    assert rec.independent is True
    assert rec.verdict is Verdict.MATCH


def test_mismatch_flags_red():
    cands = {
        "invoice_number": [_c("FAC 1111112022/0000000001", "qr")],
        # vizuális más kulcs nem kell; co-located kulcson tegyük a vizuálisat:
    }
    cands["invoice_number"].append(_c("99120310000000001", "tier2_schema", 0.97))
    rec = reconcile_field(DOCNUM, cands)
    assert rec.independent is True
    assert rec.verdict is Verdict.MISMATCH


def test_qr_only_is_not_independent():
    """Csak QR (nincs vizuális) → independent=False, INSUFFICIENT (egy-forrású)."""
    cands = {"fiscal_area": [_c("PT", "qr")]}
    rec = reconcile_field(REGION, cands)
    assert rec.independent is False
    assert rec.verdict is Verdict.INSUFFICIENT


def test_visual_only_is_not_independent():
    cands = {"seller_nif": [_c("500000018", "tier2_schema", 0.9)]}
    rec = reconcile_field(SUPPLIER, cands)
    assert rec.independent is False
    assert rec.verdict is Verdict.INSUFFICIENT


def test_multi_doc_disagreeing_qr():
    """≥2 egyet-nem-értő QR-candidate egy sloton → multi_qr, MISMATCH (multi-doc)."""
    cands = {"amount": [_c("86.43", "qr"), _c("3.02", "qr")]}
    rec = reconcile_field(GROSS, cands)
    assert rec.multi_qr is True
    assert rec.verdict is Verdict.MISMATCH


def test_match_any_against_noisy_visual():
    """Zajos vizuális (sok NIF), egy egyezik a QR-rel → MATCH (a QR lehorgonyoz)."""
    cands = {
        "tax_id": [_c("980000017", "qr")],
        "seller_nif": [_c("280000014", "tier2_schema", 0.95),
                       _c("980000017", "tier2_schema", 0.95),
                       _c("310000009", "tier2_schema", 0.95)],
    }
    rec = reconcile_field(SUPPLIER, cands)
    assert rec.independent is True
    assert rec.verdict is Verdict.MATCH


def test_redundant_same_qr_is_not_multidoc():
    """Ugyanaz a QR-érték kétszer (nem multi-doc) → NEM multi_qr."""
    cands = {
        "tax_id": [_c("500000026", "qr"), _c("500000026", "qr")],
        "seller_nif": [_c("500000026", "tier2_schema", 0.9)],
    }
    rec = reconcile_field(SUPPLIER, cands)
    assert rec.multi_qr is False
    assert rec.verdict is Verdict.MATCH
