"""
Abstract Base Class for Country-Specific Extraction Profiles

Defines the Strategy Pattern interface for Tier 2 heuristic extraction.

Created: 2026-01-20 (Session 41 - Tier 2 Architecture)
Updated: 2026-01-23 (Session 51) - Added pdfplumber_page support for Spatial Layout
Updated: 2026-01-30 (Phase 1) - Implemented BaseProfile (Slot Principle) and Confidence Metadata
"""

import re
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple

from parsing.models.candidates import FieldCandidate

# Session 55: Use StructuredLogger
from utils.structured_logger import get_logger

# ── S189 (1c): a resolve_anchored_box horgony-kontextusa (field_catalog + QR) ──────────
# field_type → value_format (a verify-kapu típusához)
_FT_TO_VF = {"AMOUNT": "pt_money", "NIF": "nif", "DATE": "pt_date", "CODE": "atcud", "INVNUM": "docnum"}
# field_name → (raw Portaria QR-kulcs, normalizált QR-kulcs) — a fiskális érték a verify-hez
_FIELD_QR_KEYS = {
    "tax_id": ("A", "nif"), "seller_nif": ("A", "nif"),
    "amount": ("O", "total"), "amount_gross": ("O", "total"), "total_with_vat": ("O", "total"),
    "date": ("F", "date"), "issue_date": ("F", "date"),
    "invoice_number": ("G", "invoice_number"), "document_number": ("G", "invoice_number"),
    "atcud": ("H", "atcud"), "anchor": ("H", "atcud"),
}


def _bbox_qr_fiscal(field_name, qr_data):
    """A mezőhöz tartozó QR-érték (a verify-kapu fiskális horgonya). Mindkét kulcs-konvenciót
    próbálja (raw Portaria A/B/O/F ÉS normalizált nif/total/date). Nincs → None."""
    keys = _FIELD_QR_KEYS.get(field_name)
    if not keys or not qr_data:
        return None
    for _qe in qr_data:
        _dp = _qe.get("data_parsed", {}) if isinstance(_qe, dict) else {}
        for _k in keys:
            _v = _dp.get(_k)
            if _v not in (None, ""):
                return _v
    return None


# S190 (0e): mely KANONIKUS mezők fiskális értékét keressük meg a lapon (a doboz =
# a keresztellenőrzés helye). Bent: amit a portugál eljárásrend szerint könyvelni kell,
# ÉS van értelmes nyomtatott példánya. Kint: `tax_region`/`customer_country` (a lapon egy
# 2-betűs `PT` token — nem érdemi ellenőrzési hely; a nem-PT vevő felderítése külön,
# vizuális slot + reconcile feladata), és minden TEXT-mező.
# Azok a mező-típusok, ahol a kanonikus egyenlőség MEGBÍZHATÓAN eldönti, hogy az érték rajta
# van-e a lapon. A TEXT (nevek/címek) NEM ilyen: ott a nulla találat nem bizonyít hiányt.
_TYPED_FTS = ("AMOUNT", "NIF", "DATE", "CODE", "INVNUM")

_QR_BBOX_FIELDS = frozenset({
    "total_with_vat", "total_vat", "total_taxable_base",
    "document_number", "atcud", "issue_date", "supplier_nif", "customer_nif",
    "tax_base_normal", "tax_vat_normal", "tax_base_reduced", "tax_vat_reduced",
    "tax_base_intermedia", "tax_vat_intermedia", "tax_base_isento",
})

# S191 (handoff §6.2 Layer 1) — TESTVÉR-CSOPORTOK a QR-slot nevén: az ÁFA-tábla egy SORA
# ('IVA Normal 23%   29,64€   6,82€' → bázis + ÁFA) + a totál-sor. Ha a sor egy celláját
# egyedien megfogtuk, az ambiguus testvér az UGYANABBAN A SORBAN álló példányára oldódik fel
# — címke- és vendor-ismeret nélkül. Vertikális (oszlopos) totál-layoutnál nem tüzel (fail-safe).
_QR_SIBLING_GROUPS = (
    ("amount_base_nor", "amount_iva_nor"),
    ("amount_base_red", "amount_iva_red"),
    ("amount_base_int", "amount_iva_int"),
    ("amount_net", "amount_tax", "amount"),
)


def _dedupe_fiscal_docs(fdocs: list) -> list:
    """S195 F-1b (B6): a multi-fatura banner DISTINCT fiskális dokumentumot számol,
    nem QR-példányt — a 2.+ lapon megismételt QR ugyanaz a fatura (repró: Oxyblack NC
    „2 al-számla"=1 valódi; <doc> „3"=2, a 3. az FR 2. lapi QR-duplája).
    Kulcs: ATCUD (H); H='0' legitim (pre-2023 + Goldenergy QR-quirk) → ott a doc-szám
    (G) dönt. Az ismétlődések lapszámai a megtartott bejegyzés 'pages' listájába."""
    seen: dict = {}
    for fd in fdocs:
        h = fd.get("atcud")
        key = str(h) if (h and str(h) != "0") else f"G:{fd.get('doc_no')}"
        if key in seen:
            seen[key].setdefault("pages", []).append(fd.get("page"))
            continue
        fd["pages"] = [fd.get("page")]
        seen[key] = fd
    return list(seen.values())


def _bbox_field_type(field_name):
    """A mező normalize_compare-típusa a field_catalogból (a verify-kapuhoz). Hiba → None."""
    try:
        from parsing.identity import field_catalog as _fc
        _canon = _fc.canonical_for_slot(field_name)
        _e = _fc.get(_canon) if _canon else None
        return _e.field_type if _e else None
    except Exception:
        return None


class CountryProfile(ABC):
    """
    Abstract base class for country-specific extraction strategies.
    (Interface Definition)
    """

    @property
    @abstractmethod
    def country_code(self) -> str:
        pass

    @property
    def name(self) -> str:
        return self.country_code

    @property
    def ocr_languages(self) -> str:
        """Default OCR language. Override in subclasses."""
        return "eng"

    @abstractmethod
    def detect(self, text: str, qr_data: Optional[List[Dict[str, Any]]] = None) -> float:
        pass

    @abstractmethod
    def extract(
        self,
        text: str,
        qr_data: Optional[List[Dict[str, Any]]] = None,
        pdfplumber_page: Optional[Any] = None,
        pdf_path: Optional[str] = None,
        verbose: bool = False,  # Phase 1.4 enhancement
    ) -> Dict[str, Any]:
        pass

    def validate(self, extracted_data: Dict[str, Any]) -> bool:
        required_fields = ["date", "tax_id", "amount"]

        # 1. Existence Check
        if not all(extracted_data.get(field) is not None for field in required_fields):
            return False

        # 2. Field-Specific Validation (Phase 1 Enhancement)
        # Re-run validators to ensure data integrity, especially for custom logic like CDV
        for field, value in extracted_data.items():
            if value is None:
                continue

            slot_config = self.SLOTS.get(field) if hasattr(self, "SLOTS") else {}
            if slot_config:
                validator = slot_config.get("validator")
                if validator:
                    # Resolve string method names
                    if isinstance(validator, str):
                        validator = getattr(self, validator, None)

                    if callable(validator):
                        try:
                            if not validator(value):
                                # Logger available? BaseProfile has it, but CountryProfile doesn't necessarily
                                # We can check hasattr or just return False
                                return False
                        except Exception as e:
                            # Be strict or lenient? For validation method, strict seems appropriate.
                            # pass # For now, don't fail excessively if validator crashes
                            pass

        return True

    def _calculate_completeness(self, result: dict) -> float:
        """Calculate completeness score: filled_required / total_required."""
        required = ["date", "tax_id", "amount", "invoice_number"]
        filled = sum(1 for f in required if result.get(f))
        return round(filled / len(required), 2) if required else 0.0

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(country_code='{self.country_code}')>"


