"""
FileSchemaRegistry - YAML-based schema loader for Tier 2 pipeline.

Loads master and delta schemas from the filesystem, resolves merges,
and compiles YAML slot definitions into the SLOTS dict format expected
by BaseProfile._process_slot().

Directory layout:
    schemas/
      masters/
        HU_GENERIC_INVOICE.yaml
        PT_GENERIC_INVOICE.yaml
      deltas/
        HU_GENERIC_INVOICE/
          billingo.yaml
"""

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from parsing.schemas.merge import deep_merge

logger = logging.getLogger(__name__)

# parsing/schemas/ -> parsing/ -> project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

# Mapping from string flag names to re flag constants
_RE_FLAGS = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
    "VERBOSE": re.VERBOSE,
}

# ── S195 F-§0 (doc-48 §4, DA-K1): delta-YAML kulcs-allowlist ────────────────
# A .get()-alapú betöltő az elgépelt kulcsot NÉMÁN nyelte (a 'dangerfields'
# elírás = a védelem csendben nem létezik) — trust-rendszerben tilos. Minden
# ismeretlen kulcs HANGOS logger.error-t kap; a betöltés nem bukik el (a
# pipeline megy tovább), de a warn a golden-runban és a suite-ban is látszik.
# ÚJ B-slot kulcstípus bevezetése (doc-48 §4 lista) = ide IS fel kell venni
# (A-protokoll: devils-advocate + golden + tests/parsing/test_delta_allowlist.py).
DELTA_TOP_LEVEL_KEYS = {
    "schema_info",
    "detection",
    "defaults",
    "slot_overrides",
    # B-slot kulcsok (doc-48 §4) — a bevezetésük sorrendjében:
    "danger_fields",  # S195 F-2a: mező → {source/ok} (pl. atcud: visual_only)
}
DELTA_SLOT_KEYS = {
    # compile_slots() olvassa:
    "patterns",
    "flags",
    "validator",
    "cleaner",
    "source",
    "confidence",
    "region",
    "anchor",
    "multi",
    # a pipeline többi szakasza olvassa (2026-07-12-i élő delta-univerzum):
    "fallback",
    "line_item_extractor",
    "box_hint",
    "column_extractors",
    "row_extractor",
    "aggregator",
    "known_issues",
}
# danger_fields értékkészlete mezőnként: {"source": "visual_only"|"qr", "reason": str}
DANGER_FIELD_SOURCES = {"visual_only", "qr"}


