"""
Tier 2 Heuristic Extraction Engine (Orchestrator)

Moduláris, country-specifikus field extraction Strategy Pattern alapon.

Architecture:
- Orchestrator selects best-matching country profile
- Each profile implements detect() and extract()
- Threshold-based selection (configurable via config.yaml)
- QR/Barcode data integration for enhanced detection

Session 50 Update:
- Configuration loaded from config.yaml via settings module
- Confidence threshold configurable

Session 51 Update:
- Passes pdfplumber_page to profiles for spatial layout analysis
- Enables "Digital Scissors" section detection

M2.4 Integration (Session 57):
- Integrates Constitution for candidate evaluation
- Returns 'decision' in process_v2

Usage:
    engine = HeuristicEngine()
    result = engine.process(text, qr_data)
    # {
    #   'country': 'PT',
    #   'confidence': 1.0,
    #   'data': {'date': '2024-01-15', 'tax_id': '599999993', ...}
    # }

Created: 2026-01-20 (Session 41 - Tier 2 Architecture)
Updated: 2026-01-23 (Session 50) - Centralized config via settings.py
Updated: 2026-01-23 (Session 51) - Spatial Layout Engine support
Updated: 2026-02-02 (Session 57) - Constitution Integration
"""

import inspect
import logging
from typing import Any, Dict, List, Optional, Tuple

from parsing.models.constitution import ConstitutionDecision, DecisionStatus

from .profiles import CountryProfile, GenericProfile, HungaryProfile, PortugalProfile
from .settings import settings

logger = logging.getLogger(__name__)


