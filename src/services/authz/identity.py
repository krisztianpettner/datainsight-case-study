"""Canonical client-identity resolver — S158.2 derivation primitive.

# ARCH-DOC: docs/architecture/02-module-map.md#authz-identity-resolver

The single blessed resolution point for the canonical client identity.

NOMENCLATURE (S158.2 survey, `.session/S158_2_identity-nomenclature.md`):
  - Canonical identity = portal `client_users.id` (every business domain keys on it:
    billing_ledger, Stripe, referral, profiling, export, audit, NotificationInbox, NifUsage).
  - Canonical natural key = `email_norm` (normalize_email) — the UNIQUE key all three
    stores enforce; the "who" anchor.
  - `vps_clients.id` / `clients.id` are aliases DERIVABLE from email, not separate identities.

This resolver materializes NOTHING: `client_users(email UNIQUE → id)` already IS the
email→portal-id map, so a `client_identity_map` table here would be redundant (DA-K6). A
materialized map earns its place ONLY where the derivation is not reachable — the R5 bridge,
where the PC cannot read vps.db to derive the email from a `vps_clients.id`. That alias-pin
(+ table + migration + registration hooks) is deferred to R5.

Pure, sync, read-only (mirrors services.authz.scope_resolver): never writes/commits.
"""

from sqlalchemy.orm import Session

from db.models_client import ClientUser
from services.email_normalize import normalize_email


class IdentityResolver:
    """Resolve the canonical portal identity from the email natural key.

    Pure read-only: issues a single SELECT, never writes or commits.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve_client_user_id(self, email: str) -> int | None:
        """email → portal `client_users.id`, or None (fail-closed) on no-match.

        Normalizes defensively (DA-K1): callers may pass a raw or already-normalized
        email; both resolve identically since registration stores the normalized form
        and `email` is UNIQUE across all roles (uq_client_users_email). Returns the
        single matching id regardless of role (owner / member / accountant)."""
        if not email:
            return None
        email_norm = normalize_email(email)
        row = (
            self.db.query(ClientUser.id)
            .filter(ClientUser.email == email_norm)
            .first()
        )
        return row.id if row else None
