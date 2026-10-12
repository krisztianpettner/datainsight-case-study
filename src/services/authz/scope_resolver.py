"""Pure authorization scope resolver — F1 characterization extract (S158.1).

# ARCH-DOC: docs/architecture/02-module-map.md#authz-scope-resolver

Faithfully MIRRORS the as-is authorization behavior currently inlined across
the codebase, collapsing the three scattered orthogonal checks into ONE
enforcement point (the "sín" / guard-rail of docs/architecture/36):

  - accountant ↔ client access  ← api/deps_client.py::_check_accountant_access
  - accountant active roster     ← api/deps_client.py::get_accountant_client_ids
  - owner/member operational scope ← inline `ClientBatch.client_id == current.id`
  - granular accountant consent  ← services/feature_gate.py::has_accountant_consent
  - billing-owner resolution     ← api/deps_client.py::_resolve_billing_owner

ZERO behavior change (NO AMPUTATION). The known gaps are deliberately mirrored
as-is and fixed later in separate, named "tightening" commits (see S158 plan):
  T1 data_access runtime-enforcement (today: onboarding-only → revoke is a no-op)
  T2 grace-period / pending-link semantics
  T3 profiling consent bug (legacy `monitoring` instead of granular `profiling`)
  T4 messaging legacy fallback
  T5 member→owner visibility — ✅ FIXED (S168 QA R3-4): a member now sees the
     whole company's batches (owner + sibling members), derived strictly from the
     `owner_id` self-FK graph. See visible_owner_ids below. READ-scope only.
  T6 wiring _resolve_billing_owner to this resolver

Read-only by contract: this service NEVER writes/commits. The IDOR audit row +
403 raise remain in the api/deps_client.py shim (caller-owns-commit / N-tier).
"""

from typing import TYPE_CHECKING

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from db.models_client import AccountantClient, ClientUser, ConsentLog

if TYPE_CHECKING:
    pass

# Granular accountant-scope consent vocabulary — mirror of
# services.feature_gate.ACCOUNTANT_SCOPES (kept in sync; see consented_scopes).
_ACCOUNTANT_SCOPES = ("data_access", "profiling", "messaging")


