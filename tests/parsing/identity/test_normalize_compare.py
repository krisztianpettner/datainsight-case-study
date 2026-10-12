"""S182 Fázis 1 — normalize_compare pure-unit tesztek (a fundamentum)."""
import unicodedata

from parsing.identity.normalize_compare import Verdict, canonicalize, compare


# ── AMOUNT ──────────────────────────────────────────────────────────────────
def test_amount_eu_vs_anglo_same_value():
    assert canonicalize("AMOUNT", "1.234,56") == 1234.56
    assert canonicalize("AMOUNT", "1,234.56") == 1234.56
    assert compare("AMOUNT", "1.234,56", "1234.56") is Verdict.MATCH


def test_amount_euro_strip_and_comma_decimal():
    assert canonicalize("AMOUNT", "€ 65,04") == 65.04
    assert compare("AMOUNT", "65,04", "65.04") is Verdict.MATCH


def test_amount_within_tolerance_and_mismatch():
    assert compare("AMOUNT", "100.00", "100.01") is Verdict.MATCH      # tol 0.02
    assert compare("AMOUNT", "40.93", "22.70") is Verdict.MISMATCH     # Endesa-jelenseg


def test_amount_insufficient_when_missing():
    assert compare("AMOUNT", None, "10.0") is Verdict.INSUFFICIENT
    assert compare("AMOUNT", "10.0", "") is Verdict.INSUFFICIENT


# ── DATE ────────────────────────────────────────────────────────────────────
def test_date_iso_and_pt_slash_equiv():
    assert canonicalize("DATE", "2022/05/08") == "2022-05-08"
    assert compare("DATE", "2022-05-08", "08/05/2022") is Verdict.MATCH


def test_date_yyyymmdd_and_pt_month_name():
    assert canonicalize("DATE", "20250214") == "2025-02-14"
    assert canonicalize("DATE", "7 de janeiro 2024") == "2024-01-07"
    assert compare("DATE", "2024-01-07", "7 de janeiro de 2024") is Verdict.MATCH


def test_date_off_by_one_mismatch():
    assert compare("DATE", "2022-12-29", "2022-12-30") is Verdict.MISMATCH


# ── NIF ─────────────────────────────────────────────────────────────────────
def test_nif_pt_prefix_strip_exact():
    assert canonicalize("NIF", "PT500000018") == "500000018"
    assert compare("NIF", "500000018", "PT 500000018") is Verdict.MATCH


def test_nif_mismatch_and_consumer_sentinel():
    assert compare("NIF", "500000018", "500000026") is Verdict.MISMATCH
    assert canonicalize("NIF", "999999990") == "999999990"  # sentinel = jelen, NEM hianyzo


# ── INVNUM ──────────────────────────────────────────────────────────────────
def test_invnum_exact_and_suffix_match():
    assert compare("INVNUM", "FT 2022/18", "FT2022/18") is Verdict.MATCH
    assert compare("INVNUM", "FT VNFACR/230200000017", "230200000017") is Verdict.MATCH


def test_invnum_mismatch():
    assert compare("INVNUM", "99120310000000001", "FAC 1111112022/0000000001") is Verdict.MISMATCH


def test_invnum_dot_and_prefix_tolerance():
    # S182 #2: pont/szóköz-eltérés → MATCH; vezető doc-típus-prefix → MATCH (endswith)
    assert compare("INVNUM", "FT.23.001/10001", "FT 23.001/10001") is Verdict.MATCH
    assert compare("INVNUM", "FT FA.ZZ25/500001", "FA ZZ25/500001") is Verdict.MATCH
    # de a VALÓDI széria-eltérés továbbra is MISMATCH (nem ál-egyezés)
    assert compare("INVNUM", "FT VNFACR/230200000017", "FT 2302/00000017") is Verdict.MISMATCH


# ── PERCENT ─────────────────────────────────────────────────────────────────
def test_percent_fraction_vs_pct_form():
    assert canonicalize("PERCENT", "0.23") == 23.0
    assert compare("PERCENT", "0.23", "23%") is Verdict.MATCH
    assert compare("PERCENT", "23", "6") is Verdict.MISMATCH


# ── ENUM_DOCTYPE ────────────────────────────────────────────────────────────
def test_doctype_visual_word_to_code():
    assert canonicalize("ENUM_DOCTYPE", "Factura") == "FT"
    assert canonicalize("ENUM_DOCTYPE", "Fatura") == "FT"
    assert compare("ENUM_DOCTYPE", "FT", "Fatura") is Verdict.MATCH


def test_doctype_credit_note_mismatch():
    assert canonicalize("ENUM_DOCTYPE", "Nota de Crédito") == "NC"
    assert compare("ENUM_DOCTYPE", "FT", "Nota de Crédito") is Verdict.MISMATCH


# ── CODE (cert / ATCUD prefix-tolerancia) ────────────────────────────────────
def test_code_cert_prefix_match_and_atcud_exact():
    assert compare("CODE", "192", "192/AT") is Verdict.MATCH          # vizuális toldalék
    assert compare("CODE", "ABCD1234-100000000001", "ABCD1234-100000000001") is Verdict.MATCH
    assert compare("CODE", "ABCD1234-100000000001", "EFGH5678-200000000002") is Verdict.MISMATCH


# ── TEXT (fuzzy) ────────────────────────────────────────────────────────────
def test_text_exact_substring_and_fuzzy():
    assert compare("TEXT", "Manz Consultores Lda", "Manz Consultores Lda") is Verdict.MATCH
    assert compare("TEXT", "Manz Consultores", "Manz Consultores Lda") is Verdict.POSSIBLE
    assert compare("TEXT", "completely other", "Manz Consultores Lda") is Verdict.MISMATCH


def test_text_nfc_nfd_accent_equivalence():
    base = "água"  # "água"
    nfc = unicodedata.normalize("NFC", base)   # a-acute = U+00E1
    nfd = unicodedata.normalize("NFD", base)   # a + U+0301 (combining acute)
    assert nfc != nfd                          # bajt-szinten KULONBOZOK
    assert compare("TEXT", nfc, nfd) is Verdict.MATCH


def test_text_insufficient_when_empty():
    assert compare("TEXT", None, "x") is Verdict.INSUFFICIENT
