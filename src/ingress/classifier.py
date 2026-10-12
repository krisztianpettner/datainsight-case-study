# ARCH-DOC: docs/architecture/24-line-items-extraction.md#16-pre-flight-zsilip-classifier--ingress-modul
"""IngressClassifier — F6 Pre-flight Zsilip (S149 LÉPCSŐ 4).

Tier 0 ELŐTT fut — TEXT/IMAGE/HYBRID/ACROFORM type-detect + NOT_INVOICE early-exit.

Implementáció a 24-doksi §16.2 alapján. Eltérések a tervhez képest:
- `LayoutFingerprinter` hívást NEM ide tesszük — a Software Discovery downstream
  modul kapja meg (S146.7 F5 LayoutFingerprintCache + LayoutFingerprinter már él).
- pdfplumber-t használunk PyMuPDF (`fitz`) helyett (`fitz` opcionális dep a stack-en;
  pdfplumber már KÉSZ minden konténerben).

Soft-fail policy: ha a pdfplumber exception-t dob, HYBRID típust adunk vissza
confidence=0.5 + reason-szal — a downstream pipeline-t NEM blokkoljuk.
"""

import logging
import re
from pathlib import Path
from typing import Union

import pdfplumber

from ingress.contracts import IngressClassification
from ingress.types import IngressType

logger = logging.getLogger(__name__)

# 10-keyword whitelist — multi-lingual (PT/EN/HU/DE), case-insensitive,
# WORD-BOUNDARY matching (so "invoice" does NOT match "invoicer").
# Devils-advocate K3 fix (2026-05-28).
INVOICE_KEYWORDS = (
    "fatura",   # PT
    "factura",  # PT/ES
    "invoice",  # EN
    "számla",   # HU
    "rechnung", # DE
    "recibo",   # PT
    "nif",      # PT/ES (tax ID)
    "iva",      # PT/ES (VAT)
    "total",    # universal
    "atcud",    # PT (mandatory QR field)
)
# Pre-compile word-boundary patterns; flags=re.UNICODE handles `számla` (HU).
_KEYWORD_PATTERNS = tuple(
    re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE | re.UNICODE)
    for kw in INVOICE_KEYWORDS
)

# Early-exit threshold (S149 LÉPCSŐ 4 / remediation plan §4):
# NOT_INVOICE early-exit CSAK akkor megy, ha confidence >= NOT_INVOICE_CONFIDENCE.
NOT_INVOICE_CONFIDENCE = 0.95
NOT_INVOICE_KEYWORD_MIN = 2

# Type-classification text-density thresholds
TEXT_PAGE_THRESHOLD = 500       # avg chars/page > 500 → TEXT
IMAGE_PAGE_THRESHOLD = 50       # avg chars/page < 50 → IMAGE (likely scan)
DEFAULT_CONFIDENCE = 0.90       # text-density heuristic confidence

PdfPath = Union[str, Path]


class IngressClassifier:
    """F6 Pre-flight Zsilip classifier.

    Single public method: `classify(pdf_path) -> IngressClassification`.
    """

    def classify(self, pdf_path: PdfPath) -> IngressClassification:
        path = Path(pdf_path)
        if not path.exists():
            return IngressClassification(
                type=IngressType.NOT_INVOICE,
                confidence=1.0,
                is_invoice_likely=False,
                reason=f"file not found: {path}",
            )

        try:
            with pdfplumber.open(str(path)) as pdf:
                page_count = len(pdf.pages)
                if page_count == 0:
                    return IngressClassification(
                        type=IngressType.NOT_INVOICE,
                        confidence=1.0,
                        is_invoice_likely=False,
                        reason="empty PDF (0 pages)",
                    )

                # 1. Text-density per page + AcroForm detection
                text_lengths = []
                has_acroform = False
                acroform_fields: dict = {}
                for page in pdf.pages:
                    text = (page.extract_text() or "").strip()
                    text_lengths.append(len(text))
                    annots = page.annots or []
                    for annot in annots:
                        # Devils-advocate K2 fix (2026-05-28): pdfplumber may
                        # return PDFObjRef (lazy proxy) instead of dict for
                        # `data`. Strict isinstance-check, skip otherwise.
                        if not isinstance(annot, dict):
                            continue
                        data = annot.get("data", {})
                        if not isinstance(data, dict):
                            continue
                        if data.get("Subtype") == "/Widget":
                            has_acroform = True
                            field_name = str(data.get("T", "")) or ""
                            field_value = str(data.get("V", "")) or ""
                            if field_name:
                                acroform_fields[field_name] = field_value

                # 2. NOT_INVOICE keyword-absence heuristic (pages 0-1)
                # Word-boundary regex match (devils-advocate K3 fix, 2026-05-28):
                # "invoice" does NOT match "invoicer", "total" does NOT match "totally".
                first_pages_text = " ".join(
                    (p.extract_text() or "") for p in pdf.pages[:2]
                )
                keyword_hits = sum(
                    1 for pattern in _KEYWORD_PATTERNS
                    if pattern.search(first_pages_text)
                )
                if keyword_hits < NOT_INVOICE_KEYWORD_MIN:
                    return IngressClassification(
                        type=IngressType.NOT_INVOICE,
                        confidence=NOT_INVOICE_CONFIDENCE,
                        page_count=page_count,
                        has_acroform=has_acroform,
                        acroform_fields=acroform_fields,
                        is_invoice_likely=False,
                        reason=(
                            f"only {keyword_hits} invoice keywords found in "
                            f"first {min(2, page_count)} page(s) "
                            f"(threshold: {NOT_INVOICE_KEYWORD_MIN})"
                        ),
                    )

                # 3. Type classification (AcroForm wins over text-density)
                avg_text_per_page = sum(text_lengths) / max(page_count, 1)
                if has_acroform:
                    ingress_type = IngressType.ACROFORM
                    reason = (
                        f"acroform detected ({len(acroform_fields)} fields, "
                        f"avg text/page={avg_text_per_page:.0f})"
                    )
                elif avg_text_per_page > TEXT_PAGE_THRESHOLD:
                    ingress_type = IngressType.TEXT
                    reason = f"avg text/page={avg_text_per_page:.0f} chars"
                elif avg_text_per_page < IMAGE_PAGE_THRESHOLD:
                    ingress_type = IngressType.IMAGE
                    reason = (
                        f"avg text/page={avg_text_per_page:.0f} chars (likely scan)"
                    )
                else:
                    ingress_type = IngressType.HYBRID
                    reason = (
                        f"avg text/page={avg_text_per_page:.0f} chars "
                        f"(between {IMAGE_PAGE_THRESHOLD} and {TEXT_PAGE_THRESHOLD})"
                    )

                return IngressClassification(
                    type=ingress_type,
                    confidence=DEFAULT_CONFIDENCE,
                    page_count=page_count,
                    has_acroform=has_acroform,
                    acroform_fields=acroform_fields,
                    is_invoice_likely=True,
                    reason=reason,
                )
        except Exception as e:
            # Soft-fail: pipeline tovább megy HYBRID-ként, downstream dönt
            logger.warning(
                "IngressClassifier failed on %s: %s", pdf_path, e, exc_info=True
            )
            return IngressClassification(
                type=IngressType.HYBRID,
                confidence=0.5,
                is_invoice_likely=True,
                reason=f"classifier exception: {type(e).__name__}: {e}",
            )