class ScopeResolver:
    """Single enforcement point for "who-sees-whom". Pure, sync, side-effect-free.

    Construct per request with the caller-owned SQLAlchemy Session. The resolver
    issues read queries only — it NEVER calls db.add / db.commit / db.flush.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── operational-data visibility ──────────────────────────────────────────
    def visible_owner_ids(self, actor: "ClientUser") -> set[int]:
        """The K7 visibility set — the client-ids whose operational data ``actor``
        may READ.

          owner      → {owner.id} ∪ {member.id : member.owner_id == owner.id}
                       The owner sees the whole company — its own batches plus
                       every member's (doc 36 §3.2: owner+members are ONE legal
                       entity, no intra-company K7 wall).
          member     → resolve up to the owner, then the SAME company set.
                       (T5 FIX, S168 QA R3-4.) Previously a member saw only
                       `{actor.id}`, so it never saw the owner's batches — a
                       company-shared workspace that was empty for the invitee.
          accountant → set(active accountant_clients client_ids)  [NO consent
                       gate today — `data_access` consent is onboarding-only, T1]

        K7 (cross-company isolation): the company set is derived ONLY from the
        `owner_id` self-FK graph — never from `nif` (synthetic `M-...` collisions
        / a shared real NIF could otherwise pull foreign rows) and never from
        `referred_by_id` (the affiliate edge grants NOTHING). The set is therefore
        bounded to a single company by construction and cannot leak across tenants.

        READ-scope only. Do NOT reuse this set to grant a member owner-only WRITE
        surfaces (billing/settings/ownership stay `get_current_owner`-gated). Batch
        writes (commit/reset) remain individual-scoped at their call sites.
        """
        if actor.role == "accountant":
            return set(self.active_client_ids(actor.id))

        # Fail-closed guards (DA K1/K2, S168): the company-set widening applies
        # ONLY to a well-formed owner or member. Anything else collapses to the
        # most restrictive own-scope {actor.id} — never raises (this is a READ
        # path; a 500 on an edge role would be worse than minimal visibility):
        #   - an unexpected/NULL role (neither accountant/owner/member), and
        #   - an orphaned member (role='member' but owner_id IS NULL — a data
        #     anomaly the invite-flow never produces, but we will not let it
        #     silently re-root the company graph onto the member's own id).
        if actor.role not in ("owner", "member"):
            return {actor.id}
        if actor.role == "member" and not actor.owner_id:
            return {actor.id}

        # owner / member → the whole company (the owner_id self-FK subgraph).
        # NOTE on is_active: members are intentionally NOT filtered by is_active.
        # A deactivated member is the SAME legal entity, and its batches are the
        # company's data — the active owner must keep seeing them (K7 is the
        # cross-COMPANY wall = the owner_id bound, not an intra-company lifecycle
        # filter). The acting user is always is_active (get_current_client).
        owner_id = actor.owner_id if actor.role == "member" else actor.id
        member_ids = {
            row.id
            for row in self.db.query(ClientUser.id)
            .filter(ClientUser.owner_id == owner_id)
            .all()
        }
        return {owner_id} | member_ids

    def active_client_ids(self, accountant_id: int) -> list[int]:
        """Exact mirror of get_accountant_client_ids: the client_ids with an
        active AccountantClient link. Returns a ``list`` (no consent, no
        ordering guarantee), so the deps shim stays byte-identical.
        """
        rows = (
            self.db.query(AccountantClient.client_id)
            .filter(
                AccountantClient.accountant_id == accountant_id,
                AccountantClient.status == "active",
            )
            .all()
        )
        return [r.client_id for r in rows]

    # ── accountant ↔ client access predicate (read-only, no side effects) ────
    def accountant_can_access(self, accountant_id: int, client_id: int) -> bool:
        """True iff an *active* AccountantClient(accountant_id, client_id) link
        exists. Pure predicate mirroring the GATE of _check_accountant_access —
        it does NOT log, write, commit, or raise. The deps shim owns the 403 +
        ``idor_attempt_blocked`` audit on a False result.
        """
        link = (
            self.db.query(AccountantClient)
            .filter(
                AccountantClient.accountant_id == accountant_id,
                AccountantClient.client_id == client_id,
                AccountantClient.status == "active",
            )
            .first()
        )
        return link is not None

    # ── granular accountant-scope consent (latest-wins) ──────────────────────
    def consented_scopes(self, client_id: int, accountant_id: int) -> set[str]:
        """Subset of {data_access, profiling, messaging} whose latest ConsentLog
        row for (client_id, accountant_id, scope) is action='granted'.

        Mirrors services.feature_gate.has_accountant_consent applied per scope.

        # TODO F2-tightening — NOT wired into any caller in F1. Do not swap an
        # existing has_accountant_consent call onto this method without checking
        # semantics (it is provided for interface completeness only).
        """
        granted: set[str] = set()
        for scope in _ACCOUNTANT_SCOPES:
            latest = (
                self.db.query(ConsentLog)
                .filter(
                    and_(
                        ConsentLog.client_id == client_id,
                        ConsentLog.accountant_user_id == accountant_id,
                        ConsentLog.consent_type == scope,
                    )
                )
                .order_by(desc(ConsentLog.created_at))
                .first()
            )
            if latest is not None and latest.action == "granted":
                granted.add(scope)
        return granted

    # ── billing owner (mirror only; NOT shim'd in F1) ────────────────────────
    def resolve_billing_owner(self, actor: "ClientUser") -> "ClientUser":
        """Mirror of api/deps_client._resolve_billing_owner: member → owner row
        (or self if the owner row is missing), else self.

        # TODO F2-tightening — NOT wired in F1; api/deps_client._resolve_billing_owner
        # stays the live implementation. Provided for interface completeness.
        """
        from db.models_client import ClientUser

        if actor.role == "member" and actor.owner_id:
            owner = (
                self.db.query(ClientUser)
                .filter(ClientUser.id == actor.owner_id)
                .first()
            )
            return owner or actor
        return actor
