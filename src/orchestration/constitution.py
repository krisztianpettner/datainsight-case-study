"""
Constitution Module - Constraint-First Orchestrator

The "Judge" over candidates. Selects best values per field and validates
against business constraints (Piros Lámpa system).

Architecture:
    HeuristicEngine.process_v2() → candidates
    Constitution.evaluate(candidates) → ConstitutionDecision
    DLQ Router(decision) → /output/ready or /output/review

Created: 2026.02.02 (Session 57 - M2.1)
"""

import logging
from typing import Any, Dict, List, Optional

from parsing.models.candidates import FieldCandidate
from parsing.models.constitution import ConstitutionDecision, ConstraintResult, DecisionStatus

# S182 Fázis 1 — adat-azonossági identity (a vak conf% PRODUCER-cseréje, tiszta csere).
# A régi ConfidenceScorer (ocr×format_boost) KUKA; a doc-conf mostantól a per-mező
# verifikáció-először identity AGGREGÁTUMA. Design: .session/S182_phase1_plan_parsing_identity.md
try:
    from parsing.identity.field_identity import aggregate as _identity_aggregate
    from parsing.identity.field_identity import compute_all as _identity_compute_all
except ImportError:  # pragma: no cover
    _identity_compute_all = None
    _identity_aggregate = None

# H1 (8b-K3): az auto-approve-kapu Fázis 1–3-ban EXPLICIT KIKAPCSOLVA (a Fázis 3 kalibrációig).
# Ez a nem-megkerülhető OFF-pont; a config `auto_approve_threshold`-hoz NEM nyúlunk.
S182_AUTO_APPROVE_DISABLED = True

# Confidence Scoring (G3 integration — Session 113) — S182: KUKA, csak import-kompat marad
try:
    from pdf_parser.confidence_scorer import ConfidenceScorer

    _scorer = ConfidenceScorer()
except ImportError:
    _scorer = None

# Confidence Router (K5 — Session 114)
try:
    from pdf_parser.confidence_router import ConfidenceRouter

    _confidence_router = ConfidenceRouter()
except ImportError:
    _confidence_router = None

# Field name → confidence type mapping
_FIELD_TYPE_MAP = {
    "tax_id": "NIF",
    "seller_nif": "NIF",
    "buyer_nif": "NIF",
    "nif": "NIF",
    "iban": "IBAN",
    "date": "DATE",
    "issue_date": "DATE",
    "due_date": "DATE",
    "invoice_number": "STRING",
    "amount": "CURRENCY",
    "amount_net": "CURRENCY",
    "amount_tax": "CURRENCY",
    "total_net": "CURRENCY",
    "total_gross": "CURRENCY",
    "total_tax": "CURRENCY",
    "email": "EMAIL",
    "atcud": "ATCUD",
}

logger = logging.getLogger(__name__)