class BaseProfile(CountryProfile):
    """
    Foundation class implementing the Slot Principle.
    (Phase 1 Implementation)

    Reduces code duplication by providing a standardized extraction loop based on
    declarative slot configurations.
    """

    # Define slots in subclasses. Format:
    # {
    #     "tax_id": {
    #         "patterns": [re.compile(r'...')], # List of patterns to try
    #         "validator": self._validate_tax_id, # Optional validation method
    #         "cleaner": self._clean_tax_id,      # Optional cleaning method
    #         "source": "tier2_regex",            # Default source name
    #         "confidence": 0.85                  # Default confidence
    #     }
    # }
    SLOTS: Dict[str, Dict[str, Any]] = {}

    def __init__(self, verbose: bool = False):
        """Initialize with StructuredLogger."""
        self.logger = get_logger(__name__, verbose=verbose)

    def _run_tier3_extraction(
        self,
        result: Dict[str, Any],
        text: str,
        pdfplumber_page: Any = None,
        pdf_path: str = None,
        tabula_hint: list = None,
    ) -> Dict[str, Any]:
        """
        Consolidated Tier 3 line item extraction.

        Called automatically by extract() after slot extraction.
        Uses self.country_code and result['currency'] for parameters.

        Args:
            result: Current extraction result dict (with 'amount', 'currency')
            text: OCR text for line item extraction
            pdfplumber_page: Optional pdfplumber page object for spatial analysis
            pdf_path: Optional PDF file path

        Returns:
            Updated result dict with 'line_items' and metadata
        """
        if not text:
            return result

        try:
            # Lazy import to avoid circular dependency
            from ..extractors.tier3_extractor import Tier3LineItemExtractor

            tier3 = Tier3LineItemExtractor()

            # Use profile's country_code and extracted/default currency
            # Fallback chain: Extracted -> Profile Default -> 'USD'
            currency = result.get("currency") or getattr(self, "DEFAULT_CURRENCY", "USD")

            line_items, status, error, _ = tier3.extract_line_items(
                ocr_text=text,
                header_total=result.get("amount"),
                currency=currency,
                country_code=self.country_code,
                pdfplumber_page=pdfplumber_page,
                pdf_path=pdf_path,
                tabula_hint=tabula_hint,
            )

            # Update result
            result["line_items"] = line_items or []

            # Metadata
            if line_items:
                avg_conf = sum(item.get("confidence", 0) for item in line_items) / len(line_items)
            else:
                avg_conf = 0.0

            if "_metadata" not in result:
                result["_metadata"] = {}

            result["_metadata"]["line_items"] = {
                "source": "tier3_llm",
                "confidence": avg_conf,
                "status": status,
                "count": len(line_items) if line_items else 0,
            }

            if status != "SUCCESS" and error:
                self.logger.warning(
                    f"Tier 3 extraction: {status} - {error}", profile=self.__class__.__name__
                )
            else:
                self.logger.info(
                    f"Tier 3 extracted {len(line_items or [])} line items",
                    profile=self.__class__.__name__,
                )

        except Exception as e:
            self.logger.error(
                f"Tier 3 integration error", profile=self.__class__.__name__, error=str(e)
            )
            result["line_items"] = []
            if "_metadata" not in result:
                result["_metadata"] = {}
            result["_metadata"]["line_items"] = {
                "source": "tier3_llm",
                "confidence": 0.0,
                "status": "ERROR",
                "error": str(e),
            }

        return result

    def extract(
        self,
        text: str,
        qr_data: Optional[List[Dict[str, Any]]] = None,
        pdfplumber_page: Optional[Any] = None,
        pdf_path: Optional[str] = None,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Standardized extraction loop using Slot Principle.
        """
        # Reinitialize logger with verbose setting if requested or if not yet set
        if verbose:
            self.logger = get_logger(__name__, verbose=True)
        elif not hasattr(self, "logger"):
            self.logger = get_logger(__name__, verbose=False)

        start_time = time.time()
        result = {
            "date": None,
            "tax_id": None,
            "invoice_number": None,
            "amount": None,  # Backward compatible (maps to gross)
            "amount_net": None,  # Phase 1.4: Nettó összesen
            "amount_tax": None,  # Phase 1.4: ÁFA összesen
            "amount_gross": None,  # Phase 1.4: Végösszeg/Bruttó
            "currency": None,
            "anchor": None,  # Fix #3
            "vendor_name": None,  # Fix #3
            "country_code": self.country_code,
            "line_items": [],
            "raw_fields": {},
            "_metadata": {
                "_extraction_summary": {
                    "profile": self.__class__.__name__,
                    "total_fields_attempted": 0,
                    "total_fields_extracted": 0,
                    "total_extraction_time_ms": 0,
                }
            },
        }

        self.logger.debug(f"Starting extraction", profile=self.__class__.__name__)

        # 1. Slot Extraction (Tier 2)
        for field, config in self.SLOTS.items():
            result["_metadata"]["_extraction_summary"]["total_fields_attempted"] += 1
            self._process_slot(field, config, text, result)

        # 2. QR Code Augmentation (Optional)
        if qr_data:
            self._augment_with_qr(qr_data, result)

        # 3. Currency Defaults
        if not result.get("currency") and hasattr(self, "DEFAULT_CURRENCY"):
            result["currency"] = self.DEFAULT_CURRENCY
            self._add_metadata(result, "currency", 0.5, "default", 0)

        # 4. Tier 3 Line Item Extraction (Task 2.1 Consolidation)
        result = self._run_tier3_extraction(result, text, pdfplumber_page, pdf_path)

        # Calculate summary
        total_time_ms = (time.time() - start_time) * 1000
        extracted_count = sum(
            1
            for k, v in result.items()
            if k not in ["_metadata", "line_items", "raw_fields"] and v is not None
        )

        result["_metadata"]["_extraction_summary"].update(
            {
                "total_fields_extracted": extracted_count,
                "total_extraction_time_ms": round(total_time_ms, 2),
            }
        )

        self.logger.info(
            "Extraction completed",
            profile=self.__class__.__name__,
            fields_extracted=extracted_count,
            total_time_ms=round(total_time_ms, 2),
        )

        return result

    def _process_slot(self, field: str, config: Dict[str, Any], text: str, result: Dict[str, Any]):
        """
        Process a single slot: Extract -> Clean -> Validate -> Register

        If config['multi'] is True, collects ALL valid matches (list).
        Otherwise (default), takes the FIRST valid match (scalar).
        """
        start_ts = time.time()
        patterns = config.get("patterns", [])
        validator = config.get("validator")
        cleaner = config.get("cleaner")
        multi = config.get("multi", False)

        extracted_value = None
        confidence = 0.0
        source = "unknown"
        match_str = None
        multi_vals = []  # for multi mode

        self.logger.debug(
            f"Processing slot: {field}",
            profile=self.__class__.__name__,
            field=field,
            pattern_count=len(patterns),
        )

        def _clean(raw_val, cleaner_ref):
            if cleaner_ref:
                if isinstance(cleaner_ref, str):
                    cleaner_ref = getattr(self, cleaner_ref, None)
                try:
                    if callable(cleaner_ref):
                        return cleaner_ref(raw_val)
                except Exception:
                    pass
            return raw_val

        def _validate(clean_val, validator_ref):
            if validator_ref:
                if isinstance(validator_ref, str):
                    validator_ref = getattr(self, validator_ref, None)
                if callable(validator_ref):
                    try:
                        return validator_ref(clean_val)
                    except Exception:
                        pass
            return True

        # Time the extraction
        with self.logger.timed("slot_extraction", profile=self.__class__.__name__, field=field):
            for pattern in patterns:
                if multi:
                    # Multi mode: findall — collect ALL valid matches
                    for m in pattern.finditer(text):
                        if len(m.groups()) > 1:
                            raw_val = m.group(0)
                        else:
                            raw_val = m.group(1) if m.groups() else m.group(0)
                        clean_val = _clean(raw_val, cleaner)
                        if _validate(clean_val, validator):
                            conf = config.get("confidence", 0.85)
                            if validator:
                                conf = min(1.0, conf + 0.15)
                            multi_vals.append(clean_val)
                            # Keep first match metadata for _add_metadata
                            if extracted_value is None:
                                extracted_value = clean_val
                                match_str = raw_val
                                confidence = conf
                                source = config.get("source", "tier2_regex")
                else:
                    # Single mode (default): first valid match wins
                    match = pattern.search(text)
                    if match:
                        if len(match.groups()) > 1:
                            raw_val = match.group(0)
                        else:
                            raw_val = match.group(1) if match.groups() else match.group(0)
                        clean_val = _clean(raw_val, cleaner)
                        if _validate(clean_val, validator):
                            extracted_value = clean_val
                            match_str = raw_val
                            confidence = config.get("confidence", 0.85)
                            source = config.get("source", "tier2_regex")
                            if validator:
                                confidence = min(1.0, confidence + 0.15)
                            break
                        else:
                            self.logger.debug(
                                f"Validation failed",
                                profile=self.__class__.__name__,
                                field=field,
                                value=clean_val,
                            )

        duration_ms = (time.time() - start_ts) * 1000

        # Register result
        if multi and multi_vals:
            # Deduplicate while preserving order
            seen = set()
            deduped = []
            for v in multi_vals:
                if v not in seen:
                    seen.add(v)
                    deduped.append(v)
            result[field] = deduped if len(deduped) > 1 else deduped[0]
            result["raw_fields"][field] = match_str
            self._add_metadata(result, field, confidence, source, round(duration_ms, 2))
            self.logger.info(
                f"Extracted {field} (multi: {len(deduped)} values)",
                profile=self.__class__.__name__,
                field=field,
                confidence=confidence,
            )
        elif extracted_value is not None:
            result[field] = extracted_value
            result["raw_fields"][field] = match_str
            self._add_metadata(result, field, confidence, source, round(duration_ms, 2))
            self.logger.info(
                f"Extracted {field}",
                profile=self.__class__.__name__,
                field=field,
                value=str(extracted_value),
                confidence=confidence,
            )

    def _add_metadata(
        self, result: Dict[str, Any], field: str, confidence: float, source: str, duration: float
    ):
        """Helper to append metadata to the result object"""
        if "_metadata" not in result:
            result["_metadata"] = {}

        result["_metadata"][field] = {
            "confidence": confidence,
            "source": source,
            "extraction_time_ms": duration,
        }

    def _augment_with_qr(self, qr_data: List[Dict[str, Any]], result: Dict[str, Any]):
        """
        Override data with high-confidence QR data if available.
        QR is usually Tier 1 (Confidence 1.0).
        """
        pass  # Implement generic QR merging logic if common schema exists

    def generate_candidates(
        self,
        text: str,
        qr_data: Optional[List[Dict[str, Any]]] = None,
        pdf_path: Optional[str] = None,
        pdfplumber_page: Optional[Any] = None,
        bbox_pdf_path: Optional[str] = None,
    ) -> Dict[str, List[FieldCandidate]]:
        """
        Generate field candidates from SLOTS patterns.

        Ez a metódus NEM dönt - csak összegyűjti az ÖSSZES lehetséges
        értéket minden mezőre. A döntést a Constitution fogja megtenni.

        F3.0 (S146.7): pdf_path kwarg — line_items Tier 2 ladder hook
        bemenete. `_add_line_items_candidates` slot-gated: csak akkor fut,
        ha az adott profilnak van `_resolved_schema.slots.line_items` config-ja.
        Hardcoded profile-ok (PortugalProfile, HungaryProfile, GenericProfile)
        auto-no-op — nincs `_resolved_schema` attribute-juk, hook üres dict-tel
        gracefully kihagyja a ladder-t.

        Args:
            text: OCR szöveg
            qr_data: QR/Barcode adatok (opcionális)
            pdf_path: PDF abszolút útvonal (opcionális) — F3.0 ladder forrás

        Returns:
            Dict[field_name, List[FieldCandidate]]
            Példa:
            {
                "tax_id": [
                    FieldCandidate(value="599999993", source="tier2_regex", conf=0.9),
                    FieldCandidate(value="599999993", source="qr", conf=1.0)
                ],
                "date": [...]
            }
        """
        from collections import defaultdict

        from governance.zones import ZoneEnforcer as _ZE

        candidates = defaultdict(list)

        # S182 SÁV-2 (doc 46): per-mező match-site bbox a HITL zoom-to-field ugráshoz.
        # FLAG-GATED (S182_SAV2_BBOX, default OFF) — a mért rollouthoz. Forrás-GATED: a page-t
        # közvetlenül használja, vagy (production-út, ahol a caller nem ad page-t) a pdf_path-ból
        # nyitja. Bármi hiányzik/hibázik → no-op → NULLA viselkedés-változás (additív meta).
        import os as _os
        _word_indices = _resolve_anchored = None   # [(PageWordIndex, page_no), ...]
        _absence_ok = True   # S191: az 'absent' claim előfeltétele a TELJES, tartalom-hordozó scan
        if _os.getenv("S182_SAV2_BBOX", "0") == "1":
            # S189 (0a): a match-site bbox MINDEN lapon keres (per-page word-index,
            # first-page-local-unique). A valós dokumentum-hossz miatt a fejléc-mezők
            # (Total/ATCUD/docnum) a 2-3. lapra migrálhatnak (mért lap-migráció); a régi
            # pages[0]-only drótozás ezeket némán elvesztette. Forrás-prioritás: kész page
            # (egy-oldalas caller) → bbox_pdf_path (a valós, ladder-független út) → pdf_path.
            _pages, _own_pdf = None, None
            if pdfplumber_page is not None:
                _pages = [pdfplumber_page]
            else:
                _open_path = bbox_pdf_path or pdf_path
                if _open_path:
                    try:
                        import pdfplumber as _pp
                        _own_pdf = _pp.open(_open_path)
                        _pages = list(_own_pdf.pages)
                    except Exception:
                        _pages, _own_pdf = None, None
            if _pages:
                try:
                    from parsing.coordinatization.match_bbox import PageWordIndex, resolve_anchored_box
                    _MAX_BBOX_PAGES = 30
                    if len(_pages) > _MAX_BBOX_PAGES:
                        self.logger.warning(
                            "S182 bbox: %d oldal → az első %d-re korlátozva (bbox-scan cap)",
                            len(_pages), _MAX_BBOX_PAGES,
                        )
                        _pages = _pages[:_MAX_BBOX_PAGES]
                        # S191: csonkolt scan → a nem-látott lapon LEHET az érték → 'absent' TILOS
                        _absence_ok = False
                    # eager extract_words per lap → a pdf utána zárható
                    _word_indices = [
                        (PageWordIndex(_p), getattr(_p, "page_number", _i + 1))
                        for _i, _p in enumerate(_pages)
                    ]
                    # S191: kép-lap vékony szöveg-réteggel (szkennelt PDF + scanner-pecsét, pl.
                    # 'Digitalizado com CamScanner' — pár szó token, az ÉRTÉKEK képként).
                    # A 0-találat ott nem hiány-bizonyíték → az EGÉSZ doc absent-claim tiltva.
                    # A 0-szavas kép-mentes lap (üres elválasztó) NEM blokkol.
                    _MIN_WORDS_FOR_ABSENT = 25
                    for _p, (_wi, _) in zip(_pages, _word_indices):
                        if len(_wi.words) < _MIN_WORDS_FOR_ABSENT and (getattr(_p, "images", None) or []):
                            _absence_ok = False
                            break
                    # S192 §1.3(b) — 5. őszinteség-őr: függőleges (upright=False) SZÁMJEGY-HORDOZÓ
                    # token = token-vak sáv. A pdfplumber a rotált szöveget REVERZBEN adja (mért:
                    # EDP margó '620000005' = az eladó-NIF fordítva) → a token-keresés ott vak, az
                    # érték a sávban LEHET → a doc-szintű 'absent' claim ("sehol nincs kinyomtatva")
                    # nem tehető meg őszintén. A számjegy-mentes vertikális dísz (pl. 'cobrança'
                    # fordítva) NEM blokkol — az nem rejthet AMOUNT/NIF/CODE/DATE értéket.
                    # (A visszafordítás maga — a keret a VALÓDI tokenre — külön spike: a reverz
                    # irány rotáció-függő, ttb/btt-ambig; mérés nélkül shippelni rossz-box vektor.)
                    if _absence_ok:
                        _VERT_DIGITS_BLIND = 4
                        for _wi, _ in _word_indices:
                            if any(
                                w.get("upright") is False
                                and sum(ch.isdigit() for ch in (w.get("text") or "")) >= _VERT_DIGITS_BLIND
                                for w in _wi.words
                            ):
                                _absence_ok = False
                                break
                    _resolve_anchored = resolve_anchored_box
                except Exception:
                    _word_indices = _resolve_anchored = None
            if _own_pdf is not None:
                try:
                    _own_pdf.close()
                except Exception:
                    pass

        # 1. SLOTS-ból generálj kandidátusokat
        for field_name, slot_cfg in self.SLOTS.items():
            patterns = slot_cfg.get("patterns", [])

            # S189 (1c): a mező bbox-horgony-kontextusa (egyszer/mező). anchor a sémából (1b);
            # fiskális a QR-ból; value_format+reconcile a field_catalogból → az UNIVERZÁLIS
            # verify-kapu (a box SOHA nem mutat hasonló-rosszra). anchor nélkül → rung V (mai).
            _bx_region = _bx_labels = _bx_fiscal = _bx_vf = None
            _bx_label_rel, _bx_vsrc, _bx_reconcile = "right_or_below", "text", False
            if _word_indices:
                _anchor = slot_cfg.get("anchor") if isinstance(slot_cfg, dict) else None
                if isinstance(_anchor, dict):
                    _bx_region = _anchor.get("region")
                    _bx_labels = _anchor.get("label")
                    _bx_label_rel = _anchor.get("label_rel", "right_or_below")
                _bx_fiscal = _bbox_qr_fiscal(field_name, qr_data)
                _bx_ft = _bbox_field_type(field_name)
                _bx_vf = _FT_TO_VF.get(_bx_ft or "")
                if _bx_ft == "AMOUNT":
                    _bx_vsrc = "qr_o"
                _bx_reconcile = _bx_fiscal is not None

            for pattern in patterns:
                matches = pattern.findall(text)

                for match in matches:
                    # Validator check (ha van)
                    validator_name = slot_cfg.get("validator")
                    if validator_name:
                        validator = getattr(self, validator_name, None)
                        if isinstance(validator, str):  # Handle string references
                            validator = getattr(self, validator, None)

                        if validator and callable(validator):
                            try:
                                if not validator(match):
                                    continue  # Skip invalid
                            except Exception:
                                continue  # Skip on validation error

                    # Cleaner (ha van)
                    value = match
                    cleaner_name = slot_cfg.get("cleaner")
                    if cleaner_name:
                        cleaner = getattr(self, cleaner_name, None)
                        if isinstance(cleaner, str):  # Handle string references
                            cleaner = getattr(self, cleaner, None)

                        if cleaner and callable(cleaner):
                            try:
                                value = cleaner(match)
                            except Exception:
                                value = match  # Use raw if cleaner fails

                    # Candidate létrehozása (with GDPR zone metadata)
                    _cand = FieldCandidate(
                        value=value,
                        source=slot_cfg.get("source", "tier2_regex"),
                        confidence=slot_cfg.get("confidence", 0.5),
                        meta={
                            "pattern": pattern.pattern,
                            "raw_match": match,
                            "region": slot_cfg.get("region"),
                            **_ZE.get_meta(field_name),
                        },
                    )
                    # S182 SÁV-2 + S189 (0a/0d/1c): match-site bbox az ELSŐ lapon, ahol a mező
                    # feloldható. rung V (value-anchor, drift-immun) az egyedi értékre; ha a
                    # sémának van anchor-ja (region/label), a rung VR/L is fut az UNIVERZÁLIS
                    # verify-kapuval (a box SOHA nem mutat hasonló-rosszra). Additív meta; ÉRTÉK
                    # változatlan. A matched_text/precision a desk glance-confirm UX-hez.
                    if _resolve_anchored is not None and _word_indices:
                        try:
                            for _wi, _pno in _word_indices:
                                if not _wi.usable:
                                    continue
                                _rb = _resolve_anchored(
                                    _wi, value, pattern=pattern,
                                    raw_value=_cand.meta.get("raw_match"),
                                    region=_bx_region, label=_bx_labels, label_rel=_bx_label_rel,
                                    value_format=_bx_vf, value_source=_bx_vsrc,
                                    fiscal_value=_bx_fiscal, reconcile=_bx_reconcile,
                                )
                                if _rb.bbox is not None:
                                    _cand.meta["bbox"] = _rb.bbox
                                    _cand.meta["page_no"] = _pno
                                    _cand.meta["bbox_source"] = _rb.rung
                                    _cand.meta["bbox_precision"] = _rb.precision
                                    if _rb.matched_text is not None:
                                        _cand.meta["matched_text"] = _rb.matched_text
                                    if not _rb.value_ok:
                                        _cand.meta["value_ok"] = False
                                    _cand.meta.pop("bbox_absence", None)
                                    break
                                if not _rb.value_ok:
                                    _cand.meta["value_ok"] = False
                                # S190: MIÉRT nincs doboz? 'ambiguous' BÁRMELY lapon felülírja
                                # (van mit nézni valahol) → a deszk ezt üzeni tovább.
                                #
                                # ⚠️ S191: a regex-kandidátus 'absent'-et NEM állíthat. Az értéke
                                # magából a dokumentum-szövegből jött (tier2_regex) — ha a szó-index
                                # mégsem lokalizálja, az extract_text↔word-index eltérés (OCR-út,
                                # cleaner-transzform), NEM a hiány bizonyítéka. No-QR docon ráadásul
                                # a deszk 'absent' üzenete hamisan QR-forrást állítana. Az 'absent'
                                # szemantika (doc 46 §2.1: „a fiskális érték NINCS a lapon") a
                                # QR-pass kizárólagos joga. Egy hamis „ne keresd" ROSSZABB, mint a semmi.
                                if _rb.absence == "ambiguous":
                                    _cand.meta["bbox_absence"] = "ambiguous"
                                    # S191: a példány-lista is megy (jelölt-dobozok, ugrálható)
                                    if _rb.candidates:
                                        _bcl = _cand.meta.setdefault("bbox_candidates", [])
                                        for _bb, _tx in _rb.candidates:
                                            if len(_bcl) >= 8:
                                                break
                                            _bcl.append({"bbox": list(_bb), "page_no": _pno, "text": _tx})
                        except Exception:
                            pass
                    candidates[field_name].append(_cand)

        # 2. QR adatok hozzáadása (ha van)
        if qr_data:
            candidates = self._add_qr_candidates(candidates, qr_data)
            # S191 (élő teszt-lelet, EDP 2-al-számlás PDF): a FISKÁLIS QR-ok doc-szintű leltára —
            # a deszk ebből tudja kimondani, hogy „ebben a PDF-ben N al-számla van, a mezők
            # EHHEZ tartoznak". A 2. fatura ma némán elveszett (first-pick) — legalább LÁTSSZON.
            _fdocs = []
            for _qe in qr_data:
                _dp = _qe.get("data_parsed", {}) if isinstance(_qe, dict) else {}
                if not isinstance(_dp, dict):
                    continue
                if _dp.get("G") or _dp.get("H"):        # fiskális AT-QR (doc-szám/ATCUD hordozó)
                    _fdocs.append({
                        "doc_no": _dp.get("G"), "atcud": _dp.get("H"),
                        "total": _dp.get("O"), "date": _dp.get("F"),
                        # S191 DA-K2/K3 (al-számla-spawn előfeltétel): a TELJES nyers payload +
                        # a QR lapja perzisztál a parse pillanatában — túléli a szülő-PDF 48h
                        # törlését, a fedlap-generálás (spawn opció c) ebből újraépíthető.
                        "page": _qe.get("page"),
                        "qr_raw": _qe.get("data_raw"),
                    })
            if _fdocs:
                candidates["_fiscal_docs"] = _dedupe_fiscal_docs(_fdocs)
            # S190 (0e): a QR-forrású kandidátusok VIZUÁLIS példányának lokalizálása.
            # A deszken a doboz a KERESZTELLENŐRZÉS helye: az operátor a nyomtatott
            # értékre néz, összeveti a QR-ből jövő fiskális értékkel, entert nyom.
            # A doboz élő lap-tokenből jön, aminek értéke KANONIKUSAN+EGZAKTUL egyenlő
            # a fiskálissal; az ÉRTÉK forrása változatlanul a QR. Ambiguus/nincs → box-less.
            self._resolve_qr_candidate_bboxes(candidates, _word_indices, absence_ok=_absence_ok)

        # 3. F3.0 (S146.7) — line_items Tier 2 ladder hook (slot-gated).
        # Hardcoded profile-ok no-op (nincs _resolved_schema). SchemaProfile-ok
        # csak akkor futnak, ha `slots.line_items` config van a resolved schemájukban.
        candidates = dict(candidates)
        self._add_line_items_candidates(candidates, pdf_path, qr_data)

        return candidates

    def _resolve_qr_candidate_bboxes(self, candidates, word_indices, absence_ok: bool = True) -> None:
        """S190 (0e) — a QR-forrású kandidátusok bbox-a a fiskális érték VIZUÁLIS példányából.

        S191 `absence_ok`: az 'absent' claim („nincs kinyomtatva → ne keresd") CSAK teljes,
        tartalom-hordozó scan mellett megengedett. False, ha a lap-cap csonkolt vagy egy lap
        kép-alapú vékony szöveg-réteggel (szkennelt+pecsét) — ott a 0-találat nem hiány-bizonyíték.
        A DOBOZOLÁST nem érinti (az bármely usable lapon állhat).

        Miért kell: a bbox-feloldás (generate_candidates SLOTS-loop) csak a regex-kandidátusokra
        fut, ezért a kizárólag-QR-ből jövő mezők (a TOTÁL, az ATCUD, a per-sáv ÁFA…) box-less-ek
        maradtak, MÉG ha az értékük egyedien ki is van nyomtatva a lapon.

        Trust-garancia: a doboz CSAK olyan tokenre kerül, amely a mező típusa szerint
        KANONIKUSAN és EGZAKTUL egyenlő a fiskális értékkel → nem mutathat „hasonló-rosszra".
        Multi-QR (több al-számla egy PDF-ben, pl. EDP) → box-less, mert ott az érték↔hely
        párosítás eleve bizonytalan. Additív meta; az ÉRTÉK és a confidence érintetlen.
        """
        if not word_indices:
            return
        try:
            from parsing.coordinatization.match_bbox import resolve_fiscal_box
            from parsing.identity import field_catalog as _fc
        except Exception:
            return

        # NC/ND (jóváíró) ELŐJEL-ŐR: a PT AT QR a jóváírásnál ELŐJELES negatív összeget ad
        # (mérve a korpuszon: D=NC → O=-4.57, N=-0.09). Ha mégis POZITÍV magnitúdót kapnánk egy
        # jóváírón, az előjel-konvenció sérült: a lapon '-14,71' áll, a fiskális +14,71, és egy
        # MÁSIK, pozitív '14,71' tokenre tennénk dobozt (előjel-maszkolás → az operátor egy rossz
        # helyen glance-confirm-ol). Ilyenkor a monetáris mezők box-less-ek.
        _doc_type = None
        for _c in (candidates.get("document_type") or []):
            if getattr(_c, "source", "") == "qr":
                _doc_type = str(getattr(_c, "value", "") or "").upper()
                break
        _credit_note = _doc_type in ("NC", "ND")

        _staged = {}   # slot → (qr_cands, may_box, ftype) — a testvér-pass (S191 §6.2) inputja

        for field_name, clist in list(candidates.items()):
            if field_name.startswith("_") or not clist:
                continue
            qr_cands = [c for c in clist if getattr(c, "source", "") == "qr"]
            if not qr_cands:
                continue
            ftype = _bbox_field_type(field_name)
            if ftype not in _TYPED_FTS:
                continue
            try:
                canonical = _fc.canonical_for_slot(field_name)
            except Exception:
                canonical = None

            # BOXOLHATÓ-E? (az allowlist + a két őr). A JELENLÉTET viszont MINDEN tipizált
            # QR-mezőre kiszámoljuk — mert a deszken a legfontosabb üzenet az, hogy a mező
            # értéke NINCS a lapon (ne keresse). Mérve: a doboz-nélküli megállások 58%-a ilyen.
            may_box = canonical in _QR_BBOX_FIELDS
            # multi-QR őr: több al-számla ugyanarra a slotra KÜLÖNBÖZŐ értéket ad →
            # nem tudjuk, melyik nyomtatott előfordulás melyik al-számláé → box-less.
            if len({str(getattr(c, "value", None)) for c in qr_cands}) > 1:
                may_box = False
            if ftype == "AMOUNT" and _credit_note:
                # jóváíró: CSAK akkor boxolunk, ha a fiskális érték maga is negatív (ép konvenció)
                try:
                    if float(qr_cands[0].value) >= 0:
                        may_box = False
                except (TypeError, ValueError):
                    may_box = False
            _staged[field_name] = (qr_cands, may_box, ftype)
            for cand in qr_cands:
                meta = getattr(cand, "meta", None)
                if meta is None or meta.get("bbox") is not None:
                    continue
                # S191 lap-szavazat aggregáció: az 'absent' claim DOC-szintű állítás („sehol
                # nincs kinyomtatva") — egyetlen lap kontra-evidenciája (magnitúdó-variáns a
                # lapon → a rezolver box-less-t ad claim NÉLKÜL) az egészet megdönti. A régi
                # per-lap írás az 1. lap 'absent'-jét akkor is állva hagyta, ha a 2. lapon
                # ott volt az érték '-0,0900' alakban (mérve: AQUAmatrix NC, amount_tax).
                any_absent = any_contra = False
                for widx, page_no in word_indices:
                    if not widx.usable:
                        continue
                    try:
                        rb = resolve_fiscal_box(widx, cand.value, field_type=ftype)
                    except Exception:
                        break
                    if rb.bbox is not None:
                        if not may_box:
                            # az érték OTT VAN a lapon, csak a policy nem boxolja (allowlist /
                            # multi-QR / NC-őr) → NEM 'absent': ne küldjük hamis üzenettel keresni.
                            # S191: JELÖLTKÉNT megmutatjuk — DE CSAK ha a blokk oka multi-QR/NC
                            # (az EDP bizonylatszám esete). Az allowlist-KIZÁRT mező (tax_region,
                            # customer_country) SZÁNDÉKOSAN doboz-mentes: egy kósza 'PT' token
                            # szemantikailag NEM a régió jelölése (élő lelet: az Espaço fiscal
                            # vizuális párja a 'Continente' SZÓ, nem a kód) → jelölt sem lehet.
                            meta.pop("bbox_absence", None)
                            if canonical in _QR_BBOX_FIELDS:
                                meta.setdefault("bbox_candidates", []).append(
                                    {"bbox": list(rb.bbox), "page_no": page_no,
                                     "text": rb.matched_text})
                            any_absent = False
                            break
                        meta["bbox"] = rb.bbox
                        meta["page_no"] = page_no
                        meta["bbox_source"] = rb.rung          # 'value_qr' (NEM a 'tier2_match' default)
                        meta["bbox_precision"] = rb.precision
                        if rb.matched_text is not None:
                            meta["matched_text"] = rb.matched_text
                        meta.pop("bbox_absence", None)
                        any_absent = False
                        break
                    if rb.absence == "ambiguous":
                        meta["bbox_absence"] = "ambiguous"
                        # S191: a példányok jelölt-dobozként (lapokon átívelve gyűjtve, cap 8)
                        if rb.candidates:
                            bcl = meta.setdefault("bbox_candidates", [])
                            for bb, tx in rb.candidates:
                                if len(bcl) >= 8:
                                    break
                                bcl.append({"bbox": list(bb), "page_no": page_no, "text": tx})
                    elif rb.absence == "absent":
                        any_absent = True
                    else:
                        # box-less, claim nélkül = pozitív kontra-evidencia (a magnitúdó/CODE-
                        # szonda variáns-alakban megtalálta) → a doc-szintű „ne keresd" HAMIS lenne
                        any_contra = True
                        # S191: a szonda variáns-példányai jelöltként (pl. '631/AT' a '631'-re)
                        if rb.candidates:
                            bcl = meta.setdefault("bbox_candidates", [])
                            for bb, tx in rb.candidates:
                                if len(bcl) >= 8:
                                    break
                                bcl.append({"bbox": list(bb), "page_no": page_no, "text": tx})
                if (any_absent and not any_contra and absence_ok
                        and meta.get("bbox") is None
                        and meta.get("bbox_absence") != "ambiguous"):
                    meta["bbox_absence"] = "absent"

        # ── S191 (§6.2 Layer 1) TESTVÉR-HORGONY: az ambiguus VAT-cella feloldása a boxolt
        # testvér SORÁVAL. Krisztián mentőöve: ha az ÁFA-sor egy celláját egyedien megfogtuk,
        # a sor többi cellája abból adódik. Trust: a kiválasztott token TOVÁBBRA IS kanonikusan-
        # EGZAKTUL egyenlő a fiskálissal (resolve_fiscal_box region-ága) — a testvér-sor csak a
        # PÉLDÁNYT választja ki a több egyenértékű közül. A sávban >1 találat → marad box-less
        # (fail-safe). Egy kör, nincs kaszkád; a may_box őrök (allowlist/multi-QR/NC) öröklődnek.
        _idx_by_page = {pno: wi for wi, pno in word_indices if wi.usable}
        for _group in _QR_SIBLING_GROUPS:
            _anchors = []            # a csoport boxolt horgonyai: (bbox, page_no)
            for _slot in _group:
                _st = _staged.get(_slot)
                if not _st:
                    continue
                for _c in _st[0]:
                    _m = getattr(_c, "meta", None) or {}
                    if _m.get("bbox") is not None and _m.get("page_no") is not None:
                        _anchors.append((_m["bbox"], _m["page_no"]))
                        break
            if not _anchors:
                continue
            for _slot in _group:
                _st = _staged.get(_slot)
                if not _st:
                    continue
                _qr_cands, _may_box, _ftype = _st
                if not _may_box or _ftype != "AMOUNT":
                    continue
                for _cand in _qr_cands:
                    _meta = getattr(_cand, "meta", None)
                    if _meta is None or _meta.get("bbox") is not None:
                        continue
                    if _meta.get("bbox_absence") != "ambiguous":
                        continue
                    for _sb, _spage in _anchors:
                        _idx = _idx_by_page.get(_spage)
                        if _idx is None:
                            continue
                        _h = max(float(_sb[3]) - float(_sb[1]), 0.004)
                        _band = (0.0, max(0.0, float(_sb[1]) - 0.6 * _h),
                                 1.0, min(1.0, float(_sb[3]) + 0.6 * _h))
                        try:
                            _rb = resolve_fiscal_box(_idx, _cand.value, field_type="AMOUNT", region=_band)
                        except Exception:
                            continue
                        if _rb.bbox is not None:
                            _meta["bbox"] = _rb.bbox
                            _meta["page_no"] = _spage
                            _meta["bbox_source"] = _rb.rung        # 'value_qr' (sor-diszambiguált)
                            _meta["bbox_precision"] = _rb.precision
                            if _rb.matched_text is not None:
                                _meta["matched_text"] = _rb.matched_text
                            _meta.pop("bbox_absence", None)
                            break

    def _add_line_items_candidates(
        self,
        candidates: Dict[str, List[Any]],
        pdf_path: Optional[str] = None,
        qr_data: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """F3.0 (S146.7) — Tier 2 schema-driven line_items extraction ladder.

        Slot-gated: csak akkor fut, ha a profile-nak van `_resolved_schema.slots.line_items`
        config-ja ÉS pdf_path is van. Hardcoded profile-ok (PortugalProfile,
        HungaryProfile, GenericProfile) attribute-mentesek → silent no-op.

        4-layer confidence-descending ladder (24-doksi §2.2):
          Layer 0 — SchemaBboxExtractor (vendor-template bbox, conf=0.92)
                    requires delta YAML `box_hint` + `column_extractors`
          Layer 1 — LatticeExtractor (grid-line detection, conf=0.80)
                    requires master YAML `column_keywords`
          Layer 2 — StreamExtractor (header-anchor X/Y cluster, conf=0.65)
                    requires master YAML `column_keywords`
          Layer 3 — LineItemExtractor (Tabula adapter, conf~0.65-0.80)
                    no config needed, last-resort fallback

        First non-empty wins (K4 arbitráció: deterministic priority, NEM threshold-gated).
        Downstream `heuristic_engine` bridge-eli a `v2_result["line_items"]`-be (F3.0.c).
        """
        # No-op gates: schema-less profile (hardcoded) OR no PDF path → silent skip
        # NOTE: empty `slots.line_items` is OK — Layer 3 Tabula has no-config
        # fallback. Only schema-less (hardcoded) profiles and missing pdf_path
        # skip the ladder entirely.
        resolved_schema = getattr(self, "_resolved_schema", None)
        if not resolved_schema:
            return
        if not pdf_path:
            return

        line_items_schema = resolved_schema.get("slots", {}).get("line_items", {})

        # Importing inside the method to avoid circulars on module load:
        from parsing.line_items.document_cell import DocumentRow

        rows: List[DocumentRow] = []
        source: Optional[str] = None

        # Layer 0 — SchemaBboxExtractor (delta-YAML vendor template)
        box_hint = line_items_schema.get("box_hint")
        column_extractors = line_items_schema.get("column_extractors")
        if box_hint and column_extractors:
            from parsing.line_items.schema_bbox_extractor import (
                SchemaBboxExtractor,
            )

            rows = SchemaBboxExtractor(
                box_hint=box_hint, column_extractors=column_extractors
            ).extract(pdf_path)
            if rows:
                source = "tier2_schema_bbox"

        # Layer 1 — LatticeExtractor (master-YAML column_keywords)
        column_keywords = line_items_schema.get("column_keywords")
        cleaners = line_items_schema.get("cleaners") or {}
        if not rows and column_keywords:
            from parsing.line_items.lattice_extractor import LatticeExtractor

            rows = LatticeExtractor(
                column_keywords=column_keywords, cleaners=cleaners
            ).extract(pdf_path)
            if rows:
                source = "tier2_lattice"

        # Layer 2 — StreamExtractor (header-anchored stream)
        if not rows and column_keywords:
            from parsing.line_items.stream_extractor import StreamExtractor

            rows = StreamExtractor(
                column_keywords=column_keywords, cleaners=cleaners
            ).extract(pdf_path)
            if rows:
                source = "tier2_stream"

        # Layer 3 — LineItemExtractor (Tabula adapter, last resort)
        if not rows:
            from parsing.line_items.extractor import LineItemExtractor

            rows = LineItemExtractor().extract_as_document_rows(pdf_path)
            if rows:
                source = "tier2_tabula"

        # Layer 3.5 — ColGeomExtractor (S168 SPIKE-2, calibration-free geometry).
        # ADDITIVE: runs regardless of what the ladder above produced, but only
        # OVERRIDES the existing winner when it is CLEARLY BETTER (gate below).
        # Protects the strong clusters (PRIMAVERA/AQUAmatrix/InvoiceXpress/
        # TOConline) and single-page invoices from regression.
        rows, source = self._maybe_apply_colgeom(
            rows, source, pdf_path, qr_data
        )

        # Layer 3.6 — GraphicTableExtractor (S168 SPIKE-3, deterministic
        # named-header utility tables: EDP / Goldenergy). ADDITIVE: runs after
        # ColGeom and OVERRIDES the existing winner ONLY when its Σnet reconciles
        # to the QR-net (the QR is a SELECTOR/validator — it never writes a cell)
        # AND it carries strictly more arith-coherent rows. This rescues the
        # graphic-utility cluster whose line-item table lives behind a marketing
        # cover page (the per-delta box_hint reads cover-slip garbage), without
        # touching the strong clusters (no QR reconcile → no override).
        rows, source = self._maybe_apply_graphic(
            rows, source, pdf_path, qr_data
        )

        # Layer 3.7 — TableFormer (S182 SÁV-2 Stage 1, docling sidecar). ADDITIVE +
        # ROUTING-gated (YAML `line_items.line_item_extractor == "tableformer"`) +
        # FLAG-gated (S182_SAV2_TABLEFORMER, default OFF). Override ONLY when strictly
        # MORE arith-coherent rows (regression-safe) — a strukturált klaszterekhez
        # (PHC/PRIMAVERA/AQUAmatrix), ahol a geometria-ladder alul-olvas. A grafikus-
        # utility (Endesa) NEM routol ide → text_fallback marad.
        rows, source = self._maybe_apply_tableformer(
            rows, source, pdf_path, qr_data, line_items_schema
        )

        # S168: collapse wrapped-description continuation rows into the prior
        # line BEFORE emitting (kills phantom line items from tight y-bands;
        # see document_cell.merge_continuation_rows). No-op when none match.
        # Then drop interstitial subtotal / section-header rows that a single
        # rectangular box_hint cannot exclude when a vendor table is two
        # physically-separate sub-tables split by a subtotal/header band
        # (GoldEnergy cert#2035 'Total de eletricidade' + 'TAXAS E IMPOSTOS').
        # Order: merge first (so a wrapped fragment is never mistaken for a
        # header), then suppress. Both no-op when nothing matches.
        if rows:
            from parsing.line_items.document_cell import (
                drop_summary_and_section_rows,
                merge_continuation_rows,
            )

            rows = merge_continuation_rows(rows)
            rows = drop_summary_and_section_rows(rows)

        # Emit FieldCandidate iff we found rows. Regression-safe: no rows → key absent.
        if rows:
            candidates["line_items"] = [
                FieldCandidate(
                    value=[r.cells for r in rows],
                    source=source or "tier2_line_items",
                    confidence=min(r.row_confidence for r in rows),
                    meta={"rows": rows, "extractor_ladder_step": source},
                )
            ]

    # ────────────────────────────────────────────────────────────────────
    # S168 SPIKE-2 — calibration-free column-geometry layer (Layer 3.5).
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _row_arith_coherent(row: Any) -> bool:
        """True if a row carries qty, unit_price AND net_amount that satisfy
        net ≈ qty × unit (±2% / ±0.05). The deterministic 'is this a real,
        internally-consistent line' signal used to rank two candidate reads."""
        try:
            q = row.get("quantity")
            u = row.get("unit_price")
            n = row.get("net_amount")
        except Exception:
            return False
        if q is None or u is None or n is None:
            return False
        try:
            q, u, n = float(q), float(u), float(n)
        except (TypeError, ValueError):
            return False
        if q == 0 or u == 0:
            return False
        prod = q * u
        return abs(prod - n) <= max(0.05, 0.02 * abs(prod))

    @classmethod
    def _coherent_count(cls, rows: List[Any]) -> int:
        return sum(1 for r in (rows or []) if cls._row_arith_coherent(r))

    @classmethod
    def _net_sum(cls, rows: List[Any]) -> Optional[float]:
        total = 0.0
        seen = False
        for r in (rows or []):
            try:
                n = r.get("net_amount")
            except Exception:
                n = None
            if n is None:
                continue
            try:
                total += float(n)
                seen = True
            except (TypeError, ValueError):
                continue
        return round(total, 2) if seen else None

    def _maybe_apply_tableformer(
        self,
        existing_rows: List[Any],
        existing_source: Optional[str],
        pdf_path: Optional[str],
        qr_data: Optional[List[Dict[str, Any]]],
        line_items_schema: Optional[Dict[str, Any]],
    ) -> Tuple[List[Any], Optional[str]]:
        """S182 SÁV-2 Stage 1 — a docling-sidecar TableFormer-olvasatát ACCEPTÁLJA a
        meglévő ladder-győztes FELETT CSAK ha szigorúan TÖBB arith-koherens sort hoz.

        Regression-safe konstrukció szerint: változatlanul visszaadja az existinget,
        kivéve ha MIND teljesül —
          1. ROUTING: a YAML `line_items.line_item_extractor == "tableformer"` (a
             cert/klaszter-delta dönt — strukturált klaszter → TableFormer);
          2. FLAG: `S182_SAV2_TABLEFORMER == "1"` (default OFF, mért rollout);
          3. a sidecar ≥1 szemantikus-soros táblát ad (column_keywords-illeszkedés);
          4. szigorúan TÖBB koherens sor, mint a meglévő győztes (a helyes olvasatot
             SOHA nem szorítja ki). A grafikus-utility (Endesa) nem routol ide.
        """
        import os as _os

        if _os.getenv("S182_SAV2_TABLEFORMER", "0") != "1":
            return existing_rows, existing_source
        schema = line_items_schema or {}
        if schema.get("line_item_extractor") != "tableformer" or not pdf_path:
            return existing_rows, existing_source
        column_keywords = schema.get("column_keywords")
        if not column_keywords:
            return existing_rows, existing_source
        try:
            from parsing.line_items.tableformer_extractor import TableFormerExtractor

            tf_rows = TableFormerExtractor(
                column_keywords=column_keywords, cleaners=schema.get("cleaners") or {}
            ).extract(pdf_path)
        except Exception:
            logger.debug("TableFormer layer failed; keeping existing read", exc_info=True)
            return existing_rows, existing_source

        if not tf_rows:
            return existing_rows, existing_source
        if self._coherent_count(tf_rows) > self._coherent_count(existing_rows):
            return tf_rows, "tier2_tableformer"
        return existing_rows, existing_source

    def _maybe_apply_colgeom(
        self,
        existing_rows: List[Any],
        existing_source: Optional[str],
        pdf_path: Optional[str],
        qr_data: Optional[List[Dict[str, Any]]],
    ) -> Tuple[List[Any], Optional[str]]:
        """Run the calibration-free ColGeom extractor and ACCEPT its rows over
        the existing ladder winner ONLY when clearly better. Regression-safe:
        returns ``(existing_rows, existing_source)`` unchanged unless the gate
        below fires.

        Gate (deterministic, no model):
          - Let C = #arith-coherent rows (net ≈ qty×unit) for each candidate.
          - QR cross-check: Σnet within ±1.5% of the QR (O−N) net, when QR present.
          - ACCEPT ColGeom iff:
              (a) the existing read is EMPTY, and ColGeom has ≥1 coherent row; OR
              (b) ColGeom has STRICTLY MORE coherent rows than the existing read
                  AND (no QR present  → require ColGeom ≥2 coherent rows
                       QR present     → ColGeom Σnet matches QR-net within tol).
          - NEVER override a non-empty `tier2_schema_bbox` (vendor-template)
            winner unless ColGeom ALSO matches the QR-net (the strong-cluster
            guard: a hand-verified template is only displaced by a QR-proven
            better read).
        """
        if not pdf_path:
            return existing_rows, existing_source
        try:
            from parsing.line_items.colgeom_extractor import ColGeomExtractor

            cg_rows = ColGeomExtractor().extract_as_document_rows(pdf_path)
        except Exception:
            logger.debug("ColGeom layer failed; keeping existing read",
                         exc_info=True)
            return existing_rows, existing_source

        if not cg_rows:
            return existing_rows, existing_source

        exist_coh = self._coherent_count(existing_rows)
        cg_coh = self._coherent_count(cg_rows)

        # MEASUREMENT-DISCIPLINE (S168 SPIKE-2): the QR is a GATE/validator ONLY —
        # it never writes a line-item cell (the per-row breakdown is undetermined
        # from a QR aggregate; the cells come purely from page geometry). The
        # COLGEOM_DISABLE_QR_GATE env switch removes the QR cross-check from the
        # accept decision so the geometry-only contribution can be measured in
        # isolation vs geometry+QR (reports the QR's TRUE marginal effect).
        import os as _os
        qr_gate_on = _os.environ.get("COLGEOM_DISABLE_QR_GATE", "") not in (
            "1", "true", "True", "yes"
        )
        qr_net = self._qr_amount_net(qr_data) if qr_gate_on else None
        cg_net = self._net_sum(cg_rows)
        qr_match = (
            qr_net is not None
            and cg_net is not None
            and qr_net != 0
            and abs(cg_net - qr_net) <= max(0.05, 0.015 * abs(qr_net))
        )

        # (a) existing ladder produced nothing usable
        if not existing_rows:
            if cg_coh >= 1:
                return cg_rows, "tier2_colgeom"
            return existing_rows, existing_source

        # Strong-cluster guard: a non-empty vendor-template (schema_bbox) winner
        # is only displaced by a QR-proven better read.
        if existing_source == "tier2_schema_bbox":
            if qr_match and cg_coh > exist_coh:
                return cg_rows, "tier2_colgeom"
            return existing_rows, existing_source

        # (b) ColGeom strictly more coherent than a weaker (lattice/stream/tabula)
        # read. With QR present, require the Σnet to corroborate; without QR,
        # require a solid (≥2) coherent-row floor to avoid latching onto noise.
        if cg_coh > exist_coh:
            if qr_net is not None:
                if qr_match:
                    return cg_rows, "tier2_colgeom"
            elif cg_coh >= 2:
                return cg_rows, "tier2_colgeom"

        return existing_rows, existing_source

    def _maybe_apply_graphic(
        self,
        existing_rows: List[Any],
        existing_source: Optional[str],
        pdf_path: Optional[str],
        qr_data: Optional[List[Dict[str, Any]]],
    ) -> Tuple[List[Any], Optional[str]]:
        """S168 SPIKE-3 — run the deterministic GraphicTableExtractor (named-
        header EDP/Goldenergy utility tables) and ACCEPT its rows over the
        existing ladder winner ONLY when the read is QR-PROVEN better.

        Regression-safe by construction: returns ``(existing_rows,
        existing_source)`` unchanged unless ALL of the following hold —
          1. the extractor produced ≥1 arith-coherent row;
          2. a QR-net is present AND the extractor's Σnet reconciles to it
             within tol (the QR is a SELECTOR/validator — the per-row cells come
             purely from page geometry, never from the QR aggregate); and
          3. the extractor carries strictly MORE arith-coherent rows than the
             existing winner (so a correct existing read is never displaced).

        Because acceptance REQUIRES a QR reconcile, the strong clusters
        (PRIMAVERA/AQUAmatrix/InvoiceXpress/TOConline) and the already-correct
        Goldenergy consumption tables are untouched: their existing reads either
        already match the QR (so the strict-more-coherent guard holds them) or
        the graphic extractor does not reconcile (so it is rejected outright).

        MEASUREMENT-DISCIPLINE: the ``COLGEOM_DISABLE_QR_GATE`` env switch (shared
        with Layer 3.5) removes the QR reconcile so the geometry-only
        contribution can be measured in isolation; with the gate off, acceptance
        falls back to a strict coherent-row-count floor (≥2 and strictly more),
        which is the geometry-only signal.
        """
        if not pdf_path:
            return existing_rows, existing_source
        try:
            from parsing.line_items.graphic_table_extractor import (
                GraphicTableExtractor,
            )

            g_rows = GraphicTableExtractor().extract_as_document_rows(pdf_path)
        except Exception:
            logger.debug("Graphic layer failed; keeping existing read",
                         exc_info=True)
            return existing_rows, existing_source

        if not g_rows:
            return existing_rows, existing_source

        exist_coh = self._coherent_count(existing_rows)
        g_coh = self._coherent_count(g_rows)
        if g_coh < 1:
            return existing_rows, existing_source

        import os as _os
        qr_gate_on = _os.environ.get("COLGEOM_DISABLE_QR_GATE", "") not in (
            "1", "true", "True", "yes"
        )
        qr_net = self._qr_amount_net(qr_data) if qr_gate_on else None
        g_net = self._net_sum(g_rows)
        qr_match = (
            qr_net is not None
            and g_net is not None
            and qr_net != 0
            and abs(g_net - qr_net) <= max(0.05, 0.015 * abs(qr_net))
        )

        if qr_gate_on:
            # QR is the selector: accept only a QR-reconciled, strictly-better read.
            if qr_match and g_coh > exist_coh:
                return g_rows, "tier2_graphic"
            return existing_rows, existing_source

        # QR-gate OFF (isolation measurement): geometry-only acceptance — a solid
        # coherent floor AND strictly more coherent rows than the existing read.
        if g_coh >= 2 and g_coh > exist_coh:
            return g_rows, "tier2_graphic"
        return existing_rows, existing_source

    @staticmethod
    def _qr_amount_net(qr_data: Optional[List[Dict[str, Any]]]) -> Optional[float]:
        """Net amount from the PT fiscal QR: gross (O) − total VAT (N).

        Correct for ALL VAT-rate combinations, unlike summing a single I-field.
        Uses the FIRST QR entry that carries both O and N — deterministic, so a
        multi-invoice PDF cannot let the last QR silently overwrite the value.
        Shared by PortugalProfile and SchemaProfile so net is derived the same
        way regardless of which profile handled the invoice."""
        for qr_entry in qr_data or []:
            if not isinstance(qr_entry, dict):
                continue
            parsed = qr_entry.get("data_parsed", {})
            if not isinstance(parsed, dict) or "O" not in parsed or "N" not in parsed:
                continue
            try:
                o_val = float(str(parsed["O"]).replace(",", "."))
                n_val = float(str(parsed["N"]).replace(",", "."))
            except (ValueError, TypeError):
                continue
            return round(o_val - n_val, 2)
        return None

    def _add_qr_candidates(
        self, candidates: Dict[str, List[Any]], qr_data: List[Dict[str, Any]]
    ) -> Dict[str, List[Any]]:
        """
        Add QR code data as high-confidence candidates.

        QR adatok mindig 1.0 confidence-t kapnak (legmegbízhatóbb forrás).
        """
        from parsing.models.candidates import FieldCandidate

        # QR field mapping (példa - ha van jobb mapping, használd azt)
        qr_field_map = {
            "nif": "tax_id",
            "total": "amount",
            "date": "date",
            "invoice_number": "invoice_number",
        }

        for qr_entry in qr_data:
            if not isinstance(qr_entry, dict):
                continue

            data_parsed = qr_entry.get("data_parsed", {})

            for qr_key, field_name in qr_field_map.items():
                if qr_key in data_parsed:
                    value = data_parsed[qr_key]
                    from governance.zones import ZoneEnforcer as _ZE

                    # Session 130: setdefault avoids KeyError when the slot
                    # has no prior candidates (devils-advocate K1).
                    candidates.setdefault(field_name, []).append(
                        FieldCandidate(
                            value=value,
                            source="qr",
                            confidence=1.0,  # QR WINS!
                            meta={
                                "qr_code_type": qr_entry.get("code_type"),
                                "qr_page": qr_entry.get("page", 1),
                                **_ZE.get_meta(field_name),
                            },
                        )
                    )

        return candidates