class FileSchemaRegistry:
    """File-based YAML schema registry (no DB dependency)."""

    CACHE_TTL = 60  # seconds — deploy freshness guarantee

    def __init__(self, schemas_dir: Optional[Path] = None):
        self._schemas_dir = schemas_dir or (PROJECT_ROOT / "schemas")
        self._masters_dir = self._schemas_dir / "masters"
        self._deltas_dir = self._schemas_dir / "deltas"
        self._cache: Dict[str, Dict] = {}
        self._cache_time: float = 0.0

    def _check_cache_freshness(self):
        """Invalidate cache if TTL expired (deploy freshness for all containers)."""
        if time.time() - self._cache_time > self.CACHE_TTL:
            self._cache.clear()
            self._cache_time = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_masters(self) -> List[str]:
        """Return master schema names (filename without .yaml)."""
        self._check_cache_freshness()
        if not self._masters_dir.is_dir():
            return []
        return sorted(p.stem for p in self._masters_dir.glob("*.yaml"))

    def list_deltas(self, master_name: str) -> List[str]:
        """Return delta names for a given master."""
        self._check_cache_freshness()
        delta_dir = self._deltas_dir / master_name
        if not delta_dir.is_dir():
            return []
        return sorted(p.stem for p in delta_dir.glob("*.yaml"))

    def build_cert_index(self) -> Dict[str, List[tuple]]:
        """Build index: cert_no → [(master, delta_name), ...] from all delta YAMLs.

        Scans the filesystem — no hardcoded catalog needed.
        Call once at startup, result is cached.
        """
        self._check_cache_freshness()
        cache_key = "_cert_index"
        if cache_key in self._cache:
            return self._cache[cache_key]

        index: Dict[str, List[tuple]] = {}
        for master in self.list_masters():
            for delta_name in self.list_deltas(master):
                delta = self._load_delta(master, delta_name)
                if not delta:
                    continue
                info = delta.get("schema_info", {})
                cert_no = str(info.get("cert_no", "")).replace("/AT", "").strip()
                if cert_no:
                    index.setdefault(cert_no, []).append((master, delta_name))

        self._cache[cache_key] = index
        logger.info(
            f"Cert index built: {len(index)} AT codes → {sum(len(v) for v in index.values())} deltas"
        )
        return index

    def build_nif_index(self) -> Dict[str, List[tuple]]:
        """Build index: issuer_nif → [(master, delta_name), ...] from all delta YAMLs.

        Iter 9c (S146.5): enables no-QR routing via issuer-NIF text-discovery.
        Reads `detection.issuer_nif` (scalar or list) from each delta YAML.
        Cached alongside the cert index; both invalidate on CACHE_TTL.
        """
        self._check_cache_freshness()
        cache_key = "_nif_index"
        if cache_key in self._cache:
            return self._cache[cache_key]

        index: Dict[str, List[tuple]] = {}
        for master in self.list_masters():
            for delta_name in self.list_deltas(master):
                delta = self._load_delta(master, delta_name)
                if not delta:
                    continue
                issuer = delta.get("detection", {}).get("issuer_nif")
                if not issuer:
                    continue
                entries = issuer if isinstance(issuer, (list, tuple)) else [issuer]
                for n in entries:
                    digits = re.sub(r"\D", "", str(n))
                    if len(digits) == 9:
                        index.setdefault(digits, []).append((master, delta_name))

        self._cache[cache_key] = index
        logger.info(
            f"NIF index built: {len(index)} issuer NIFs → {sum(len(v) for v in index.values())} deltas"
        )
        return index

    def get_master(self, name: str) -> Dict[str, Any]:
        """Load and return a master schema dict."""
        self._check_cache_freshness()
        cache_key = f"master:{name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        path = self._masters_dir / f"{name}.yaml"
        data = self._load_yaml(path)
        if data is not None:
            self._cache[cache_key] = data
        return data or {}

    def resolve(self, master_name: str, delta_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Resolve a schema: master only, or master + delta merged.

        If delta_name is given, the delta's ``slot_overrides`` are deep-merged
        into the master's ``slots``, and top-level keys (detection, defaults,
        schema_info) are also merged.
        """
        self._check_cache_freshness()
        master = self.get_master(master_name)
        if not master:
            logger.warning("Master schema not found: %s", master_name)
            return {}

        if delta_name is None:
            return master

        cache_key = f"resolved:{master_name}:{delta_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta = self._load_delta(master_name, delta_name)
        if not delta:
            logger.warning(
                "Delta not found: %s/%s, returning master as-is",
                master_name,
                delta_name,
            )
            return master

        # Merge slot_overrides into master slots
        merged = deep_merge(master, {})  # copy master
        if "slot_overrides" in delta:
            merged["slots"] = deep_merge(merged.get("slots", {}), delta["slot_overrides"])

        # Merge top-level keys (detection, defaults, schema_info)
        for key in ("detection", "defaults", "schema_info"):
            if key in delta:
                merged[key] = deep_merge(merged.get(key, {}), delta[key])

        self._cache[cache_key] = merged
        return merged

    def compile_slots(self, resolved: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Compile YAML slot definitions into the format BaseProfile._process_slot() expects.

        Input (from YAML):
            slots:
              tax_id:
                patterns: ['\\b(\\d{8}-\\d-\\d{2})\\b']
                validator: "hu_tax_id"
                confidence: 0.9

        Output:
            {
                "tax_id": {
                    "patterns": [re.compile(...)],
                    "validator": "hu_tax_id",   # string - SchemaProfile resolves later
                    "cleaner": "clean_tax_id",  # string - SchemaProfile resolves later
                    "source": "tier2_regex",
                    "confidence": 0.9
                }
            }
        """
        raw_slots = resolved.get("slots", {})
        compiled: Dict[str, Dict[str, Any]] = {}

        for slot_name, slot_cfg in raw_slots.items():
            if not isinstance(slot_cfg, dict):
                logger.warning("Invalid slot config for '%s', skipping", slot_name)
                continue

            # Compile patterns
            patterns = []
            raw_patterns = slot_cfg.get("patterns", [])
            flags_str = slot_cfg.get("flags", "")
            re_flags = self._parse_re_flags(flags_str)

            for pat_str in raw_patterns:
                try:
                    patterns.append(re.compile(pat_str, re_flags))
                except re.error as e:
                    logger.warning("Invalid regex in slot '%s': %s -> %s", slot_name, pat_str, e)

            if not patterns:
                logger.warning("No valid patterns for slot '%s', skipping", slot_name)
                continue

            compiled[slot_name] = {
                "patterns": patterns,
                "validator": slot_cfg.get("validator"),  # string, resolved later
                "cleaner": slot_cfg.get("cleaner"),  # string, resolved later
                "source": slot_cfg.get("source", "tier2_schema"),
                "confidence": slot_cfg.get("confidence", 0.7),
                "region": slot_cfg.get("region"),  # page region hint (legacy string)
                # S189 (1b): region+label horgony-spec a resolve_anchored_box-hoz (2-gen B-ág).
                # {region, label[], label_rel, ...} — a rung VR/L ezt gate-eli. Nincs → rung V.
                "anchor": slot_cfg.get("anchor"),
                "multi": bool(slot_cfg.get("multi", False)),
            }

        return compiled

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_yaml(self, path: Path) -> Optional[Dict[str, Any]]:
        """Safely load a YAML file."""
        if not path.is_file():
            logger.warning("YAML file not found: %s", path)
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML %s: %s", path, e)
            return None

    def _load_delta(self, master_name: str, delta_name: str) -> Optional[Dict]:
        """Load a delta YAML."""
        cache_key = f"delta:{master_name}:{delta_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        path = self._deltas_dir / master_name / f"{delta_name}.yaml"
        data = self._load_yaml(path)
        if data is not None:
            self.validate_delta_keys(master_name, delta_name, data)
            self._cache[cache_key] = data
        return data

    @staticmethod
    def validate_delta_keys(master_name: str, delta_name: str, data: Dict) -> List[str]:
        """S195 F-§0 (DA-K1): kulcs-allowlist ellenőrzés — HANGOS warn, nem bukás.

        Returns the list of violation strings (üres = tiszta) — a teszt erre épül.
        """
        violations: List[str] = []
        for key in data:
            if key not in DELTA_TOP_LEVEL_KEYS:
                violations.append(f"ismeretlen top-level kulcs: '{key}'")
        for slot_name, slot_cfg in (data.get("slot_overrides") or {}).items():
            if not isinstance(slot_cfg, dict):
                continue
            for key in slot_cfg:
                if key not in DELTA_SLOT_KEYS:
                    violations.append(f"ismeretlen slot-kulcs: '{slot_name}.{key}'")
        for field, cfg in (data.get("danger_fields") or {}).items():
            src = (cfg or {}).get("source") if isinstance(cfg, dict) else cfg
            if src not in DANGER_FIELD_SOURCES:
                violations.append(
                    f"danger_fields.{field}: érvénytelen source '{src}' "
                    f"(engedett: {sorted(DANGER_FIELD_SOURCES)})"
                )
        for v in violations:
            logger.error(
                "DELTA ALLOWLIST SÉRTÉS %s/%s: %s — az elgépelt kulcs NÉMÁN "
                "hatástalan lenne (doc-48 §4 DA-K1); javítsd a YAML-t vagy "
                "vedd fel a kulcsot az allowlistbe (A-protokollal!)",
                master_name,
                delta_name,
                v,
            )
        return violations

    @staticmethod
    def _parse_re_flags(flags_str: str) -> int:
        """Convert 'IGNORECASE|MULTILINE' string to re flags int."""
        if not flags_str:
            return 0
        result = 0
        for name in flags_str.split("|"):
            name = name.strip().upper()
            if name in _RE_FLAGS:
                result |= _RE_FLAGS[name]
            else:
                logger.warning("Unknown regex flag: %s", name)
        return result