class Constitution:
    """
    Constraint-First Orchestrator - "Bíró" a candidates felett.

    Workflow:
    1. Select best value per field (priority: QR > regex > OCR > LLM)
    2. Run constraints (Piros Lámpa system)
    3. Make decision (AUTO_APPROVE / HITL_FIELD / HITL_FULL)

    Example:
        constitution = Constitution()
        decision = constitution.evaluate(candidates)

        if decision.status == DecisionStatus.AUTO_APPROVE:
            # Process invoice automatically
            ...
        elif decision.status == DecisionStatus.HITL_FIELD:
            # Send specific fields for human review
            for field in decision.fields_to_review:
                ...
    """

    def __init__(self):
        """Initialize Constitution with priority order and constraints."""
        # Source priority (highest first)
        self.priority_order = ["qr", "tier2_regex", "ocr", "llm"]

        # Load constraints (M2.2)
        self.constraints = self._load_constraints()

        # Load strictness level from settings
        from parsing.settings import settings

        self.strictness = settings.constitution.strictness
        self._penalties = settings.confidence.violation_penalties
        self._router = _confidence_router  # ConfidenceRouter instance (K5)

        logger.info(
            f"Constitution initialized with {len(self.constraints)} constraints, strictness={self.strictness}"
        )

    def _load_constraints(self) -> List[Any]:
        """
        Load all 5 Piros Lámpa constraints.

        Returns:
            List[Constraint]: All constraint instances
        """
        from orchestration.constraints.atcud_match import ATCUDMatchConstraint
        from orchestration.constraints.customer_country import CustomerCountryConstraint
        from orchestration.constraints.date_validator import DateRangeConstraint
        from orchestration.constraints.financial_triangle import FinancialTriangleConstraint
        from orchestration.constraints.line_item_horizontal import LineItemHorizontalCheckConstraint
        from orchestration.constraints.line_item_math import LineItemMathConstraint
        from orchestration.constraints.line_item_tax_rate import LineItemTaxRateValidityConstraint
        from orchestration.constraints.line_item_vertical import LineItemVerticalCheckConstraint
        from orchestration.constraints.line_items_presence import LineItemsPresenceConstraint
        from orchestration.constraints.nif_active import NIFActiveConstraint
        from orchestration.constraints.nif_direction_ambiguity import (
            NifDirectionAmbiguityConstraint,
        )
        from orchestration.constraints.nif_validator import NIFChecksumConstraint
        from orchestration.constraints.page_limit import PageLimitConstraint
        from orchestration.constraints.qr_consistency import QRCodeConsistencyConstraint
        from orchestration.constraints.supplier_nif_sentinel import (
            SupplierNifSentinelConstraint,
        )
        from orchestration.constraints.vendor_cert import VendorCertConsistencyConstraint

        return [
            FinancialTriangleConstraint(tolerance=0.05),
            NIFChecksumConstraint(),
            DateRangeConstraint(),
            # DuplicateDetectorConstraint() KIVEZETVE az aktív listából (S188 F5) — superseded
            # by the PC dedup-kapu (services/duplicate_gate_service.py) + window-sweep + upload
            # hard-skip (S188 itinerary §0). A batch-scoped in-memory heurisztika severity="low"
            # volt, 0 hatással a decision-státuszra (ld. _make_decision Step 2/4 lent — a status
            # csak critical/high violation-t néz). A fájl + osztály MARAD (NO AMPUTATION,
            # tests/test_constraints.py közvetlenül teszteli) — csak deaktiválva; lásd
            # orchestration/constraints/duplicate_detector.py fejléc-kommentje.
            ATCUDMatchConstraint(),
            QRCodeConsistencyConstraint(),
            PageLimitConstraint(max_pages=50),
            NIFActiveConstraint(),
            # Session 70: Line Item constraints
            LineItemVerticalCheckConstraint(),
            LineItemHorizontalCheckConstraint(),
            LineItemTaxRateValidityConstraint(),
            # S146.7 F1.5.8: G8 acceptance (net+vat=gross, vat=net*rate/100)
            LineItemMathConstraint(),
            # S146.8 F8: empty line_items must not silently AUTO_APPROVE
            LineItemsPresenceConstraint(),
            # Session 80: Vendor cert tracking
            VendorCertConsistencyConstraint(),
            # S190: a vevő (adquirente) MINDIG portugál — konstans-elvárás, nem kereszt-ellenőrzés.
            # Riaszt, ha NEM PT, VAGY ha nem derül ki (fail-closed). CSAK a vevő: az eladó lehet
            # külföldi (a portugál ügyfél vásárolhat EU-ból). `medium` + field=None → a doc-státusz
            # nem mozdul; a piros sáv a K6-térképen át jön (field_identity._CONSTRAINT_FIELD_MAP).
            CustomerCountryConstraint(),
            # S213 (L2): a Consumidor Final sentinel (999999990) SOHA nem lehet szállító-NIF —
            # vevő-oldali kód, kiállító entitás nem lehet végső fogyasztó. `medium` (nem REJECTED,
            # mert hibás OLVASAT, nem hibás dokumentum) + field KITÖLTVE → HITL_FIELD a hibás
            # mezőre. ⚠️ A CustomerCountry-val ELLENTÉTBEN kritikus mezőt vétóz → doc-conf 0.0;
            # a szándékos eltérés indoklása a constraint fejléc-kommentjében.
            SupplierNifSentinelConstraint(),
            # S215 (C①): a szállító- és a vevő-NIF nem lehet AZONOS — determinisztikus
            # ellentmondás, ami az irány ISMERETE NÉLKÜL felismerhető. Mérve: a no-QR halmaz
            # 27/41 dokumentumán ugyanaz az érték ül mindkét slotban. `medium` + **field=None**
            # → a `fields_to_review` üres marad, tehát HITL_FULL (nem FIELD): az ambiguitás
            # definíció szerint nem tudja, MELYIK a hibás, és a 27-ből 17-ben épp a szállító a
            # helyes — egyetlen dobozra mutatni kétharmadában félrevinné az operátort.
            # A piros sáv + a doc-conf hatás a K6-térképen át jön (field_identity).
            NifDirectionAmbiguityConstraint(),
        ]

    def evaluate(
        self, candidates: Dict[str, List[FieldCandidate]], ocr_confidence: float = 0.0
    ) -> ConstitutionDecision:
        """
        Evaluate candidates and make decision.

        Args:
            candidates: Dict[field_name, List[FieldCandidate]]
                Example:
                {
                    "tax_id": [
                        FieldCandidate(value="599999993", source="qr", confidence=1.0),
                        FieldCandidate(value="599999993", source="tier2_regex", confidence=0.9)
                    ],
                    "date": [...]
                }

        Returns:
            ConstitutionDecision: Decision with status, selected values, constraints

        Workflow:
            1. Select best value per field (_select_best_values)
            2. Run constraints (_validate_constraints) - M2.2
            3. Make decision (_make_decision) - M2.3
        """
        logger.info(f"Constitution evaluating {len(candidates)} fields...")

        # S191: a fiskális QR-ok doc-szintű leltára (multi-fatura PDF jelzés a deszknek) —
        # a mező-loopok elől ki (belső "_" kulcs), a decision.meta-ba be.
        fiscal_docs = candidates.pop("_fiscal_docs", None)

        # Step 1: Select best value per field
        selected_values = self._select_best_values(candidates)
        logger.debug(f"Selected values: {list(selected_values.keys())}")

        # Step 2: Run constraints (M2.2)
        constraint_results = self._validate_constraints(selected_values, candidates)
        logger.debug(f"Constraint results: {len(constraint_results)} checks")

        # Step 2b (S182 I1): per-mező adat-azonossági identity a TELJES per-forrás
        # candidate-listából (QR↔vizuális reconcile + K6-mappelt constraint-jelek). Ez
        # váltja ki a vak conf%-ot a _make_decision-ben. A candidates itt még tartalmazza
        # az összes forrást slotonként (a _select_best_values csak a _multi_fields meta-kulcsot
        # popolta, a candidate-listákat nem mutálta).
        field_identities = (
            _identity_compute_all(candidates, constraint_results)
            if _identity_compute_all is not None
            else []
        )
        # Védelmi jelzés (DA-K1): a compute_all mindig visszaadja a katalógust, de ha EGY kritikus
        # mezőnek sincs forrása (a candidate-slot-nevek nem illenek a katalógus-aliasra → katalógus-
        # mismatch / törölt slot-név), a doc-conf csendben fail-closed-low lesz → minden HITL-be.
        # Ez szándékos (fail-closed), de NE némán — egy katalógus-regresszió így rejtve maradna.
        if _identity_compute_all is not None and candidates and field_identities:
            if not any(fi.sources for fi in field_identities if getattr(fi, "critical", False)):
                logger.warning(
                    "S182: EGY kritikus mezőnek sincs candidate-forrása (%d slot a bemenetben) → "
                    "doc-conf fail-closed (katalógus-slot-mismatch?)", len(candidates)
                )

        # Step 3: If no OCR confidence provided, derive from candidates (K5 fix)
        if ocr_confidence <= 0.0 and candidates:
            all_confs = [
                c.confidence
                for clist in candidates.values()
                for c in clist
                if hasattr(c, "confidence")
            ]
            ocr_confidence = max(all_confs) if all_confs else 0.5

        # Step 4: Make decision (M2.3) — S182: doc-conf = aggregate(field_identities)
        decision = self._make_decision(
            selected_values,
            constraint_results,
            ocr_confidence=ocr_confidence,
            field_identities=field_identities,
        )
        logger.info(f"Constitution decision: {decision.status.value}")

        # S182 SÁV-2 (doc 46): a HITL-munkapad-út (DLQ-artefakt → decision.meta → desk_service)
        # per-mező bbox-ot vár a `meta.field_metadata`-ban (a desk innen olvas, NEM a UnifiedInvoiceData-
        # ból). Additív, non-PII koordináta; a doc-conf/status/selected_values ÉRINTETLEN.
        decision.meta["field_metadata"] = self._build_field_metadata(
            candidates, field_identities, selected_values=selected_values
        )
        # S191: multi-fatura PDF (EDP-minta: 2 al-számla egy fájlban) — a deszk-banner forrása.
        # ITT (az evaluate-ben, a field_metadata mintájára), mert a _make_decision-nek több
        # korai return-útja van — a meta-dict-be írás ott NameError-t adott a reject-úton.
        if fiscal_docs:
            decision.meta["fiscal_docs"] = fiscal_docs

        return decision

    def _build_field_metadata(
        self,
        candidates: Dict[str, List[FieldCandidate]],
        field_identities: Optional[List[Any]] = None,
        selected_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """S182 SÁV-2: per-slot {confidence, source, bbox, page_no, bbox_source} a desk-útra
        (decision.meta.field_metadata). A bbox a bbox-os candidate-ből (match-site, tier2), NEM a
        magasabb-conf bbox-mentes QR-ből; a conf a SÁV-1 estimate-tel felülírva (mint output.py I5).
        Csak a meglévő candidate-meta-ból olvas — érték-független, regressziómentes."""
        fm: Dict[str, Dict[str, Any]] = {}
        for fn, clist in candidates.items():
            if fn.startswith("_") or not clist:
                continue
            best = max(clist, key=lambda c: getattr(c, "confidence", 0.0))
            fm[fn] = {"confidence": getattr(best, "confidence", 0.0), "source": getattr(best, "source", "unknown")}
            bcand = next((c for c in clist if (getattr(c, "meta", None) or {}).get("bbox") is not None), None)
            if bcand is not None:
                m = bcand.meta
                fm[fn]["bbox"] = m.get("bbox")
                fm[fn]["page_no"] = m.get("page_no")
                fm[fn]["bbox_source"] = m.get("bbox_source", "tier2_match")
                if m.get("matched_text") is not None:
                    fm[fn]["matched_text"] = m.get("matched_text")
            else:
                # S190: box-less — de MIÉRT? A deszken ez a különbség a 'nincs mit keresni' és a
                # 'több hasonló van, nézd meg' között. 'ambiguous' BÁRMELY kandidátuson felülír.
                # S192 §1.4 (absence-follows-selected): az absence a KIJELZETT érték kandidátusairól
                # jöjjön — multi-fatura slotokon (EDP: total_vat=x,xx mellett a 2. al-számla y,yy-je)
                # a MÁSIK érték 'ambiguous'-a hamis pánik-üzenet volt. A más-értékű kandidátus
                # absence-e az Ő értékéről állít, nem a kijelzettről → skálár selected mellett
                # SZIGORÚ szűrés (nincs fallback); None/lista selected → a mai teljes-scan.
                _sel = (selected_values or {}).get(fn)
                _scope = clist
                if _sel is not None and not isinstance(_sel, list):
                    _scope = [c for c in clist if c.value == _sel] or []
                _abs = None
                for c in _scope:
                    a = (getattr(c, "meta", None) or {}).get("bbox_absence")
                    if a == "ambiguous":
                        _abs = a
                        break
                    if a and _abs is None:
                        _abs = a
                if _abs:
                    fm[fn]["bbox_absence"] = _abs
                # S191: a jelölt-példányok (ugrálható dobozok) — a kijelzett érték hordozójából;
                # ha nincs, a teljes listából (a desk `_candidates_for` úgyis érték-szűr, S191).
                _bc = next(((getattr(c, "meta", None) or {}).get("bbox_candidates")
                            for c in _scope
                            if (getattr(c, "meta", None) or {}).get("bbox_candidates")), None)
                if _bc is None:
                    _bc = next(((getattr(c, "meta", None) or {}).get("bbox_candidates")
                                for c in clist
                                if (getattr(c, "meta", None) or {}).get("bbox_candidates")), None)
                if _bc:
                    fm[fn]["bbox_candidates"] = _bc
        for fi in field_identities or []:  # SÁV-1 estimate overlay (mint output.py I5)
            for slot in (getattr(fi, "slots", None) or []):
                if slot in fm:
                    fm[slot]["confidence"] = fi.estimate
        return fm

    def _select_best_values(self, candidates: Dict[str, List[FieldCandidate]]) -> Dict[str, Any]:
        """
        Select best value per field based on source priority.

        Priority order: QR > tier2_regex > OCR > LLM

        Multi fields (tagged via _multi_fields): return sorted list of ALL
        unique values instead of a single best pick.

        Args:
            candidates: Dict[field_name, List[FieldCandidate]]

        Returns:
            Dict[field_name, value]: Best value per field (scalar or list)
        """
        selected = {}

        # Pop internal metadata keys before iteration
        multi_fields = set(candidates.pop("_multi_fields", []))

        for field_name, field_candidates in candidates.items():
            # Skip internal metadata keys (start with _)
            if field_name.startswith("_"):
                continue

            if not field_candidates:
                selected[field_name] = None
                continue

            # Sort by: 1) Source priority, 2) Confidence (descending)
            def sort_key(cand: FieldCandidate):
                try:
                    source_priority = self.priority_order.index(cand.source)
                except ValueError:
                    source_priority = 999
                return (source_priority, -cand.confidence)

            sorted_candidates = sorted(field_candidates, key=sort_key)

            if field_name in multi_fields:
                # Multi mode: return all unique values, priority-ordered
                seen = set()
                vals = []
                for c in sorted_candidates:
                    if c.value not in seen:
                        seen.add(c.value)
                        vals.append(c.value)
                selected[field_name] = vals
                logger.debug(f"Field '{field_name}' (multi): {len(vals)} unique values")
            else:
                best_candidate = sorted_candidates[0]
                # S192 §1.1: no-QR gross first-pick trust-rés — a `szám+€` minta 10+ találatából
                # a dokumentum-sorrendi első nyert (néma rossz prefill). HA nincs QR-jelölt az
                # amount-listában, a háromszög-konzisztens jelölt nyer (net+tax ≈ gross, a
                # financial_triangle 0.05 toleranciájával); nincs ilyen → marad a mai first-pick.
                # QR-dokon a gating miatt SOSEM fut (a QR-jelölt priority-győztes) → 0 golden-mozgás.
                if (
                    field_name == "amount"
                    and not any(getattr(c, "source", None) == "qr" for c in field_candidates)
                ):
                    tri = self._triangle_consistent_pick(sorted_candidates, candidates)
                    if tri is not None:
                        best_candidate = tri
                selected[field_name] = best_candidate.value
                logger.debug(
                    f"Field '{field_name}': selected {best_candidate.value} "
                    f"from {best_candidate.source} (conf={best_candidate.confidence})"
                )

        return selected

    def _triangle_consistent_pick(
        self,
        sorted_candidates: List[FieldCandidate],
        candidates: Dict[str, List[FieldCandidate]],
    ) -> Optional[FieldCandidate]:
        """S192 §1.1: a gross-jelöltek közül az nyer, amelyre net + tax = gross teljesül.

        A net/tax referencia a saját slot-lista priority-best értéke (ugyanaz a sort_key,
        mint a fő kiválasztásé). Bármelyik hiányzik vagy nem szám → None (fallback a mai
        first-pick — a háromszög CSAK dönteni segít, értéket nem talál ki)."""
        def _best_num(slot: str) -> Optional[float]:
            clist = candidates.get(slot) or []
            best_v, best_k = None, None
            for c in clist:
                try:
                    v = float(c.value)
                except (TypeError, ValueError):
                    continue
                try:
                    prio = self.priority_order.index(c.source)
                except ValueError:
                    prio = 999
                k = (prio, -c.confidence)
                if best_k is None or k < best_k:
                    best_v, best_k = v, k
            return best_v

        net = _best_num("amount_net")
        tax = _best_num("amount_tax")
        if net is None or tax is None:
            return None
        target = net + tax
        for c in sorted_candidates:
            try:
                cv = float(c.value)
            except (TypeError, ValueError):
                continue
            if abs(cv - target) <= 0.05:  # a financial_triangle toleranciája (reconcile, NEM doboz)
                return c
        return None

    def _validate_constraints(
        self, selected_values: Dict[str, Any], candidates: Dict[str, List[FieldCandidate]] = None
    ) -> List[ConstraintResult]:
        """
        Run all constraints on selected values.

        M2.2 IMPLEMENTATION: Run all 5 Piros Lámpa constraints.

        Args:
            selected_values: Dict[field_name, value]

        Returns:
            List[ConstraintResult]: Results from all constraint checks
        """
        results = []

        for constraint in self.constraints:
            try:
                try:
                    result = constraint.validate(selected_values, candidates=candidates)
                except TypeError:
                    # Legacy constraint: signature doesn't include candidates
                    result = constraint.validate(selected_values)

                # Apply strictness downgrade if needed
                if not result.passed and self.strictness == 1:
                    # Draft mode: downgrade MISSING to skipped
                    details = result.details or {}
                    is_missing = details.get("reason") == "missing_values"
                    is_atcud = constraint.name == "ATCUD Match"

                    if is_missing or is_atcud:
                        # Override: treat as passed with warning
                        result = ConstraintResult(
                            constraint_name=result.constraint_name,
                            passed=True,
                            severity="info",
                            message=f"[Draft Mode] {result.message} (skipped - strictness=1)",
                            field=result.field,
                            details={**(result.details or {}), "skipped_by_strictness": True},
                        )

                results.append(result)

                # Log result
                status = "PASS" if result.passed else "FAIL"
                logger.info(f"Constraint '{constraint.name}': {status}")
                if not result.passed:
                    logger.warning(f"  -> {result.message}")

            except Exception as e:
                # If a constraint crashes, log and create failed result
                logger.error(f"Constraint '{constraint.name}' crashed: {e}", exc_info=True)
                results.append(
                    ConstraintResult(
                        constraint_name=constraint.name,
                        passed=False,
                        severity="critical",
                        message=f"Constraint crashed: {str(e)}",
                        field=None,
                        details={"error": str(e), "crashed": True},
                    )
                )

        return results

    def _make_decision(
        self,
        selected_values: Dict[str, Any],
        constraint_results: List[ConstraintResult],
        ocr_confidence: float = 0.0,
        field_identities: Optional[List[Any]] = None,
    ) -> ConstitutionDecision:
        """
        Make final decision based on constraint results + confidence scoring.

        G3 Integration (Session 113): Uses ConfidenceScorer for real OCR-based
        confidence instead of fixed values. Constraint violations still override
        routing (critical → REJECTED regardless of confidence).

        Args:
            selected_values: Dict[field_name, value]
            constraint_results: List[ConstraintResult]
            ocr_confidence: OCR word-level confidence (0.0-1.0)

        Returns:
            ConstitutionDecision: Final decision with status, confidence, fields_to_review
        """
        # Step 1 (S182 I2/I3): a doc-conf az adat-azonossági identity AGGREGÁTUMA
        # (min a kritikus (a)/(b) mezőkön). A régi ocr×format_boost ConfidenceScorer KUKA
        # (tiszta csere, nincs dual-SoT). A field_confidences a per-slot identity-estimate
        # (a meglévő fogyasztók kényelmére; a SoT a field_identities lista).
        field_identities = field_identities or []
        field_confidences = {}
        for fi in field_identities:
            for slot in (getattr(fi, "slots", None) or []):
                field_confidences[slot] = fi.estimate
        if _identity_aggregate is not None and field_identities:
            base_confidence = _identity_aggregate(field_identities)
        else:
            # fail-closed: identity nélkül nincs BIZONYÍTOTT azonosság → HITL-sávba (nem 0.5-vakon)
            base_confidence = 0.0

        # Step 2: Categorize violations by severity
        violations = [r for r in constraint_results if not r.passed]
        critical_violations = [v for v in violations if v.severity == "critical"]
        high_violations = [v for v in violations if v.severity == "high"]
        medium_violations = [v for v in violations if v.severity == "medium"]
        low_violations = [v for v in violations if v.severity == "low"]

        total_violations = len(violations)
        severe_violations = len(critical_violations) + len(high_violations)

        # Step 3 (S182 K2): NINCS dupla-büntetés. A doc-conf MÁR az identity-aggregátum, ami
        # a QR↔vizuális reconcile-t ÉS a K6-mappelt constraintek hard_veto-ját tartalmazza
        # (NIFChecksum/FinancialTriangle/QRConsistency/ATCUD → bármely kritikus mező hard_veto
        # esetén az aggregate már 0.0). A régi violation-szorzót NEM alkalmazzuk újra. A critical
        # constraint a STATUS-t hajtja (lent → REJECTED), nem szoroz másodszor a confidence-en.
        confidence = base_confidence
        if critical_violations:
            confidence = 0.0

        # Step 4: Determine status — critical override, H1-guard, majd ConfidenceRouter (K5)
        fields_to_review = list(set([v.field for v in violations if v.field]))

        if critical_violations:
            status = DecisionStatus.REJECTED
            reason = f"REJECTED: {len(critical_violations)} critical violation(s) - " + ", ".join(
                [v.constraint_name for v in critical_violations]
            )
        elif S182_AUTO_APPROVE_DISABLED:
            # H1 (8b-K3): a Fázis 3 kalibrációig SOHA nem keletkezhet AUTO_APPROVE. A blast-radius
            # a kijelzés + a manuális-HITL-routing; a kapu-ENGEDÉLYEZÉS = Fázis 4 (kalibráció után).
            status = (
                DecisionStatus.HITL_FIELD if fields_to_review else DecisionStatus.HITL_FULL
            )
            reason = f"S182-F1: auto-approve OFF (kalibrációig); identity-conf={confidence:.2f}"
        elif self._router is not None:
            routing = self._router.route_invoice(confidence)
            status = DecisionStatus(routing.route)
            reason = routing.reason
            # S153 (precision-first): REJECTED is reserved for a critical constraint
            # breach (see DecisionStatus.REJECTED). ConfidenceRouter.route_invoice,
            # however, emits REJECTED on confidence alone (<0.70) — with no critical/high
            # violation this is an over-rejection. A human should review (HITL), never a
            # hard reject. Measure: S153 no-QR image census, 8/9 rejects were medium-only
            # (Date Range + Financial Triangle) → HITL, with 0 shift toward auto_approve.
            # Written before the Step-5 ConstitutionDecision build so JSON/DLQ/Excel all
            # observe the corrected status. High violations are deliberately left rejectable.
            if (
                status == DecisionStatus.REJECTED
                and not critical_violations
                and not high_violations
            ):
                status = (
                    DecisionStatus.HITL_FIELD if fields_to_review else DecisionStatus.HITL_FULL
                )
                reason = f"HITL (S153 floor): {reason}; no critical/high violation"
            if status == DecisionStatus.AUTO_APPROVE:
                fields_to_review = []
            elif status == DecisionStatus.HITL_FULL and fields_to_review:
                status = DecisionStatus.HITL_FIELD
        else:
            # Fallback if ConfidenceRouter unavailable
            from parsing.settings import settings

            auto_t = settings.confidence.auto_approve_threshold
            hitl_t = settings.confidence.hitl_threshold
            if confidence >= auto_t:
                status = DecisionStatus.AUTO_APPROVE
                reason = f"AUTO_APPROVE: confidence {confidence:.2f}"
                fields_to_review = []
            elif confidence >= hitl_t:
                status = DecisionStatus.HITL_FIELD if fields_to_review else DecisionStatus.HITL_FULL
                reason = f"HITL: confidence {confidence:.2f}, {total_violations} violation(s)"
            else:
                status = DecisionStatus.HITL_FULL
                reason = f"HITL_FULL: confidence {confidence:.2f} below threshold"

        # Step 5: Build decision
        return ConstitutionDecision(
            status=status,
            selected_values=selected_values,
            constraint_results=constraint_results,
            confidence=confidence,
            reason=reason,
            fields_to_review=fields_to_review,
            meta={
                "total_violations": total_violations,
                "critical_violations": len(critical_violations),
                "high_violations": len(high_violations),
                "medium_violations": len(medium_violations),
                "low_violations": len(low_violations),
                # S182: a verifikálható kritikus mezők közül hány hard_veto / piros
                "s182_field_count": len(field_identities),
                "s182_hard_veto_fields": [
                    getattr(fi, "field", None) for fi in field_identities
                    if getattr(fi, "hard_veto", False)
                ],
            },
            field_identities=field_identities,
        )

    def __repr__(self) -> str:
        return f"<Constitution(constraints={len(self.constraints)})>"
