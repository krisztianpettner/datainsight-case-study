# ARCH-DOC: docs/architecture/24-line-items-extraction.md#16-pre-flight-zsilip-classifier--ingress-modul
"""Ingress classification types — F6 Pre-flight Zsilip (S149 LÉPCSŐ 4)."""

from enum import Enum


class IngressType(str, Enum):
    """Pre-flight classification outcomes (24-doksi §16.2).

    - TEXT       — avg >500 char per page; text-PDF, fast pdfplumber path
    - IMAGE      — avg <50 char per page AND has images; scan-PDF, OCR mandatory
    - HYBRID     — between TEXT and IMAGE (multi-page mixed or low-quality text)
    - ACROFORM   — fillable form fields detected (SAP/ERP exports); shortcut Tier 0-1
    - NOT_INVOICE — < 2 invoice keywords on pages 0-1; early-exit + REJECTED bucket
    """

    TEXT = "text"
    IMAGE = "image"
    HYBRID = "hybrid"
    ACROFORM = "acroform"
    NOT_INVOICE = "not_invoice"
