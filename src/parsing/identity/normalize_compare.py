"""
normalize_compare.py — S182 adat-azonossági fundamentum.

A „v_A azonos-e v_B-vel" SOHA nem nyers string-összehasonlítás (design §4). Mindkét
oldalt a mező TÍPUSA szerint kanonizáljuk, aztán pontos egyezést nézünk ott, ahol van
kanonikus alak; fuzzy CSAK a maradék szabadszövegre (record-linkage / Fellegi–Sunter).

A normalizáló-logika a már bevált `scripts/pipeline_lab/score_full_invoice.py`-ból van
átemelve (NEM importálva — a `scripts/` nem package, és ez a modul dep-mentes kell legyen),
de a kimenet **3/4-utas** (a scorer csak bináris correct/wrong volt):

  MATCH        — kanonikusan azonos (a fő pozitív bizonyíték)
  MISMATCH     — kanonikusan eltér (PIROS-jelölt; QR↔vizuális eltérés = OCR-hiba gyanú)
  POSSIBLE     — szabadszöveg fuzzy-közeli, de nem biztos (a munkapad-front)
  INSUFFICIENT — az egyik oldal hiányzik → nincs mit összevetni

Pure stdlib. Pure-unit tesztelhető claude-dev-ben (tests/parsing/identity/).
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from enum import Enum
from typing import Any, Optional

# ── tolerancia (a score_full_invoice tükre) ────────────────────────────────
AMOUNT_TOL = 0.02      # fejléc + totálok
PERCENT_TOL = 0.05     # vat_rate százalékpont
TEXT_FUZZY_POSSIBLE = 0.80   # difflib ratio küszöb a POSSIBLE-höz

# PT consumer-final sentinel: „nincs NIF / végső fogyasztó" — NEM hiányzó érték
CONSUMER_FINAL_NIF = "999999990"

# PT dokumentum-típus lexikon: vizuális szöveg → kanonikus AT-kód (QR-D mező)
_DOCTYPE_LEXICON = {
    "fatura": "FT",
    "factura": "FT",
    "fatura-recibo": "FR",
    "fatura recibo": "FR",
    "factura-recibo": "FR",
    "recibo": "RC",
    "nota de credito": "NC",
    "nota de crédito": "NC",
    "nota de debito": "ND",
    "nota de débito": "ND",
    "fatura simplificada": "FS",
    "factura simplificada": "FS",
    "guia": "GT",
    "orcamento": "OR",
    "orçamento": "OR",
}
_VALID_DOCTYPE_CODES = {"FT", "FR", "FS", "NC", "ND", "RC", "GT", "OR", "GR", "GA", "CM", "CC"}


class Verdict(Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    POSSIBLE = "possible"
    INSUFFICIENT = "insufficient"


# ===========================================================================
# CANONICALIZERS (score_full_invoice tükre, NFC-tudatos kiegészítéssel)
# ===========================================================================

def _nfc(s: str) -> str:
    """UAX #15: „á" = U+00E1 VAGY U+0061+U+0301 → mindkettő NFC-re, hogy a == működjön."""
    return unicodedata.normalize("NFC", s)


def _norm_nif(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"[^0-9]", "", str(v).upper().replace("PT", "", 1))
    return s or None


def _norm_amount(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace("€", "").strip()
    if not s:
        return None
    # Európai vs angolszász tizedes: „1.234,56" és „1,234.56" UGYANAZ az érték.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # „1.234,56" → a vessző a tizedes
            s = s.replace(".", "").replace(",", ".")
        else:
            # „1,234.56" → a vessző az ezres
            s = s.replace(",", "")
    elif "," in s:
        # csak vessző → tizedes-vessző (PT/EU)
        s = s.replace(",", ".")
    try:
        return round(float(s), 4)
    except (ValueError, TypeError):
        return None


# PT (+ ES/EN) hónapnév → szám (a kiírt-dátumokhoz: „7 de janeiro 2024")
_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "mayo": 5, "junio": 6, "julio": 7,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "set": 9, "oct": 10, "out": 10, "nov": 11, "dec": 12, "dez": 12,
}


def _norm_date(v: Any) -> Optional[str]:
    """Locale-parse → kanonikus ISO 8601 (PT = DD/MM/YYYY; kiírt hónapnevek is)."""
    if v is None:
        return None
    s = str(v).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.match(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"(\d{8})$", s)
    if m:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    # kiírt dátum: „7 de janeiro 2024" / „7 de janeiro de 2024" / „7 janeiro 2024"
    m = re.match(r"(\d{1,2})\s+(?:de\s+)?([A-Za-zÀ-ÿ]+)\.?\s+(?:de\s+)?(\d{4})", _nfc(s), re.IGNORECASE)
    if m:
        mon = _MONTHS.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return s or None


