"""
QR/Barcode Engine V2 - Code Detection and Decoding

This module provides QR code and barcode detection for PDF documents.
It uses PyMuPDF for PDF-to-image conversion and pyzbar for decoding.

Key Features:
- Multi-page PDF support
- QR code and barcode detection (CODE128, EAN13, CODE39, etc.)
- Data normalization (JSON parsing, key-value extraction)
- Per-code confidence scoring
- Full backward compatibility (flag-controlled)

Output:
- List of QRBarcodeResult dataclass instances
- Each result has: id, code_type, data_raw, data_parsed, bbox, page

Usage:
    from pdf_parser.qr_barcode_engine_v2 import QRBarcodeEngineV2

    engine = QRBarcodeEngineV2()
    results = engine.scan(Path("invoice.pdf"))
    # Returns: [QRBarcodeResult(id="abc123", code_type="qr", ...), ...]

Module: 2. Modul - QR/Barcode Engine V2
Sprint: V2 Baseline Integration (Session 41)
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

# Pyzbar import with graceful fallback
try:
    from pyzbar.pyzbar import ZBarSymbol
    from pyzbar.pyzbar import decode as pyzbar_decode

    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    pyzbar_decode = None
    ZBarSymbol = None

# PIL for image handling
try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None

logger = logging.getLogger(__name__)


@dataclass
class QRBarcodeResult:
    """
    Represents a detected QR code or barcode from PDF

    Attributes:
        id: Unique identifier (UUID string) for this code
        code_type: Normalized code type (qr, code128, ean13, etc.)
        data_raw: Raw decoded string
        data_parsed: Parsed/normalized data structure
        bbox: Bounding box coordinates {x1, y1, x2, y2}
        page: Page number (1-indexed)
        confidence: Detection confidence (0.0-1.0)
    """

    id: str
    code_type: str
    data_raw: str
    data_parsed: Dict[str, Any]
    bbox: Dict[str, float]
    page: int
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


def _has_pt_fiscal_qr(results: List["QRBarcodeResult"]) -> bool:
    """True if any result is a PT fiscal QR — a QR whose payload parsed to an
    'A' field (issuer NIF, Portaria 195/2020). Used to decide whether the scan
    can stop early or should keep trying other DPIs / embedded images."""
    return any(
        r.code_type == "qr" and isinstance(r.data_parsed, dict) and "A" in r.data_parsed
        for r in results
    )


class QRBarcodeEngineV2:
    """
    QR/Barcode Engine V2

    Detects and decodes QR codes and barcodes in PDF documents using
    PyMuPDF for image conversion and pyzbar for decoding.

    Features:
    - Multi-page PDF support
    - Multiple code types (QR, CODE128, EAN13, CODE39, etc.)
    - Data normalization (JSON, key-value, plain text)
    - Configurable DPI for image conversion

    Usage:
        engine = QRBarcodeEngineV2()
        results = engine.scan(Path("invoice.pdf"))
    """

    # Code type normalization map
    CODE_TYPE_MAP = {
        "QRCODE": "qr",
        "QR_CODE": "qr",
        "CODE128": "code128",
        "CODE39": "code39",
        "EAN13": "ean13",
        "EAN8": "ean8",
        "UPCA": "upca",
        "UPCE": "upce",
        "I25": "interleaved25",
        "DATAMATRIX": "datamatrix",
        "PDF417": "pdf417",
    }

    def __init__(self, dpi: int = 300):
        """
        Initialize QR/Barcode Engine V2

        Args:
            dpi: Primary resolution for PDF-to-image conversion (default: 300)
                 Uses multi-DPI fallback: tries primary DPI first, then alternates
        """
        self.dpi = dpi
        self.zoom = dpi / 72.0  # 72 is standard PDF DPI
        # Multi-DPI fallback chain (pyzbar has DPI sensitivity issues)
        self._dpi_chain = [dpi] + [d for d in [300, 150, 200] if d != dpi]

        if not PYZBAR_AVAILABLE:
            logger.warning(
                {"event": "qr_engine_init", "status": "degraded", "reason": "pyzbar not available"}
            )
        elif not PIL_AVAILABLE:
            logger.warning(
                {"event": "qr_engine_init", "status": "degraded", "reason": "PIL not available"}
            )
        else:
            print(f"DEBUG: QREngine initialized with DPI={dpi}")
            logger.info({"event": "qr_engine_init", "status": "ready", "dpi": dpi})

    def scan(self, pdf_path: Path) -> List[QRBarcodeResult]:
        """
        Scan PDF for QR codes and barcodes

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of QRBarcodeResult instances

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            RuntimeError: If scanning fails
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        if not PYZBAR_AVAILABLE or not PIL_AVAILABLE:
            logger.warning(
                {
                    "event": "qr_engine_scan_skipped",
                    "pdf_name": pdf_path.name,
                    "reason": "pyzbar or PIL not available",
                }
            )
            return []

        results: List[QRBarcodeResult] = []

        try:
            print(f"DEBUG: Scanning PDF {pdf_path.name}")
            logger.info({"event": "qr_engine_scan_start", "pdf_name": pdf_path.name})

            doc = fitz.open(str(pdf_path))

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_results = self._scan_page(page, page_num + 1)
                results.extend(page_results)

            doc.close()

            logger.info(
                {
                    "event": "qr_engine_scan_success",
                    "pdf_name": pdf_path.name,
                    "codes_found": len(results),
                }
            )

            return results

        except Exception as e:
            logger.error(
                {"event": "qr_engine_scan_error", "pdf_name": pdf_path.name, "error": str(e)}
            )
            raise RuntimeError(f"QR/Barcode scan failed: {e}") from e

    def _scan_page(self, page: fitz.Page, page_num: int) -> List[QRBarcodeResult]:
        """
        Scan a single PDF page for codes

        Args:
            page: PyMuPDF Page object
            page_num: Page number (1-indexed)

        Returns:
            List of QRBarcodeResult instances for this page
        """
        results: List[QRBarcodeResult] = []
        seen: set = set()

        try:
            # Multi-DPI fallback: pyzbar is sensitive to specific DPI values where
            # the pixel grid aliases the QR module grid. Accumulate codes across
            # DPIs (de-duplicated) and only stop early once a PT *fiscal* QR is
            # found — a payload with an "A" field. Stopping at the first DPI that
            # yields *any* code lets a stray Code128 (e.g. a Multibanco payment
            # barcode) mask the fiscal QR that only decodes at another DPI.
            for try_dpi in self._dpi_chain:
                zoom = try_dpi / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Convert to PIL Image
                img_data = pix.tobytes("png")
                img = Image.open(BytesIO(img_data))

                # Decode QR/barcodes
                decoded = pyzbar_decode(img)

                for code in decoded or []:
                    result = self._process_code(code, page_num, pix.width, pix.height)
                    if result and (result.code_type, result.data_raw) not in seen:
                        seen.add((result.code_type, result.data_raw))
                        results.append(result)

                if _has_pt_fiscal_qr(results):
                    if try_dpi != self._dpi_chain[0]:
                        logger.info(
                            {
                                "event": "qr_engine_fallback_hit",
                                "page": page_num,
                                "primary_dpi": self._dpi_chain[0],
                                "success_dpi": try_dpi,
                                "codes_found": len(results),
                            }
                        )
                    break  # Found the PT fiscal QR — no need to try other DPIs

            # Fallback: Extract embedded images from PDF and scan individually
            # Some PDFs embed QR codes as JPEG objects — full-page rendering
            # introduces compression artifacts that destroy the finder patterns
            # (1:1:3:1:1 black-white ratio). Direct extraction + binarization fixes this.
            # Only when the page-render path found nothing at all — running it on every
            # page that merely lacks a *fiscal* QR is too slow for image-only PDFs.
            if not results:
                for r in self._scan_embedded_images(page, page_num):
                    if (r.code_type, r.data_raw) not in seen:
                        seen.add((r.code_type, r.data_raw))
                        results.append(r)

            logger.debug(
                {"event": "qr_engine_page_scanned", "page": page_num, "codes_found": len(results)}
            )

        except Exception as e:
            logger.warning({"event": "qr_engine_page_error", "page": page_num, "error": str(e)})

        return results

    def _scan_embedded_images(self, page: fitz.Page, page_num: int) -> List[QRBarcodeResult]:
        """
        Extract embedded image objects from PDF page and scan each for QR codes.

        Handles the case where QR codes are embedded as JPEG images —
        full-page rendering introduces compression artifacts that destroy
        the finder pattern edges. Direct extraction + binary thresholding
        restores the sharp black-white transitions needed by pyzbar.
        """
        from PIL import ImageOps

        results: List[QRBarcodeResult] = []

        try:
            doc = page.parent
            image_list = page.get_images(full=True)

            for img_info in image_list:
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue

                    img_bytes = base_image["image"]
                    pil_img = Image.open(BytesIO(img_bytes))
                    img_w, img_h = pil_img.size

                    # Skip tiny images (icons, logos) — QR needs at least ~100px
                    if img_w < 80 or img_h < 80:
                        continue

                    # Try 1: Direct decode
                    decoded = pyzbar_decode(pil_img)

                    # Try 2: Grayscale + binary threshold (restores finder pattern edges)
                    if not decoded:
                        gray = ImageOps.grayscale(pil_img)
                        binary = gray.point(lambda p: 255 if p > 128 else 0)
                        decoded = pyzbar_decode(binary)

                    if decoded:
                        for code in decoded:
                            result = self._process_code(code, page_num, img_w, img_h)
                            if result:
                                results.append(result)
                        logger.info(
                            {
                                "event": "qr_engine_embedded_image_hit",
                                "page": page_num,
                                "image_size": f"{img_w}x{img_h}",
                                "codes_found": len(results),
                            }
                        )
                        break  # Found codes, stop scanning images

                except Exception:
                    continue  # Skip problematic images

        except Exception as e:
            logger.debug(f"Embedded image scan failed: {e}")

        return results

    def _process_code(
        self, code, page_num: int, img_width: int, img_height: int
    ) -> Optional[QRBarcodeResult]:
        """
        Process a decoded code into QRBarcodeResult

        Args:
            code: pyzbar decoded object
            page_num: Page number (1-indexed)
            img_width: Image width in pixels
            img_height: Image height in pixels

        Returns:
            QRBarcodeResult instance or None
        """
        try:
            # Extract raw data
            data_raw = code.data.decode("utf-8", errors="replace")

            # Get code type
            code_type = self._normalize_code_type(code.type)

            # Get bounding box (convert from pixels to PDF coordinates)
            rect = code.rect
            scale = 72.0 / self.dpi  # Convert back to PDF units
            bbox = {
                "x1": rect.left * scale,
                "y1": rect.top * scale,
                "x2": (rect.left + rect.width) * scale,
                "y2": (rect.top + rect.height) * scale,
            }

            # Parse/normalize data
            data_parsed = self._normalize_data(data_raw)

            return QRBarcodeResult(
                id=str(uuid.uuid4()),
                code_type=code_type,
                data_raw=data_raw,
                data_parsed=data_parsed,
                bbox=bbox,
                page=page_num,
                confidence=1.0,  # pyzbar doesn't provide confidence
            )

        except Exception as e:
            logger.warning(f"Failed to process code: {e}")
            return None

    def _normalize_code_type(self, raw_type: str) -> str:
        """
        Normalize code type to standard format

        Args:
            raw_type: Raw code type from pyzbar

        Returns:
            Normalized code type string
        """
        raw_upper = str(raw_type).upper()

        # Check direct mapping
        if raw_upper in self.CODE_TYPE_MAP:
            return self.CODE_TYPE_MAP[raw_upper]

        # Default: lowercase
        return raw_upper.lower()

    def _normalize_data(self, data_raw: str) -> Dict[str, Any]:
        """
        Normalize/parse raw code data into structured format

        Normalization rules:
        1. Try JSON parse
        2. Try key-value pair extraction
        3. Fallback to simple value wrapper

        Args:
            data_raw: Raw decoded string

        Returns:
            Parsed data dictionary
        """
        if not data_raw:
            return {"value": ""}

        # 1. Try JSON parse
        try:
            parsed = json.loads(data_raw)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except (json.JSONDecodeError, ValueError):
            pass

        # 2. Try key-value extraction (common in payment QR codes)
        # Format: "key1:value1;key2:value2" or "key1=value1&key2=value2"
        # Also handles Portuguese AT QR codes: "A:value*B:value*..."
        # Some certified software emit "\" as the field separator instead of "*"
        # (observed: SAP Business Suite). Treat "\" as an additional separator.
        if ":" in data_raw and (
            ";" in data_raw or "\n" in data_raw or "*" in data_raw or "\\" in data_raw
        ):
            try:
                result = {}
                # Split by semicolon, newline, asterisk, or backslash (PT AT QR formats)
                pairs = (
                    data_raw.replace("\n", ";").replace("*", ";").replace("\\", ";").split(";")
                )
                for pair in pairs:
                    if ":" in pair:
                        key, value = pair.split(":", 1)
                        result[key.strip()] = value.strip()
                if result:
                    return result
            except Exception:
                pass

        # URL query string format
        if "=" in data_raw and ("&" in data_raw or "?" in data_raw):
            try:
                result = {}
                # Remove URL prefix if present
                query = data_raw.split("?")[-1]
                pairs = query.split("&")
                for pair in pairs:
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        result[key.strip()] = value.strip()
                if result:
                    return result
            except Exception:
                pass

        # 3. Fallback: simple value wrapper
        return {"value": data_raw}

    def scan_image(self, image_path: Path) -> List[QRBarcodeResult]:
        """
        Scan an image file for QR codes and barcodes

        Args:
            image_path: Path to image file (JPG, PNG, etc.)

        Returns:
            List of QRBarcodeResult instances
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        if not PYZBAR_AVAILABLE or not PIL_AVAILABLE:
            return []

        results: List[QRBarcodeResult] = []

        try:
            img = Image.open(image_path)
            decoded = pyzbar_decode(img)

            for code in decoded:
                result = self._process_code(code, 1, img.width, img.height)
                if result:
                    results.append(result)

            logger.info(
                {
                    "event": "qr_engine_image_scan_success",
                    "image_name": image_path.name,
                    "codes_found": len(results),
                }
            )

        except Exception as e:
            logger.error(
                {
                    "event": "qr_engine_image_scan_error",
                    "image_name": image_path.name,
                    "error": str(e),
                }
            )

        return results
