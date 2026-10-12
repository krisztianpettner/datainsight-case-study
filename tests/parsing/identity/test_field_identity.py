"""S182 Fázis 1 — field_identity pure-unit tesztek (estimate + hard-veto + aggregate)."""
from types import SimpleNamespace

from parsing.identity import field_catalog
from parsing.identity.field_identity import (
    MISMATCH_EST,
    POSSIBLE_EST,
    PROVEN_MATCH,
    SINGLE_SOURCE_CAP,
    VETO_EST,
    aggregate,
    compute_all,
    compute_field,
)
from parsing.identity.normalize_compare import Verdict
from parsing.identity.qr_reconcile import Reconcile
from parsing.models.candidates import FieldCandidate


def _c(value, source, conf=1.0):
    return FieldCandidate(value=value, source=source, confidence=conf)


def _cr(name, passed, field=None, severity="high"):
    return SimpleNamespace(constraint_name=name, passed=passed, field=field, severity=severity)


SUPPLIER = field_catalog.get("supplier_nif")
REGION = field_catalog.get("tax_region")


def _rec(verdict, independent, multi_qr=False, qr="x", visual="x"):
    return Reconcile(field=SUPPLIER.canonical, verifiable_class="a", field_type="NIF",
                     qr_value=qr, visual_value=visual, verdict=verdict,
                     independent=independent, multi_qr=multi_qr, n_qr=1, n_visual=1)


# ── per-mező estimate ────────────────────────────────────────────────────────
def test_match_gets_proven_no_veto():
    fi = compute_field(SUPPLIER, _rec(Verdict.MATCH, True), [], {})
    assert fi.estimate == PROVEN_MATCH
    assert fi.hard_veto is False


def test_mismatch_low_and_veto():
    fi = compute_field(SUPPLIER, _rec(Verdict.MISMATCH, True), [], {})
    assert fi.estimate == MISMATCH_EST
    assert fi.hard_veto is True


def test_possible_medium_no_veto():
    fi = compute_field(SUPPLIER, _rec(Verdict.POSSIBLE, True), [], {})
    assert fi.estimate == POSSIBLE_EST
    assert fi.hard_veto is False


def test_multi_doc_vetoes():
    fi = compute_field(SUPPLIER, _rec(Verdict.MISMATCH, True, multi_qr=True), [], {})
    assert fi.hard_veto is True
    assert fi.estimate == MISMATCH_EST


def test_single_source_placeholder_capped():
    """Egy-forrású → kalibrálatlan candidate.confidence, a proven-plafon ALÁ vágva."""
    cands = {"fiscal_area": [_c("PT", "qr", 1.0)]}
    rec = Reconcile(field="tax_region", verifiable_class="a", field_type="CODE",
                    qr_value="PT", visual_value=None, verdict=Verdict.INSUFFICIENT,
                    independent=False, n_qr=1, n_visual=0)
    fi = compute_field(REGION, rec, [], cands)
    assert fi.estimate == SINGLE_SOURCE_CAP    # 1.0 → 0.95 cap (sosem proven-100%)
    assert fi.hard_veto is False
    assert fi.breakdown.get("placeholder") is True


# ── constraint-override (K6) ─────────────────────────────────────────────────
def test_hard_constraint_forces_veto_floor():
    """NIF Checksum FAIL → hard_veto + estimate floor, akkor is ha a reconcile MATCH volt."""
    crs = [_cr("NIF Checksum", passed=False, field="tax_id", severity="high")]
    fi = compute_field(SUPPLIER, _rec(Verdict.MATCH, True), crs, {})
    assert fi.hard_veto is True
    assert fi.estimate <= VETO_EST


def test_soft_constraint_caps_only():
    """Date Range (medium) → csak estimate-cap, NEM teljes veto."""
    issue = field_catalog.get("issue_date")
    crs = [_cr("Date Range", passed=False, field=None, severity="medium")]
    rec = Reconcile(field="issue_date", verifiable_class="a", field_type="DATE",
                    qr_value="2022-05-08", visual_value="2022-05-08", verdict=Verdict.MATCH,
                    independent=True, n_qr=1, n_visual=1)
    fi = compute_field(issue, rec, crs, {})
    assert fi.hard_veto is False
    assert fi.estimate <= 0.50


# ── aggregate (K2/K5) ────────────────────────────────────────────────────────
def _fi(canonical, estimate, veto=False, vclass="a"):
    entry = field_catalog.get(canonical)
    from parsing.identity.field_identity import FieldIdentity
    return FieldIdentity(field=canonical, value="x", estimate=estimate, verdict=Verdict.MATCH,
                         verifiable_class=vclass, hard_veto=veto, critical=entry.critical)