def _norm_invnum(v: Any) -> Optional[str]:
    # S182 Fázis 3 #2: a whitespace MELLETT a pontokat is strip-eljük — a számla-szám gyakori
    # reprezentáció-eltérése csak pont/szóköz (`FT.23.001/10001` ⟺ `FT 23.001/10001`); a `/` (valódi
    # széria-elválasztó) MARAD. A vezető doc-típus-prefixet (`FT FA.ZZ25` ⊇ `FA ZZ25`) a compare
    # endswith-ága kezeli. A valódi széria-eltérés (Goldenergy `VNFACR` vs `2302`) így is MISMATCH marad.
    if v is None:
        return None
    return re.sub(r"[\s.]+", "", _nfc(str(v)).strip().upper()) or None


def _norm_percent(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(str(v).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    if 0.0 <= x <= 1.0:
        x *= 100.0
    return round(x, 2)


def _norm_code(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", "", _nfc(str(v)).strip().upper())
    # S195 F-1c/a (B1, repró EDP <doc>): a vizuális kandidátusra ráragad a nyomtatott
    # CÍMKE („ATCUD:ABCD1234-…") → hamis MISMATCH a QR H-val. A vezető ATCUD-címke
    # lestrippelése kanonizálás — az értéket nem érinti, csak a címke-zajt.
    s = re.sub(r"^ATCUD[:.]*", "", s)
    return s or None


def _norm_doctype(v: Any) -> Optional[str]:
    """Vizuális 'Factura'/'Fatura' VAGY QR 'FT' → kanonikus AT-kód."""
    if v is None:
        return None
    s = _nfc(str(v)).strip()
    up = s.upper()
    if up in _VALID_DOCTYPE_CODES:
        return up
    key = re.sub(r"\s+", " ", s.lower()).strip()
    if key in _DOCTYPE_LEXICON:
        return _DOCTYPE_LEXICON[key]
    # első szó próbálkozás (pl. „Fatura nº 12")
    first = key.split()[0] if key.split() else ""
    if first in _DOCTYPE_LEXICON:
        return _DOCTYPE_LEXICON[first]
    return up or None


def _norm_text(v: Any) -> Optional[str]:
    """NFC + casefold + whitespace-collapse (ékezet MEGTARTVA — PT-ben jelentéshordozó)."""
    if v is None:
        return None
    s = re.sub(r"\s+", " ", _nfc(str(v)).strip()).casefold()
    return s or None


# ===========================================================================
# PUBLIC API
# ===========================================================================

def canonicalize(field_type: str, v: Any):
    """A mező TÍPUSA szerint kanonizál. Visszatérés: str|float|None (None = hiányzó)."""
    ft = (field_type or "TEXT").upper()
    if ft == "NIF":
        return _norm_nif(v)
    if ft == "AMOUNT":
        return _norm_amount(v)
    if ft == "DATE":
        return _norm_date(v)
    if ft == "INVNUM":
        return _norm_invnum(v)
    if ft == "PERCENT":
        return _norm_percent(v)
    if ft == "CODE":
        return _norm_code(v)
    if ft == "ENUM_DOCTYPE":
        return _norm_doctype(v)
    # TEXT (default)
    return _norm_text(v)


def compare(field_type: str, a: Any, b: Any, *, tol: float = AMOUNT_TOL) -> Verdict:
    """Két érték adat-azonossága a mező TÍPUSA szerint. 3/4-utas Verdict.

    A QR↔vizuális reconcile, az aritmetika-reconcile és a HITL-commit-gate KÖZÖS magja.
    """
    ft = (field_type or "TEXT").upper()
    ca = canonicalize(ft, a)
    cb = canonicalize(ft, b)

    if ca is None or cb is None:
        return Verdict.INSUFFICIENT

    # numerikus típusok: tolerancia-sávval
    if ft in ("AMOUNT", "PERCENT"):
        t = PERCENT_TOL if ft == "PERCENT" else tol
        return Verdict.MATCH if abs(float(ca) - float(cb)) <= t else Verdict.MISMATCH

    # azonosító-típusok: pontos kanonikus egyezés
    if ft in ("NIF", "DATE", "ENUM_DOCTYPE"):
        return Verdict.MATCH if ca == cb else Verdict.MISMATCH

    # CODE (cert / ATCUD / régió): pontos VAGY prefix-tartalmazás — a vizuális gyakran toldalékol
    # ('192/AT' ⊇ QR '192'); a teljes-prefix követelmény nem ad ál-egyezést hosszú ATCUD-okra.
    if ft == "CODE":
        if ca == cb or ca.startswith(cb) or cb.startswith(ca):
            return Verdict.MATCH
        return Verdict.MISMATCH

    # számla-szám: pontos VAGY suffix-tartalmazás (rövidített/szériás alak)
    if ft == "INVNUM":
        if ca == cb or ca.endswith(cb) or cb.endswith(ca):
            return Verdict.MATCH
        return Verdict.MISMATCH

    # TEXT (szabadszöveg): pontos → MATCH; substring/fuzzy-közeli → POSSIBLE; egyébként MISMATCH
    if ca == cb:
        return Verdict.MATCH
    if ca in cb or cb in ca:
        return Verdict.POSSIBLE
    ratio = difflib.SequenceMatcher(None, ca, cb).ratio()
    if ratio >= TEXT_FUZZY_POSSIBLE:
        return Verdict.POSSIBLE
    return Verdict.MISMATCH
