# ARCH-DOC: docs/architecture/24-line-items-extraction.md#16-pre-flight-zsilip-classifier--ingress-modul
"""Ingress pre-flight classifier package — F6 (S146.7 25-doksi §7 + S149 LÉPCSŐ 4).

A pipeline első lépése a Tier 0 OCR ELŐTT — TEXT/IMAGE/HYBRID/ACROFORM-osztály +
NOT_INVOICE early-exit (Pedro beszédes-státus).

Konvenció (S149 LÉPCSŐ 2): `# ARCH-DOC:` forward-link a 24-doksi §16-ra,
amely a tervezési SoT.
"""

from ingress.classifier import IngressClassifier
from ingress.contracts import IngressClassification
from ingress.types import IngressType

__all__ = [
    "IngressClassifier",
    "IngressClassification",
    "IngressType",
]