def test_aggregate_is_min_over_critical():
    fields = [_fi("supplier_nif", 0.99), _fi("total_vat", 0.95, vclass="b"),
              _fi("issue_date", 0.97)]
    assert aggregate(fields) == 0.95


def test_aggregate_zero_on_any_critical_veto():
    """K2: bármely kritikus hard_veto → 0.0 (nincs dupla-büntetés)."""
    fields = [_fi("supplier_nif", 0.99), _fi("document_number", MISMATCH_EST, veto=True)]
    assert aggregate(fields) == 0.0


def test_aggregate_readonly_does_not_drag():
    """K5: a (c) read-only NEM húzza le a doc-confot (csak az (a)/(b) kritikus számít)."""
    fields = [_fi("supplier_nif", 0.99),
              _fi("customer_country", 0.30, vclass="c")]   # nem kritikus + (c)
    assert aggregate(fields) == 0.99


def test_aggregate_fail_closed_when_no_critical():
    assert aggregate([]) == 0.0


# ── field_band (Krisztián-döntés: single-source → BOROSTYÁN, nem ZÖLD) ───────
def test_field_band_green_only_on_independent_match():
    from parsing.identity.field_identity import field_band
    fi = compute_field(SUPPLIER, _rec(Verdict.MATCH, independent=True), [], {})
    assert field_band(fi) == "green"


def test_field_band_single_source_is_amber():
    from parsing.identity.field_identity import field_band
    cands = {"fiscal_area": [_c("PT", "qr", 1.0)]}
    rec = Reconcile(field="tax_region", verifiable_class="a", field_type="CODE",
                    qr_value="PT", visual_value=None, verdict=Verdict.INSUFFICIENT,
                    independent=False, n_qr=1, n_visual=0)
    fi = compute_field(REGION, rec, [], cands)
    assert field_band(fi) == "amber"  # single-source → NEM zöld


def test_field_band_red_on_veto():
    from parsing.identity.field_identity import field_band
    fi = compute_field(SUPPLIER, _rec(Verdict.MISMATCH, independent=True), [], {})
    assert field_band(fi) == "red"


def test_field_band_possible_is_amber():
    from parsing.identity.field_identity import field_band
    fi = compute_field(SUPPLIER, _rec(Verdict.POSSIBLE, independent=True), [], {})
    assert field_band(fi) == "amber"


# ── compute_all integráció (mini end-to-end) ────────────────────────────────
def test_compute_all_strong_invoice_high():
    cands = {
        "tax_id": [_c("500000018", "qr")], "seller_nif": [_c("500000018", "tier2_schema", 0.93)],
        "customer_tax_id": [_c("240000013", "qr")],   # QR-only kritikus (placeholder)
        "invoice_number": [_c("FT 2022/18", "qr"), _c("FT 2022/18", "tier2_schema", 0.96)],
        "date": [_c("2022-05-08", "qr")], "issue_date": [_c("2022/05/08", "tier2_schema", 0.95)],
        "amount": [_c("80.0", "qr")], "amount_gross": [_c("80.0", "tier2_schema", 0.8)],
        "amount_net": [_c("65.04", "qr"), _c("65.04", "tier2_schema", 0.8)],
        "amount_tax": [_c("14.96", "qr"), _c("14.96", "tier2_schema", 0.8)],
        "document_type": [_c("FT", "qr")], "invoice_type": [_c("Fatura", "tier2_schema", 0.8)],
        "anchor": [_c("0-18", "qr")],          # atcud (QR-only placeholder)
        "fiscal_area": [_c("PT", "qr")],       # tax_region (QR-only placeholder)
    }
    fids = compute_all(cands, constraint_results=[])
    doc = aggregate(fids)
    assert doc >= 0.95
    assert not any(f.hard_veto for f in fids if f.critical)


def test_compute_all_mismatch_invoice_vetoes():
    cands = {
        "tax_id": [_c("980000017", "qr")], "seller_nif": [_c("980000017", "tier2_schema", 0.95)],
        "invoice_number": [_c("FAC 001/001", "qr"), _c("99120310000000001", "tier2_schema", 0.97)],
        "amount_tax": [_c("5.23", "qr"), _c("1.9", "tier2_schema", 0.8)],
    }
    fids = compute_all(cands, constraint_results=[])
    assert aggregate(fids) == 0.0
    vetoed = {f.field for f in fids if f.hard_veto}
    assert "document_number" in vetoed
