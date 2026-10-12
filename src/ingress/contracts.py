# ARCH-DOC: docs/architecture/24-line-items-extraction.md#16-pre-flight-zsilip-classifier--ingress-modul
"""IngressClassification — F6 Pre-flight Zsilip output contract (S149 LÉPCSŐ 4).

Pydantic v2 BaseModel (egységes a parsing/line_items/document_cell.py
mintával, S149 LÉPCSŐ 3 LineItemSet ↔ IngressClassification audit-trail
sztili).
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ingress.types import IngressType


class IngressClassification(BaseModel):
    """Output of IngressClassifier.classify().

    AE8 audit-trail: `confidence` + `reason` kötelezően reprodukálható,
    a NOT_INVOICE early-exit-hez `confidence >= 0.95` kell (rejection_policy).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    type: IngressType
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    page_count: int = 1
    has_acroform: bool = False
    acroform_fields: dict = Field(default_factory=dict)
    is_invoice_likely: bool = True
    reason: str = ""
    # Page 0 image bytes for downstream LayoutFingerprinter (Software Discovery).
    # NONE in minimal-MVP — render happens in the downstream module.
    page0_image_bytes: Optional[bytes] = None
