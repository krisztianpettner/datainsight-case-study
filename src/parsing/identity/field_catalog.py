"""
field_catalog.py — S182 kanonikus mező-katalógus + slot-alias térkép.

A `S182_field_catalog_and_verifiability_map.md` §1 tábláinak KÓD-megfelelője, kiegészítve
a `S182_keyprobe_result.md` által MÉRT slot-alias-párokkal: a QR-adapter (`qr_field_map`
a master YAML-ből) és a vizuális kiolvasás (`tier2_schema`) KÜLÖN slot-kulcsot használ az
identity-fejléc mezőkre (pl. QR `tax_id` ↔ vizuális `seller_nif`). A reconciler ezen a
térképen át gyűjti EGY kanonikus mezőre a QR + vizuális olvasatot.

verifiable_class (design §3):
  "a" — kripto/registry (QR/checksum) — közel-bizonyíték
  "b" — aritmetikai (a számla redundanciájából)
  "c" — read-only (nincs gépi ellenőrzés)

critical — a `field_catalog §1 ✔` + a `conf_swap §7-#4` auto-approve kritikus-halmaza.

Pure stdlib, dep-mentes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class CatalogEntry:
    canonical: str             # a kanonikus mező-név (a reconcile/identity kulcsa)
    qr_slots: List[str]        # a QR-adapter slot-kulcs(ai) a candidates dict-ben
    visual_slots: List[str]    # a vizuális (tier2/ocr/llm) slot-kulcs(ai)
    field_type: str            # normalize_compare típus (NIF/AMOUNT/DATE/INVNUM/CODE/ENUM_DOCTYPE/TEXT)
    verifiable_class: str      # "a" | "b" | "c"
    critical: bool             # a kritikus-mező-halmaz tagja?
    # QR „nincs adat" sentinel-ek (kanonizált alak): ezeket a reconcile NEM QR-olvasatként kezeli.
    # Pl. atcud: a QR H-mező '0' (validation-code 0) = NINCS ATCUD → ne MISMATCH-eljen a vizuálissal.
    qr_absent: tuple = ()
    # A mező szintje: "H"=fejléc/adó-összesítő (1×/doc, a fejléc-identity reconcile dolgozza) ·
    # "L"=tételsor-oszlop (1..n SOR — a desk tételsor-rétegének sémája; a `compute_all` KIHAGYJA,
    # mert egy per-katalógus identity a sorokra értelmetlen). Designated scope: S182_hitl_designated_field_scope.
    level: str = "H"


# ── A katalógus (a probe által mért alias-párokkal) ────────────────────────
# Megj.: ahol qr_slot == visual_slot (invoice_number / amount_net / amount_tax),
# ott a QR és a vizuális MÁR egy kulcs alatt van — a reconciler közvetlen.
_ENTRIES: List[CatalogEntry] = [
    # ── IDENTITY fejléc (a „felek") ──
    CatalogEntry("supplier_nif",   ["tax_id"],          ["seller_nif"],    "NIF",          "a", True),
    CatalogEntry("customer_nif",   ["customer_tax_id"], ["buyer_nif"],     "NIF",          "a", True),
    CatalogEntry("issue_date",     ["date"],            ["issue_date"],    "DATE",         "a", True),
    CatalogEntry("document_number", ["invoice_number"], ["invoice_number"], "INVNUM",      "a", True),
    CatalogEntry("document_type",  ["document_type"],   ["invoice_type"],  "ENUM_DOCTYPE", "a", True),
    CatalogEntry("atcud",          ["anchor"],          ["atcud"],         "CODE",         "a", True,
                 qr_absent=("0",)),
    CatalogEntry("tax_region",     ["fiscal_area"],     [],                "CODE",         "a", True),
    CatalogEntry("customer_country", ["customer_country"], [],             "CODE",         "a", False),
    CatalogEntry("software_cert_no", ["software_cert_no"], ["software_cert"], "CODE",       "a", False),
    # ── TOTÁLOK (az „arany-horgony": QR-O/N + financial_triangle) ──
    CatalogEntry("total_with_vat", ["amount"],          ["amount_gross"],  "AMOUNT",       "b", True),
    CatalogEntry("total_taxable_base", ["amount_net"],  ["amount_net"],    "AMOUNT",       "b", True),
    CatalogEntry("total_vat",      ["amount_tax"],      ["amount_tax"],    "AMOUNT",       "b", True),
    # ── PER-SÁV adó (QR I2–I8; vizuális slot-szintű megfelelő nincs → egy-forrású Fázis 1-ben) ──
    CatalogEntry("tax_base_normal",  ["amount_base_nor"], [],              "AMOUNT",       "a", False),
    CatalogEntry("tax_vat_normal",   ["amount_iva_nor"],  [],              "AMOUNT",       "a", False),
    CatalogEntry("tax_base_reduced", ["amount_base_red"], [],              "AMOUNT",       "a", False),
    CatalogEntry("tax_vat_reduced",  ["amount_iva_red"],  [],              "AMOUNT",       "a", False),
    # ── 🆕 PER-SÁV adó: intermédia (QR I5/I6) + isento (QR I2) — a hiányzó sávok (designated scope B) ──
    CatalogEntry("tax_base_intermedia", ["amount_base_int"], [],           "AMOUNT",       "a", False),
    CatalogEntry("tax_vat_intermedia",  ["amount_iva_int"],  [],           "AMOUNT",       "a", False),
    CatalogEntry("tax_base_isento",     ["amount_base_ise"], [],           "AMOUNT",       "a", False),
    CatalogEntry("vat_exemption_reason", [],               ["exemption_reason"], "TEXT",   "c", False),
    # ── 🆕 A FELEK NEVE/CÍME (read-only, egy-forrású vizuális → BOROSTYÁN; designated scope A) ──
    CatalogEntry("supplier_name",    [],                  ["seller_name"],    "TEXT",      "c", False),
    CatalogEntry("supplier_address", [],                  ["seller_address"], "TEXT",      "c", False),
    CatalogEntry("customer_name",    [],                  ["buyer_name"],     "TEXT",      "c", False),
    CatalogEntry("customer_address", [],                  ["buyer_address"],  "TEXT",      "c", False),
    # ── 🆕 FIZETÉS + EGYÉB (designated scope D) ──
    CatalogEntry("due_date",  [],                         ["due_date"],       "DATE",      "c", False),
    CatalogEntry("currency",  [],                         ["currency"],       "CODE",      "c", False),
    CatalogEntry("iban",      [],                         ["iban"],           "CODE",      "a", False),
    # ── 🆕 TÉTELSOR-OSZLOPOK (level="L" — a desk tételsor-rétegének sémája; compute_all KIHAGYJA; scope C) ──
    CatalogEntry("line_description", [], ["line_description"], "TEXT",   "c", False, level="L"),
    CatalogEntry("line_quantity",    [], ["line_quantity"],    "AMOUNT", "b", False, level="L"),
    CatalogEntry("line_unit_price",  [], ["line_unit_price"],  "AMOUNT", "b", False, level="L"),
    CatalogEntry("line_net_amount",  [], ["line_net_amount"],  "AMOUNT", "b", False, level="L"),
    CatalogEntry("line_vat_rate",    [], ["line_vat_rate"],    "CODE",   "b", False, level="L"),
    CatalogEntry("line_vat_amount",  [], ["line_vat_amount"],  "AMOUNT", "b", False, level="L"),
    CatalogEntry("line_total_gross", [], ["line_total_gross"], "AMOUNT", "b", False, level="L"),
]

CATALOG = {e.canonical: e for e in _ENTRIES}

# A kritikus-mező-halmaz (conf_swap §7-#4 / phase1 §1) — a doc-aggregate ezen áll.
CRITICAL_FIELDS = frozenset(e.canonical for e in _ENTRIES if e.critical)

# Gyors visszakeresés: melyik slot-kulcs melyik kanonikus mezőhöz tartozik (alias-feloldás).
_SLOT_TO_CANONICAL = {}
for _e in _ENTRIES:
    for _s in (_e.qr_slots + _e.visual_slots):
        _SLOT_TO_CANONICAL.setdefault(_s, _e.canonical)


def entries() -> List[CatalogEntry]:
    return list(_ENTRIES)


def get(canonical: str) -> CatalogEntry | None:
    return CATALOG.get(canonical)


def canonical_for_slot(slot: str) -> str | None:
    """Egy nyers candidates-slot-kulcs → kanonikus mező (alias-feloldás), vagy None."""
    return _SLOT_TO_CANONICAL.get(slot)