class HeuristicEngine:
    """
    Orchestrator for country-specific heuristic extraction.

    Strategy Pattern implementation with dynamic profile selection.

    Workflow:
    1. Initialize all available profiles
    2. Run detect() on each profile
    3. Select winner (highest confidence above threshold)
    4. Run extract() on winner
    5. Return structured result

    Threshold: configurable via config.yaml (default: 0.4)
    """

    def __init__(self, threshold: float = None):
        """
        Initialize HeuristicEngine with available country profiles.

        Args:
            threshold: Minimum confidence score for profile selection (0.0-1.0)
                       If not specified, uses value from config.yaml (processing.confidence_threshold)
        """
        # Use settings module (Session 50) for default threshold
        self.threshold = (
            threshold if threshold is not None else settings.processing.confidence_threshold
        )
        self.profiles: List[CountryProfile] = self._load_profiles()
        self._constitution = (
            None  # Lazy init — Constitution imported on first access to break circular dep
        )
        logger.info(
            f"HeuristicEngine initialized with {len(self.profiles)} profiles (threshold: {threshold})"
        )

    @property
    def constitution(self):
        """Lazy-load Constitution (cached). Import is deferred to avoid circular import."""
        if self._constitution is None:
            from orchestration.constitution import Constitution

            self._constitution = Constitution()
        return self._constitution

    def _load_profiles(self) -> List[CountryProfile]:
        """
        Load all available country profiles.

        Loads hardcoded profiles first, then YAML schema profiles if enabled.
        All profiles compete via detect() confidence — no country_code skip.

        Returns:
            list: Instantiated CountryProfile objects
        """
        profiles = [
            PortugalProfile(),
            HungaryProfile(),
            GenericProfile(),  # Fallback for international invoices
        ]

        # Load YAML schema profiles alongside hardcoded ones
        if settings.schemas.enable_schema_profiles:
            try:
                from parsing.profiles.schema_profile import SchemaProfile
                from parsing.schemas.registry import FileSchemaRegistry

                registry = FileSchemaRegistry()
                for master_name in registry.list_masters():
                    resolved = registry.resolve(master_name)
                    slots = registry.compile_slots(resolved)
                    if slots:
                        profiles.append(SchemaProfile(resolved, slots))
                        logger.info(f"Schema profile loaded: {master_name}")

                # F3.0 K2-B (S146.7): attach country-master `_resolved_schema`
                # to hardcoded profiles so the inherited `_add_line_items_candidates`
                # ladder hook can fire with the YAML slot config.
                # Detection logic (Portugal QR/NIF/ATCUD, Hungary tax_id, etc.)
                # stays hardcoded — only the line_items extraction borrows the
                # YAML. Best of both worlds: hardcoded detection + YAML line_items.
                country_to_master = {
                    "PT": "PT_GENERIC_INVOICE",
                    "HU": "HU_GENERIC_INVOICE",
                }
                for profile in profiles:
                    if hasattr(profile, "_resolved_schema"):
                        continue  # SchemaProfile-ok már rendelkeznek vele
                    cc = getattr(profile, "country_code", None)
                    master = country_to_master.get(cc)
                    if not master:
                        continue
                    try:
                        profile._resolved_schema = registry.resolve(master)
                        logger.info(
                            f"K2-B: attached schema {master} to {profile.name} "
                            f"for line_items ladder activation"
                        )
                    except Exception as e:
                        logger.debug(
                            f"K2-B schema attach failed for {profile.name}: {e}"
                        )
            except Exception as e:
                logger.warning(f"Schema profiles loading failed: {e}")

        logger.debug(f"Loaded profiles: {[p.name for p in profiles]}")
        return profiles

    def detect_best_profile(
        self, text: str, qr_data: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[CountryProfile], float]:
        """
        Detect best-matching country profile.

        Args:
            text: OCR text from document
            qr_data: QR/Barcode results from qr_barcode_engine_v2

        Returns:
            tuple: (best_profile, confidence_score)
                   Returns (None, 0.0) if no profile exceeds threshold
        """
        best_profile = None
        best_confidence = 0.0

        logger.info("Running detection across all profiles...")
        for profile in self.profiles:
            confidence = profile.detect(text, qr_data)
            logger.debug(f"{profile.name}: Confidence = {confidence:.2f}")

            if confidence > best_confidence:
                best_confidence = confidence
                best_profile = profile

        if best_confidence < self.threshold:
            logger.warning(
                f"No profile exceeded threshold ({self.threshold}). Best: {best_profile.name if best_profile else 'None'} @ {best_confidence:.2f}"
            )
            return None, 0.0

        logger.info(f"Selected profile: {best_profile.name} (Confidence: {best_confidence:.2f})")
        return best_profile, best_confidence

    def process(
        self,
        text: str,
        qr_data: Optional[List[Dict[str, Any]]] = None,
        validate: bool = True,
        pdfplumber_page: Optional[Any] = None,
        pdf_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process document with heuristic extraction.

        Workflow:
        1. Detect best country profile
        2. Extract fields using selected profile
        3. Validate extracted data (optional)
        4. Return structured result

        Session 51 Update:
        - pdfplumber_page: Optional pdfplumber.Page for spatial layout analysis
        - pdf_path: Optional path to PDF for debug visualization

        Args:
            text: OCR text from document
            qr_data: QR/Barcode results (optional)
            validate: Run validation on extracted data (default: True)
            pdfplumber_page: pdfplumber.Page for spatial analysis (Session 51)
            pdf_path: Path to PDF for debug visualization (Session 51)

        Returns:
            dict: Extraction result
                {
                    'country': str (country_code or None),
                    'confidence': float (detection confidence),
                    'data': dict (extracted fields),
                    'profile_name': str (human-readable name),
                    'validation_passed': bool (if validate=True),
                    'error': str (if extraction failed)
                }

        Example:
            {
                'country': 'PT',
                'confidence': 1.0,
                'profile_name': 'Portugal (ATCUD/NIF)',
                'data': {
                    'date': '2024-01-15',
                    'tax_id': '599999993',
                    'invoice_number': 'ABCD1234-5678',
                    'amount': 1500.00,
                    'currency': 'EUR',
                    'anchor': 'ABCD1234-5678'
                },
                'validation_passed': True
            }
        """
        result = {
            "country": None,
            "confidence": 0.0,
            "data": {},
            "profile_name": None,
            "validation_passed": None,
            "error": None,
        }

        try:
            # Step 1: Detect best profile
            best_profile, confidence = self.detect_best_profile(text, qr_data)

            if best_profile is None:
                result["error"] = f"No profile exceeded threshold ({self.threshold})"
                logger.warning(result["error"])
                return result

            # Phase 3.3: Software Discovery — 1:N delta competition
            sw_profile = self._resolve_software_profile(text, qr_data)
            if sw_profile:
                best_profile = sw_profile

            # Step 2: Extract fields
            # SESSION 51: Pass pdfplumber_page for spatial layout (if profile supports it)
            logger.info(f"Extracting fields with {best_profile.name}...")
            try:
                # Try new signature with pdfplumber_page (Session 51)
                extracted_data = best_profile.extract(
                    text, qr_data, pdfplumber_page=pdfplumber_page, pdf_path=pdf_path
                )
            except TypeError:
                # Fallback for profiles that don't support new parameters yet
                logger.debug(
                    f"{best_profile.name} doesn't support pdfplumber_page, using legacy signature"
                )
                extracted_data = best_profile.extract(text, qr_data)

            # Step 3: Validate (optional)
            validation_passed = None
            if validate:
                validation_passed = best_profile.validate(extracted_data)
                logger.info(f"Validation result: {'PASS' if validation_passed else 'FAIL'}")

            # Step 4: Build result
            result.update(
                {
                    "country": best_profile.country_code,
                    "confidence": confidence,
                    "data": extracted_data,
                    "profile_name": best_profile.name,
                    "validation_passed": validation_passed,
                }
            )

            logger.info(
                f"HeuristicEngine processing complete: {result['country']} @ {result['confidence']:.2f}"
            )

        except Exception as e:
            result["error"] = f"Extraction failed: {str(e)}"
            logger.error(result["error"], exc_info=True)

        return result

    def process_v2(
        self,
        text: str,
        qr_data: Optional[List[Dict[str, Any]]] = None,
        pdfplumber_page: Optional[Any] = None,
        pdf_path: Optional[str] = None,
        ocr_confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Process document with heuristic extraction V2 (Candidates Pipeline).

        V2-First Pipeline (Session 69):
        Returns 'candidates' + 'decision' + 'line_items'.
        No legacy_data — V2 is the single source of truth.

        Args:
            text: OCR text from document
            qr_data: QR/Barcode results (optional)
            pdfplumber_page: pdfplumber.Page for spatial analysis
            pdf_path: Path to PDF for debug visualization

        Returns:
            dict: Extraction result
                {
                    'country': str,
                    'confidence': float,
                    'candidates': Dict[str, List[FieldCandidate]],
                    'decision': ConstitutionDecision,
                    'line_items': List[Dict],
                    'line_items_metadata': Dict,
                    'profile_name': str,
                    'error': str
                }
        """
        result = {
            "country": None,
            "confidence": 0.0,
            "candidates": {},
            "decision": None,
            "line_items": [],
            "line_items_metadata": {},
            "profile_name": None,
            "error": None,
        }

        try:
            # Step 1: Detect best profile
            best_profile, confidence = self.detect_best_profile(text, qr_data)

            if best_profile is None:
                result["error"] = f"No profile exceeded threshold ({self.threshold})"
                return result

            # Phase 3.3: Software Discovery — 1:N delta competition
            sw_profile = self._resolve_software_profile(text, qr_data)
            if sw_profile:
                best_profile = sw_profile

            # Step 2: Generate Candidates
            logger.info(f"Generating candidates with {best_profile.name} (V2)...")

            # F2.5 (S146.7): pass pdf_path to profiles that support it
            # (SchemaProfile uses it for the Tier 2 line_items ladder via
            # `_add_line_items_candidates`). Vanilla BaseProfile subclasses keep
            # the legacy 2-arg signature — detected via inspect to stay safe.
            #
            # S168 cert-aware ladder gate: only forward pdf_path into the
            # candidate-generation ladder when the ACTIVE profile carries a
            # delta Layer-0 `box_hint` (i.e. `_resolve_software_profile` matched
            # a per-cert delta whose `line_items` slot defines box_hint +
            # column_extractors → the deterministic tier2_schema_bbox ladder).
            # For master-only profiles (hardcoded PortugalProfile, or any
            # SchemaProfile lacking a box_hint) we keep pdf_path OUT of the
            # ladder so the master-level Layer 1/2/3 extractors (Lattice / Stream
            # / Tabula, driven by the master's `column_keywords`) do NOT newly
            # fire — preserving the prior Tier-3 line-item path exactly (no
            # regression on non-delta invoices). The real pdf_path is still used
            # below for the Tabula hint + Tier-3 context, unchanged.
            ladder_pdf_path = pdf_path if self._profile_has_box_hint(best_profile) else None
            _gc_params = inspect.signature(best_profile.generate_candidates).parameters
            _gc_kwargs = {}
            if "pdf_path" in _gc_params:
                _gc_kwargs["pdf_path"] = ladder_pdf_path
            # S182 SÁV-2 + S189 (0a): a match-site bbox a VALÓS pdf_path MINDEN lapján keres
            # (base.py: per-page word-index, first-page-local-unique). A bbox_pdf_path a
            # ladder-gating-től FÜGGETLEN csatorna (a ladder továbbra is a ladder_pdf_path-ot
            # kapja → regresszió-mentes); base.py flag-gated (S182_SAV2_BBOX), off-nál no-op és
            # nem nyit PDF-et. Kész pdfplumber_page-et (ha a caller ad) egy-oldalas fallbackként
            # adunk át; a lap-életciklust base.py birtokolja.
            if "bbox_pdf_path" in _gc_params and pdf_path:
                _gc_kwargs["bbox_pdf_path"] = pdf_path
            if "pdfplumber_page" in _gc_params and pdfplumber_page is not None:
                _gc_kwargs["pdfplumber_page"] = pdfplumber_page
            candidates = best_profile.generate_candidates(text, qr_data, **_gc_kwargs)

            # Tag multi fields so Constitution knows to keep lists
            multi_fields = {
                name for name, cfg in best_profile.SLOTS.items() if cfg.get("multi", False)
            }
            if multi_fields:
                candidates["_multi_fields"] = list(multi_fields)

            # Step 3: Line Item Extraction
            line_items = []
            line_items_metadata = {}

            # F3.0 (S146.7) — K4 arbitráció: Tier 2 ladder wins if produced rows.
            # The BaseProfile._add_line_items_candidates hook (F3.0.a) emits a
            # `candidates["line_items"]` FieldCandidate when any of the 4 layers
            # produces DocumentRows. Bridge via `DocumentRow.to_legacy_dict()` to
            # the legacy dict-shape consumed by UnifiedInvoiceData.from_v2_decision
            # (`parsing/models/output.py:501-518`). Tier 3 LLM SKIPPED when ladder
            # is authoritative — deterministic priority per 24-doksi §2.2.
            ladder_cands = candidates.get("line_items")
            ladder_rows = None
            if ladder_cands:
                # F2.5 emits exactly one FieldCandidate with meta["rows"] = [DocumentRow,...]
                meta = getattr(ladder_cands[0], "meta", None) or {}
                ladder_rows = meta.get("rows")

            if ladder_rows:
                # Ladder authoritative path — bridge rows → legacy dict shape
                line_items = [row.to_legacy_dict() for row in ladder_rows]
                line_items_metadata = {
                    "source": ladder_cands[0].source,
                    "extractor_ladder_step": meta.get("extractor_ladder_step"),
                    "ladder_row_count": len(ladder_rows),
                    "ladder_confidence": ladder_cands[0].confidence,
                }
                logger.info(
                    f"Line items from Tier 2 ladder ({ladder_cands[0].source}): "
                    f"{len(line_items)} rows"
                )
            else:
                # ── S168 SPIKE-4 — deterministic ColGeom for delta-less / ATCUD ──
                # This `else` is reached ONLY when the Tier-2 ladder produced no
                # rows — i.e. delta-less profiles (the Portugal ATCUD/NIF cluster
                # and the rare schema_bbox-empty fallbacks) that historically went
                # straight to the non-deterministic tier3 LLM (FAILED↔SUCCESS
                # flips, row truncation on large tables). Try the calibration-free
                # geometry extractors FIRST; accept their rows ONLY when they are
                # arith-coherent (net≈qty×unit). Otherwise fall through to tier3
                # unchanged — so a profile geometry cannot read (heterogeneous
                # receipts) keeps the prior LLM path exactly (no regression).
                #
                # ANTI-PSEUDO-METRIC: every emitted cell comes from page geometry
                # (qty/unit/net read off x-bands). The QR is a SELECTOR/validator
                # only (Σnet reconcile inside _maybe_apply_*); it never writes a
                # cell. Gated by ATCUD_DETERMINISTIC_DISABLE for before/after.
                import os as _os
                det_disabled = _os.environ.get(
                    "ATCUD_DETERMINISTIC_DISABLE", ""
                ) in ("1", "true", "True", "yes")
                det_rows = None
                expected_rows = None
                if pdf_path and not det_disabled:
                    det_rows, expected_rows = self._try_deterministic_li_for_delta_less(
                        pdf_path, qr_data
                    )

                if det_rows:
                    line_items = [r.to_legacy_dict() for r in det_rows]
                    line_items_metadata = {
                        "source": "tier2_colgeom_atcud",
                        "ladder_row_count": len(det_rows),
                        "expected_rows": expected_rows,
                        "path": "spike4_deterministic_delta_less",
                    }
                    logger.info(
                        f"S168 SPIKE-4: delta-less deterministic geometry won "
                        f"({len(line_items)} rows, expected≈{expected_rows})"
                    )

                # Tier 3 LLM fallback (Session 70 legacy path — unchanged)
                # Tier 3 runs first so line items are available for Constitution constraints.

                # Session 70: Tabula structured hint (if pdf_path available)
                tabula_hint = None
                if not det_rows and pdf_path:
                    try:
                        from parsing.line_items.extractor import LineItemExtractor

                        tabula_ext = LineItemExtractor()
                        tabula_items = tabula_ext.extract(pdf_path)
                        if tabula_items:
                            from dataclasses import asdict

                            tabula_hint = [asdict(item) for item in tabula_items]
                            logger.info(f"Tabula hint: {len(tabula_hint)} items found")
                    except Exception as e:
                        logger.debug(f"Tabula hint failed (non-critical): {e}")

                if not det_rows and hasattr(best_profile, "_run_tier3_extraction"):
                    try:
                        # Extract amount/currency from candidates (quick pick for Tier 3 context)
                        _amount = self._quick_pick(
                            candidates, ["amount", "amount_gross", "gross_amount"]
                        )
                        _currency = self._quick_pick(candidates, ["currency"])
                        tier3_ctx = {
                            "amount": _amount,
                            "currency": _currency,
                        }
                        best_profile._run_tier3_extraction(
                            tier3_ctx,
                            text,
                            pdfplumber_page,
                            pdf_path,
                            tabula_hint=tabula_hint,
                        )
                        line_items = tier3_ctx.get("line_items", [])
                        line_items_metadata = tier3_ctx.get("_metadata", {}).get(
                            "line_items", {}
                        )
                        # S168 SPIKE-4 — deterministic ROW-COUNT anchor: when tier3
                        # IS used (geometry refused), compare the LLM row count to a
                        # pdfplumber text-layer row-count pre-pass so truncation is
                        # DETECTABLE (sub-group A: large >6-row utility bills where
                        # the LLM stops mid-table). Recorded for diagnosis; does NOT
                        # mutate the cells (the QR/geometry never writes them here).
                        if expected_rows is None and pdf_path:
                            expected_rows = self._expected_data_row_count(pdf_path)
                        if expected_rows and line_items:
                            line_items_metadata = dict(line_items_metadata or {})
                            line_items_metadata["expected_rows"] = expected_rows
                            line_items_metadata["row_truncated"] = (
                                len(line_items) < expected_rows
                            )
                    except Exception as t3_err:
                        logger.warning(f"Tier 3 extraction failed in V2: {t3_err}")

            # Step 3b: Inject line items into candidates for Constitution (Session 70)
            if line_items:
                candidates["_line_items"] = line_items

            # Step 3c: ConfidenceRouter — per-slot self-healing decision (Session 130)
            # NON-mutating: produces audit trace alongside the existing candidates flow.
            # Constitution continues to evaluate raw candidates; the router trace is
            # attached to the result for audit/HITL visibility.
            router_trace = []
            router_summary = {}
            try:
                from parsing.routing import ConfidenceRouter

                if not hasattr(self, "_router"):
                    # Session 130 K6 fix: runtime policy YAMLs live under config/policies/
                    self._router = ConfidenceRouter.from_yaml(
                        "/app/config/policies/confidence_policy.yaml"
                    )
                # Pass only real-slot candidates (skip control keys like _multi_fields, _line_items)
                routable = {
                    k: v
                    for k, v in candidates.items()
                    if not k.startswith("_") and isinstance(v, list)
                }
                _, router_trace = self._router.route(
                    routable,
                    context={
                        "text": text,
                        "pdf_path": pdf_path,
                        "profile": best_profile.name,
                    },
                )
                router_summary = self._router.summarize(router_trace)
                logger.info(f"ConfidenceRouter summary: {router_summary}")
            except Exception as e:
                logger.warning(f"ConfidenceRouter evaluation failed (non-blocking): {e}")

            # Step 4: Constitution Decision (M2.4) + Confidence Scoring (G3 — Session 113)
            decision = None
            try:
                decision = self.constitution.evaluate(candidates, ocr_confidence=ocr_confidence)
            except Exception as e:
                # Fallback if Constitution crashes
                logger.error(f"Constitution crashed: {e}", exc_info=True)
                decision = ConstitutionDecision(
                    status=DecisionStatus.HITL_FULL,
                    selected_values={},
                    constraint_results=[],
                    confidence=0.0,
                    reason=f"Constitution crashed: {str(e)}",
                    fields_to_review=[],
                    meta={"error": str(e), "fallback": True},
                )

            # F3.2 (S146.7) — Constitution → router recalibration. Line-item
            # constraint PASS/FAIL feeds back into the line_items winner's
            # confidence (24-doksi §5.3). Updates router_trace so HITL UI
            # sees the recalibrated value.
            if (
                decision
                and decision.constraint_results
                and hasattr(self, "_router")
                and self._router is not None
            ):
                try:
                    # Build slot→winner dict from router_trace for recalibration input
                    final_for_recalib = {
                        d.slot: type(
                            "RecalibWinner",
                            (),
                            {
                                "confidence": d.winner_confidence,
                                "source": d.winner_source,
                                "value": d.winner_value,
                            },
                        )()
                        for d in router_trace
                    }
                    self._router.recalibrate_with_constraints(
                        final_for_recalib,
                        decision.constraint_results,
                        trace=router_trace,
                    )
                except Exception as e:
                    logger.warning(
                        f"ConfidenceRouter recalibrate_with_constraints failed: {e}"
                    )

            # Step 4b: ConstraintValidator boost/penalty (G3 — Session 113)
            # S182 Fázis 1: a doc-conf MOST az adat-azonossági identity aggregátuma
            # (Constitution._make_decision). A régi CV boost/penalty a RÉGI conf-eloszlásra
            # hangolt → a Fázis 4 kalibrációig NEM írhatja felül az identity-t (tiszta csere,
            # nincs dual-SoT). A kapu úgyis OFF (H1), így a confidence-tweak Fázis 1-ben felesleges.
            from orchestration.constitution import S182_AUTO_APPROVE_DISABLED as _S182_OFF
            if decision and decision.confidence > 0 and not _S182_OFF:
                try:
                    from pdf_parser.constraint_validator import ConstraintValidator

                    cv = ConstraintValidator()
                    sv = decision.selected_values or {}
                    val_result = cv.validate_invoice(
                        {
                            "net_total": sv.get("amount_net") or sv.get("total_net"),
                            "vat_total": sv.get("amount_tax") or sv.get("total_tax"),
                            "gross_total": sv.get("amount") or sv.get("total_gross"),
                            "line_items": line_items,
                            "qr_data": qr_data,
                            "nif": sv.get("tax_id") or sv.get("seller_nif"),
                            "iban": sv.get("iban"),
                        }
                    )
                    decision.confidence = cv.apply_adjustments(decision.confidence, val_result)
                    decision.meta["constraint_validation"] = {
                        "boost": val_result.confidence_boost,
                        "penalty": val_result.confidence_penalty,
                    }
                    # NOTE: Session 130 had a post-boost re-route here that
                    # could lift HITL_FULL/REJECTED decisions back into
                    # AUTO_APPROVE if the CV boost brought the confidence
                    # over the auto_approve threshold.  That was removed
                    # because it over-rode the Constitution's diagnostic —
                    # e.g. QR Consistency FAIL (OCR disagreed with QR) is
                    # exactly the case where the invoice SHOULD land in
                    # HITL/REJECTED.  The Constitution's severity-based
                    # penalties are the correct signal; the CV boost is a
                    # confidence tweak, not a status override.
                except Exception as cv_err:
                    logger.warning(f"ConstraintValidator failed: {cv_err}")

            # Step 5: Build result
            result.update(
                {
                    "country": best_profile.country_code,
                    "confidence": decision.confidence if decision else confidence,
                    "candidates": candidates,
                    "decision": decision,
                    "line_items": line_items,
                    "line_items_metadata": line_items_metadata,
                    "profile_name": best_profile.name,
                    "router_trace": [d.to_dict() for d in router_trace],
                    "router_summary": router_summary,
                }
            )

            logger.info(
                f"HeuristicEngine V2 complete: {result['country']} - Decision: {decision.status.value}"
            )

        except Exception as e:
            result["error"] = f"Candidate generation failed: {str(e)}"
            logger.error(result["error"], exc_info=True)

        return result

    def _resolve_software_profile(
        self, text: str, qr_data: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Any]:
        """Phase 3.3: Software Discovery — deterministic schema override.

        Handles 1:N AT code → delta mapping via anchor competition.
        Single delta = direct override (fast path).
        Multiple deltas = detect() competition among them.
        """
        try:
            from parsing.discovery.software_registry import identify_software

            # S195 F-3a: a korai `return None`-ok itt KIUGROTTAK a metódusból, mielőtt
            # az Iter 9c NIF-fallback (lent) sorra került volna → az R='0' QR-es vendorok
            # (NOS/Galp/NOWO — cert-routing HALOTT, S194 vendor-intel C3) SOSEM érték el
            # a NIF-útjukat. A nem-talált cert-ágak most ÁTESNEK a NIF-fallbackre;
            # a sikeres cert-match viselkedése változatlan.
            sw_info = identify_software(text, qr_data)
            matches = []
            if sw_info:
                cert_no = sw_info["cert_no"]
                logger.info(
                    f"Software detected: {sw_info['name']} ({cert_no}/AT) via {sw_info['source']}"
                )

                from parsing.profiles.schema_profile import SchemaProfile
                from parsing.schemas.registry import FileSchemaRegistry

                registry = FileSchemaRegistry()

                # Filesystem-driven: cert_no → delta YAML-ek (schema_info.cert_no)
                cert_index = registry.build_cert_index()
                matches = cert_index.get(cert_no, [])
                if not matches:
                    logger.debug(f"No delta schema for {cert_no}/AT, using master profile")

            if not matches:
                pass  # → Iter 9c NIF-fallback (lent)
            elif len(matches) == 1:
                master, delta_name = matches[0]
                resolved = registry.resolve(master, delta_name)
                slots = registry.compile_slots(resolved)
                if slots:
                    logger.info(f"Delta loaded: {delta_name} (from {master})")
                    return SchemaProfile(resolved, slots)
            else:
                # Multiple deltas for same AT code → anchor competition
                best_profile, best_conf = None, 0.0
                for master, delta_name in matches:
                    try:
                        resolved = registry.resolve(master, delta_name)
                        slots = registry.compile_slots(resolved)
                        if not slots:
                            continue
                        profile = SchemaProfile(resolved, slots)
                        conf = profile.detect(text, qr_data)
                        logger.debug(f"Delta {delta_name}: confidence={conf:.2f}")
                        if conf > best_conf:
                            best_conf = conf
                            best_profile = profile
                    except Exception as e:
                        logger.warning(f"Delta {delta_name} load failed: {e}")
                if best_profile:
                    logger.info(f"Best delta: {best_profile.name} (confidence={best_conf:.2f})")
                    return best_profile
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Software discovery failed: {e}")

        # Iter 9c (S146.5): issuer-NIF text-based fallback delta swap.
        # When cert# discovery is silent (typical for QR-less invoices), try to
        # recognize the issuer via NIFs printed near a label in the invoice text,
        # and match against deltas that declare `detection.issuer_nif`. Surgical:
        # only fires when a NIF is both found in text *and* claimed by some delta —
        # the rest of the corpus is untouched. Multiple deltas with the same NIF
        # fall back to detect() competition among them.
        try:
            from parsing.profiles.schema_profile import (
                SchemaProfile,
                _extract_text_nifs,
            )
            from parsing.schemas.registry import FileSchemaRegistry

            text_nifs = _extract_text_nifs(text)
            # S195 F-3a: a QR A-mezője MAGA a kibocsátó NIF (Portaria 195/2020, determinista).
            # Az R='0' vendoroknál (NOS/Galp/NOWO — cert-routing halott) a szöveg-címkés NIF
            # gyakran nem extraktálható (reverz/inline réteg), a QR-A viszont mindig ott van.
            # A QR-A elsőbbséget kap (determinista forrás), a címkés text-NIF-ek utána.
            qr_a_nifs = []
            for _qe in qr_data or []:
                _dp = _qe.get("data_parsed", {}) if isinstance(_qe, dict) else {}
                if not isinstance(_dp, dict):
                    continue
                import re as _re_nif

                _a = _re_nif.sub(r"\D", "", str(_dp.get("A", "")))
                if len(_a) == 9 and _a not in qr_a_nifs:
                    qr_a_nifs.append(_a)
            candidate_nifs = qr_a_nifs + sorted(text_nifs - set(qr_a_nifs))
            if not candidate_nifs:
                return None

            registry = FileSchemaRegistry()
            nif_index = registry.build_nif_index()
            if not nif_index:
                return None

            for nif in candidate_nifs:
                matches = nif_index.get(nif, [])
                if not matches:
                    continue
                if len(matches) == 1:
                    master, delta_name = matches[0]
                    resolved = registry.resolve(master, delta_name)
                    slots = registry.compile_slots(resolved)
                    if slots:
                        logger.info(
                            f"Issuer-NIF delta swap: {delta_name} via NIF {nif} "
                            f"(from {master})"
                        )
                        return SchemaProfile(resolved, slots)
                else:
                    best_profile, best_conf = None, 0.0
                    for master, delta_name in matches:
                        try:
                            resolved = registry.resolve(master, delta_name)
                            slots = registry.compile_slots(resolved)
                            if not slots:
                                continue
                            profile = SchemaProfile(resolved, slots)
                            conf = profile.detect(text, qr_data)
                            logger.debug(
                                f"Issuer-NIF delta {delta_name}: confidence={conf:.2f}"
                            )
                            if conf > best_conf:
                                best_conf = conf
                                best_profile = profile
                        except Exception as e:
                            logger.warning(f"Delta {delta_name} load failed: {e}")
                    if best_profile:
                        logger.info(
                            f"Issuer-NIF best delta: {best_profile.name} via NIF {nif} "
                            f"(conf={best_conf:.2f})"
                        )
                        return best_profile
        except Exception as e:
            logger.warning(f"Issuer-NIF resolution failed: {e}")
        return None

    @staticmethod
    def _profile_has_box_hint(profile: Any) -> bool:
        """S168: True iff the profile's resolved schema defines a Layer-0
        line_items `box_hint` (the per-cert delta's tier2_schema_bbox config).

        Used to scope the line-item ladder activation to delta-resolved
        profiles only — master-only profiles (no box_hint) keep the prior
        Tier-3 line-item path, so passing pdf_path does not regress them.
        """
        resolved = getattr(profile, "_resolved_schema", None)
        if not isinstance(resolved, dict):
            return False
        line_items = resolved.get("slots", {}).get("line_items", {})
        return bool(isinstance(line_items, dict) and line_items.get("box_hint"))

    # ────────────────────────────────────────────────────────────────────
    # S168 SPIKE-4 — deterministic line-items for delta-less / ATCUD invoices
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _row_arith_coherent(cells: Dict[str, Any]) -> bool:
        """net ≈ qty × unit (±2% / ±0.05) — the deterministic 'real line' signal.
        Mirrors BaseProfile._row_arith_coherent but works on a legacy dict."""
        try:
            q = cells.get("quantity")
            u = cells.get("unit_price")
            n = cells.get("net_amount")
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

    def _try_deterministic_li_for_delta_less(
        self,
        pdf_path: str,
        qr_data: Optional[List[Dict[str, Any]]],
    ) -> Tuple[Optional[List[Any]], Optional[int]]:
        """S168 SPIKE-4 — run ColGeom (+ Graphic) on a delta-less invoice and
        return its rows ONLY when they are deterministically coherent.

        Returns ``(rows, expected_rows)``:
          - ``rows`` = the merged/cleaned DocumentRows when ≥1 is arith-coherent
            (net≈qty×unit); ``None`` otherwise → caller falls back to tier3.
          - ``expected_rows`` = a pdfplumber text-layer row-count pre-pass, so a
            tier3 fallback (when geometry refuses) can detect truncation.

        QR-isolation: the cells are read purely from page geometry. The QR is a
        SELECTOR only — when present and reconciling, it RAISES confidence in the
        ColGeom read (an extra accept path for single/sparse tables); it never
        writes a cell. ``COLGEOM_DISABLE_QR_GATE`` removes the QR involvement so
        the geometry-only contribution can be measured in isolation.
        """
        from parsing.line_items.colgeom_extractor import ColGeomExtractor
        from parsing.line_items.document_cell import (
            drop_summary_and_section_rows,
            merge_continuation_rows,
        )

        expected_rows = self._expected_data_row_count(pdf_path)

        rows: List[Any] = []
        try:
            rows = ColGeomExtractor().extract_as_document_rows(pdf_path) or []
        except Exception:
            logger.debug("SPIKE-4 ColGeom failed", exc_info=True)
            rows = []

        # Graphic named-header extractor (EDP/Goldenergy-style) as a second
        # deterministic source — keep whichever yields MORE coherent rows.
        try:
            from parsing.line_items.graphic_table_extractor import (
                GraphicTableExtractor,
            )

            g_rows = GraphicTableExtractor().extract_as_document_rows(pdf_path) or []
        except Exception:
            g_rows = []

        if self._coherent_legacy_count(g_rows) > self._coherent_legacy_count(rows):
            rows = g_rows

        if not rows:
            return None, expected_rows

        rows = merge_continuation_rows(rows)
        rows = drop_summary_and_section_rows(rows)

        coherent = self._coherent_legacy_count(rows)
        if coherent < 1:
            # Geometry produced rows but none are arith-coherent → NOT trustworthy
            # for a delta-less invoice; let tier3 handle it (no regression).
            return None, expected_rows

        # QR-selector (additive confidence, never writes a cell). When the QR-net
        # reconciles to the geometry Σnet we are extra-confident; either way the
        # arith-coherence floor above already qualified the read.
        import os as _os
        qr_gate_on = _os.environ.get("COLGEOM_DISABLE_QR_GATE", "") not in (
            "1", "true", "True", "yes"
        )
        if qr_gate_on:
            qr_net = self._qr_net_from_data(qr_data)
            geo_net = self._legacy_net_sum(rows)
            if (
                qr_net is not None
                and geo_net is not None
                and qr_net != 0
                and abs(geo_net - qr_net) <= max(0.05, 0.015 * abs(qr_net))
            ):
                logger.debug(
                    "SPIKE-4 QR-net reconciled geometry read (geo=%.2f qr=%.2f)",
                    geo_net, qr_net,
                )

        return rows, expected_rows

    @classmethod
    def _coherent_legacy_count(cls, rows: List[Any]) -> int:
        cnt = 0
        for r in rows or []:
            try:
                if cls._row_arith_coherent(r.to_legacy_dict()):
                    cnt += 1
            except Exception:
                continue
        return cnt

    @staticmethod
    def _legacy_net_sum(rows: List[Any]) -> Optional[float]:
        total = 0.0
        seen = False
        for r in rows or []:
            try:
                n = r.to_legacy_dict().get("net_amount")
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

    @staticmethod
    def _qr_net_from_data(qr_data: Optional[List[Dict[str, Any]]]) -> Optional[float]:
        """PT fiscal QR net = gross (O) − total VAT (N), first QR with both."""
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

    @staticmethod
    def _expected_data_row_count(pdf_path: str) -> Optional[int]:
        """Deterministic row-count anchor: count candidate DATA rows in the PDF
        text layer (a line that carries ≥2 numeric tokens AND ≥1 alphabetic
        token, i.e. 'description … amount … amount'). Coarse on purpose — it is a
        TRUNCATION DETECTOR / expected-rows hint, NOT a cell source. Returns None
        when pdfplumber is unavailable or the read fails."""
        try:
            import re as _re

            import pdfplumber

            num_re = _re.compile(r"\d+[.,]\d{2}\b")
            alpha_re = _re.compile(r"[A-Za-zÀ-ÿ]{3,}")
            count = 0
            with pdfplumber.open(pdf_path) as pdf:
                for pg in pdf.pages:
                    txt = pg.extract_text() or ""
                    for ln in txt.splitlines():
                        if len(num_re.findall(ln)) >= 2 and alpha_re.search(ln):
                            count += 1
            return count or None
        except Exception:
            logger.debug("SPIKE-4 row-count pre-pass failed", exc_info=True)
            return None

    @staticmethod
    def _quick_pick(candidates: Dict, field_names: list):
        """Pick highest-confidence value from candidates for a set of field names."""
        for name in field_names:
            cands = candidates.get(name, [])
            if cands:
                best = max(cands, key=lambda c: c.confidence)
                return best.value
        return None

    def get_available_profiles(self) -> List[str]:
        """
        Get list of available country profiles.

        Returns:
            list: Country codes of loaded profiles
        """
        return [profile.country_code for profile in self.profiles]

    def __repr__(self) -> str:
        return f"<HeuristicEngine(profiles={len(self.profiles)}, threshold={self.threshold})>"
