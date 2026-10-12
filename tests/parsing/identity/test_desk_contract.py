"""S182 — desk_contract pure-unit tesztek (a HITL-kontraktus S182-oldali assemblere)."""
from parsing.identity.desk_contract import desk_type, doc_admission, to_desk_field_record


def _fi(field, estimate, band, *, verifiable_class="a", verdict="match", hard_veto=False,
        sources=("qr", "tier2_schema"), slots=None):
    return {
        "field": field, "value": "***", "estimate": estimate, "band": band,
        "verdict": verdict, "verifiable_class": verifiable_class, "critical": True,
        "hard_veto": hard_veto, "sources": list(sources), "slots": slots or [field],
        "breakdown": {},
    }


# ── desk_type ───────────────────────────────────────────────────────────────
def test_desk_type_canonical_first():
    assert desk_type("supplier_nif") == "nif"
    assert desk_type("total_with_vat") == "total"
    assert desk_type("issue_date") == "date"
    assert desk_type("atcud") == "atcud"
    assert desk_type("document_number") == "text"


def test_desk_type_field_type_fallback():
    assert desk_type("some_unknown_amount", "AMOUNT") == "number"
    assert desk_type("some_unknown_pct", "PERCENT") == "iva"
    assert desk_type("totally_unknown") == "text"


# ── to_desk_field_record ─────────────────────────────────────────────────────
def test_record_maps_conf_band_and_type():
    rec = to_desk_field_record(_fi("supplier_nif", 0.99, "green"))
    assert rec["field_name"] == "supplier_nif"
    assert rec["type"] == "nif"
    assert rec["confidence"] == 0.99
    assert rec["band"] == "green"
    assert rec["oracle_class"] == "a"          # a/b/c → commit-gate validátor
    assert rec["surfaced"] is False            # ZÖLD → nem surface-elt
    assert rec["value_real"] is None           # KÍVÜLRŐL jön (nem a redaktált sor)


def test_amber_and_red_are_surfaced():
    assert to_desk_field_record(_fi("atcud", 0.95, "amber"))["surfaced"] is True
    red = to_desk_field_record(_fi("document_number", 0.2, "red", verdict="mismatch", hard_veto=True))
    assert red["surfaced"] is True and red["hard_veto"] is True


def test_external_value_and_bbox_passthrough():
    rec = to_desk_field_record(_fi("issue_date", 0.99, "green"),
                               value_real="2024-06-27", bbox=[0.1, 0.2, 0.3, 0.25], page=1)
    assert rec["value_real"] == "2024-06-27"   # PC parse-artefakt
    assert rec["bbox"] == [0.1, 0.2, 0.3, 0.25]  # séma / SÁV 2
    assert rec["page"] == 1


def test_no_band_uses_threshold_then_failsafe():
    # band hiányában a field_threshold dönt; ha az sincs → surface-eld (kétségnél PIROS)
    nb = {"field": "total_vat", "estimate": 0.5, "verifiable_class": "b", "sources": ["qr"]}
    assert to_desk_field_record(nb, field_threshold=0.9)["surfaced"] is True
    assert to_desk_field_record(nb, field_threshold=0.4)["surfaced"] is False
    assert to_desk_field_record(nb)["surfaced"] is True  # fail-safe


# ── doc_admission ────────────────────────────────────────────────────────────
def test_doc_admission_threshold_and_failclosed():
    assert doc_admission(0.95, 0.90) is True       # doc kihagyja a munkapadot
    assert doc_admission(0.85, 0.90) is False       # munkapadra
    assert doc_admission(None, 0.90) is False        # fail-closed
    assert doc_admission(0.99, None) is False
