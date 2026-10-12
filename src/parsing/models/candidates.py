from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class FieldCandidate:
    """
    Egy mező egy lehetséges értéke egy adott forrásból.

    A HeuristicEngine és a Constitution közötti interfész.
    A HeuristicEngine generate_candidates() metódusa ezeket adja vissza,
    a Constitution pedig ezek közül választ.

    Attributes:
        value: A kinyert érték (str, float, date, stb.)
        source: Forrás azonosító ("qr", "tier2_regex", "ocr", "llm")
        confidence: Megbízhatóság 0.0-1.0 között
        meta: Extra metaadatok (pattern_id, bbox, stb.)

    Example:
        FieldCandidate(
            value="599999993",
            source="qr",
            confidence=1.0,
            meta={"page": 1, "bbox": {...}}
        )
    """

    value: Any
    source: str
    confidence: float
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate confidence range."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")

        # Normalize source to lowercase
        self.source = self.source.lower()
