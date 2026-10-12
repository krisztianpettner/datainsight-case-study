"""
desk_contract.py — S182 (SÁV 1) → HITL Javító-Munkapad kontraktus-assembler.

A persisted `field_identity` dict (a `constitution_decisions.field_identity` JSON egy eleme — az S182
conf/band FÉL) → a `docs/architecture/44 §11` per-mező kontraktus-rekord. A `value_real` (a PC parse-
artefaktból, UNMASKED) és a `bbox` (a séma / SÁV 2) **KÍVÜLRŐL** jön (a `desk_service` joinolja, kanonikus
mező-néven) — itt NEM a redaktált perzisztált értéket adjuk vissza (K7).

A kötés-pont: a join-kulcs a **kanonikus mező-név** (`field_identity.field`); a séma-update bbox-ait olyan
néven kell regisztrálni, ami a `field_catalog.canonical_for_slot`-tal kanonikusra resolve-ol.

A commit-gate (44 §7) validátorai az S182 `normalize_compare` + `qr_reconcile` — a `verifiable_class`
(a/b/c) mondja meg, melyik oracle fut a humán-beírt értékre.

Pure stdlib, dep-mentes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from parsing.identity import field_catalog

# ── doc-44 §11 `type` kanonikus mezőnként (a landing-mode + commit-gate vezérlője) ──
# {text|nif|number|date|iva|line_item|iban|total|atcud}. A NIF/total/IBAN → ÜRES-cella anti-anchoring.
_CANONICAL_DESK_TYPE = {
    "supplier_nif": "nif", "customer_nif": "nif",
    "issue_date": "date",
    "document_number": "text", "document_type": "text", "tax_region": "text",
    "customer_country": "text", "software_cert_no": "text",
    "atcud": "atcud",
    "total_with_vat": "total", "total_taxable_base": "total", "total_vat": "total",
    "tax_base_normal": "number", "tax_vat_normal": "number",
    "tax_base_reduced": "number", "tax_vat_reduced": "number",
    # 🆕 S182 designated scope: a katalógus-bővítés desk-típusai
    "tax_base_intermedia": "number", "tax_vat_intermedia": "number", "tax_base_isento": "number",
    "vat_exemption_reason": "text",
    "supplier_name": "text", "supplier_address": "text",
    "customer_name": "text", "customer_address": "text",
    "due_date": "date", "currency": "text", "iban": "iban",
    # tételsor-oszlopok (level=L)
    "line_description": "line_item", "line_quantity": "number", "line_unit_price": "number",
    "line_net_amount": "number", "line_vat_rate": "iva", "line_vat_amount": "number",
    "line_total_gross": "number",
}

# 🆕 tételsor-oszlop (kanonikus) → a serialized line-item SOR-dict kulcsa(i) (to_dict / to_dict_v11 alias).
_LINE_COL_TO_ROWKEY: Dict[str, tuple] = {
    "line_description": ("description",),
    "line_quantity":    ("quantity", "qty"),
    "line_unit_price":  ("unit_price",),
    "line_net_amount":  ("net_amount",),
    "line_vat_rate":    ("tax_rate",),
    "line_vat_amount":  ("tax_amount",),
    "line_total_gross": ("gross_amount",),
}
_FIELD_TYPE_FALLBACK = {
    "NIF": "nif", "AMOUNT": "number", "DATE": "date", "PERCENT": "iva",
    "INVNUM": "text", "CODE": "text", "ENUM_DOCTYPE": "text", "TEXT": "text",
}


def desk_type(canonical: str, field_type: Optional[str] = None) -> str:
    """A kanonikus mező → doc-44 §11 `type`. Kanonikus-első, field_type-fallback."""
    if canonical in _CANONICAL_DESK_TYPE:
        return _CANONICAL_DESK_TYPE[canonical]
    if field_type is None:
        e = field_catalog.get(canonical)
        field_type = e.field_type if e else "TEXT"
    return _FIELD_TYPE_FALLBACK.get((field_type or "TEXT").upper(), "text")


def to_desk_field_record(
    fi_dict: Dict[str, Any],
    *,
    value_real: Any = None,
    bbox: Optional[List[float]] = None,
    page: Optional[int] = None,
    field_threshold: Optional[float] = None,
    queue_order: Optional[int] = None,
) -> Dict[str, Any]:
    """Egy persisted field_identity dict → doc-44 §11 per-mező kontraktus-rekord.

    `value_real` + `bbox` KÍVÜLRŐL (a desk_service joinolja a PC parse-artefaktból + a sémából).
    `surfaced`: ZÖLD sávú mező sosem surfaced; egyébként a `field_threshold` (ha adott) dönt.
    """
    field = fi_dict.get("field")
    entry = field_catalog.get(field) if field else None
    ft = entry.field_type if entry else None
    band = fi_dict.get("band")
    est = fi_dict.get("estimate")
    if band is not None:
        surfaced = band != "green"
    elif field_threshold is not None and est is not None:
        surfaced = est < field_threshold
    else:
        surfaced = True  # fail-safe: kétségnél surface-eld (kétségnél PIROS elv)
    return {
        "field_name": field,
        "type": desk_type(field, ft) if field else "text",
        "confidence": est,
        "band": band,                                # ZÖLD/BOROSTYÁN/PIROS (S182 — gazdagabb a puszta küszöbnél)
        "surfaced": surfaced,
        "oracle_class": fi_dict.get("verifiable_class"),  # a/b/c → a commit-gate validátor-választója
        "value_source": fi_dict.get("sources"),
        "hard_veto": fi_dict.get("hard_veto"),
        "verdict": fi_dict.get("verdict"),
        # ── KÍVÜLRŐL joinolva (NEM az S182 redaktált sora) ──
        "value_real": value_real,                    # PC parse-artefakt (UNMASKED, K7-PC-oldal)
        "bbox": bbox,                                # séma / SÁV 2
        "page": page,
        # ── munkapad-paraméterek / write-back placeholderek ──
        "field_threshold": field_threshold,
        "queue_order": queue_order,
        "slots": fi_dict.get("slots"),               # nyers slot-nevek (join-segéd a field_metadata-hoz)
        # committed_value / pristine / provenance: a munkapad ÍRJA vissza (final_values oszlop)
    }


# S195 F-2b (B8): a csupa-nulla numerikus sor extraktor-hiba szignatúra (Moloni-út,
# repró 6a887144: qty=0.0/ár=0,00/nettó=0,00 — nyomtatva 1/21,17/21,17; az IX-úton jó).
# Az Enter-rutin a nullákat MEGERŐSÍTI (élő műszak-bizonyíték) → ilyen sorban a numerikus
# cellák előtöltése ÜRES (az operátor beírja). Az EGYEDI, legit 0,00 érintetlen marad.
_B8_NUM_COLS = {
    "line_quantity",
    "line_unit_price",
    "line_net_amount",
    "line_vat_amount",
    "line_total_gross",
}


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if not any(ch.isdigit() for ch in s):
        return None
    try:
        return float(s.replace(" ", "").replace(".", "").replace(",", "."))
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def _row_zero_defect(row: Dict[str, Any]) -> bool:
    """≥2 jelenlévő numerikus cella és MIND nulla → B8-szignatúra."""
    nums = []
    for canonical in _B8_NUM_COLS:
        keys = _LINE_COL_TO_ROWKEY.get(canonical, ())
        val = next((row[k] for k in keys if k in row and row[k] is not None), None)
        f = _to_float(val)
        if f is not None:
            nums.append(f)
    return len(nums) >= 2 and all(f == 0 for f in nums)


def to_desk_line_item_records(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """🆕 S182 designated scope C: egy serialized line-item SOR → per-CELLA desk-rekordok (level="L").

    A QR NEM fedi a tételsort (csak a SET-szintű Σnettó=sáv-alap) → minden cella egy-forrású vizuális →
    a band v0-ban **BOROSTYÁN** (HITL-front; a pilotban úgyis minden átmegy). A `line_description` a
    **PT-picker**-re kötött (CatalogResolver, vendor-scope). A rekord-alak illeszkedik az assemble
    fejléc-rekordjához (a frontend egységesen kezeli; a `level`+`row_index` adja a tételsor-csoportosítást).
    """
    line_no = row.get("line_no")
    bbox = row.get("bbox")
    page = row.get("page_no")
    conf = row.get("confidence")
    zero_defect = _row_zero_defect(row)  # S195 F-2b (B8)
    out: List[Dict[str, Any]] = []
    for col in field_catalog.entries():
        if getattr(col, "level", "H") != "L":
            continue
        keys = _LINE_COL_TO_ROWKEY.get(col.canonical, ())
        val = next((row[k] for k in keys if k in row and row[k] is not None), None)
        if zero_defect and col.canonical in _B8_NUM_COLS:
            val = None  # B8: hamis 0-előtöltés helyett üres — az operátor a lapról írja be
        out.append({
            "field_id": f"line.{line_no}.{col.canonical}",
            "field_name": col.canonical,
            "type": desk_type(col.canonical, col.field_type),
            "level": "L",
            "row_index": line_no,
            "page": page,
            "value_real": (str(val) if val is not None else None),
            "confidence": conf,
            "confidence_source": "saav1_lineitem",
            "band": "amber",                         # tételsor = egy-forrású → HITL-front (konzervatív)
            "surfaced": True,
            "verdict": None,
            "oracle_class": col.verifiable_class,    # c (description) / b (összegek)
            "hard_veto": None,
            "value_source": ["tier2_lineitem"],
            "bbox_extraction": bbox,
            "bbox_schema_layout": None,
            "bbox_active": bbox,
            "bbox_source": "extraction" if bbox is not None else "none",
            "constraint_reason": None,
            "committed_value": None,
            # PT-picker (CatalogResolver) CSAK a leírásra; vendor-scope (a tételek vendor-függők)
            "picker": col.canonical == "line_description",
            "catalog_scope": "vendor_line" if col.canonical == "line_description" else None,
        })
    return out


def doc_admission(doc_confidence: Optional[float], global_threshold: Optional[float]) -> bool:
    """A doc KIHAGYJA a munkapadot? (44 §11 admission). Fail-closed: hiányzó adat → munkapadra."""
    if doc_confidence is None or global_threshold is None:
        return False
    return doc_confidence >= global_threshold
