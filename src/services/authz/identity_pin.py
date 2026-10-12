"""R0b (S162) — the vps_client_id → client_user_id alias-pin service (the bridge).

# ARCH-DOC: docs/architecture/02-module-map.md#authz-identity-resolver

The PC dispatch boundary (`dispatch_watcher.py`) carries only `vps_clients.id`
(an integer from the NAS path). The canonical portal identity (`client_users.id`,
the FK target of billing_ledger + profiling stats) is NOT derivable PC-side
because `vps_clients.email` lives in the VPS DB the PC cannot read. This service
materializes that hop into `client_identity_map` (db.models_client) so R6b
(profiling) and BR1 (pilot-billing) can attach work to the right portal client.

DESIGN (DA S162):
  - The pin is on the IMMUTABLE `client_user_id` (K1/K6): a portal email change
    does not break it. `email_norm` is a denormalized audit column, never the
    resolution key. The email→id derivation runs ONCE here at registration, not
    at resolution.
  - Soft-deleted targets are rejected at registration (K3, GDPR/K7): an email
    reused after erasure cannot pin a vps_client to a wound-down account.
  - Idempotent upsert on the vps_client_id PK (K7).
  - Caller-owns-transaction (K4, N-tier): this service flushes, never commits.
  - Resolution is fail-closed → None on no-pin; the consumer decides (K5).

Pure DB-access lives here (services), never in routes. Pilot populates the single
Pedro row via `register_pin`; the general 4-entry-point provision sync is a later
slice. SoT: docs/architecture/35 FÁZIS R5 + services/authz/identity.py.
"""

import logging

from sqlalchemy.orm import Session

from db.models_client import ClientIdentityMap, ClientUser
from services.authz.identity import IdentityResolver
from services.email_normalize import normalize_email

logger = logging.getLogger(__name__)


class IdentityPinService:
    """Resolve and register the PC-local vps_client_id → client_user_id pin."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve_client_user_id_from_vps(self, vps_client_id: int) -> int | None:
        """vps_clients.id → portal client_users.id, or None (fail-closed) on no-pin.

        Pure read-only: a single SELECT on the immutable integer pin. Returns None
        when no pin exists (e.g. a vps_client not yet provisioned into the map) —
        the caller (R6b/BR1 wiring) decides whether to skip, queue, or fail (K5).
        Does NOT re-validate the target's lifecycle: the pin is authoritative once
        registered (soft-delete is enforced at registration, K3)."""
        if vps_client_id is None:
            return None
        row = (
            self.db.query(ClientIdentityMap.client_user_id)
            .filter(ClientIdentityMap.vps_client_id == vps_client_id)
            .first()
        )
        return row.client_user_id if row else None

    def register_pin(
        self,
        *,
        vps_client_id: int,
        email_norm: str | None = None,
        client_user_id: int | None = None,
    ) -> ClientIdentityMap:
        """Establish (or update) the pin for a vps_client_id. Fail-closed.

        Exactly one identity source is required:
          - `email_norm` given, `client_user_id` None → derive the id via the single
            blessed IdentityResolver (the normal path).
          - `client_user_id` given → explicit ops override (the K6 email-mismatch
            escape hatch); `email_norm` is then stored as audit only.

        Validation (all fail-closed → ValueError):
          - vps_client_id must be a positive int.
          - the resolved/given client_user must EXIST and be NOT soft-deleted
            (deletion_requested_at IS NULL) — K3 / GDPR Art.17.
        On an email/identity mismatch (audit email_norm ≠ the target's normalized
        email) a warning is logged but the pin is still written (K6: the integer
        pin is authoritative; the audit column merely records provenance).

        Idempotent: upserts on the vps_client_id PK (K7). Caller owns the
        transaction — this method flushes but never commits (K4)."""
        if not isinstance(vps_client_id, int) or vps_client_id <= 0:
            raise ValueError(f"invalid vps_client_id: {vps_client_id!r}")

        audit_email = normalize_email(email_norm) if email_norm else None

        # Resolve the pin target.
        if client_user_id is None:
            if not audit_email:
                raise ValueError("register_pin requires email_norm or client_user_id")
            client_user_id = IdentityResolver(self.db).resolve_client_user_id(audit_email)
            if client_user_id is None:
                raise ValueError(f"no client_user matches email {audit_email!r} (fail-closed)")

        # Validate the target exists and is not soft-deleted (K3).
        target = (
            self.db.query(ClientUser)
            .filter(ClientUser.id == client_user_id)
            .first()
        )
        if target is None:
            raise ValueError(f"client_user_id {client_user_id} does not exist (fail-closed)")
        if target.deletion_requested_at is not None:
            raise ValueError(
                f"client_user_id {client_user_id} is soft-deleted — refusing to pin (K3)"
            )

        # Audit-email mismatch is a warning, not a failure (K6).
        if audit_email and normalize_email(target.email) != audit_email:
            logger.warning(
                "identity-pin email mismatch: vps_client_id=%s pinned to client_user_id=%s "
                "but audit email %r != target email %r",
                vps_client_id,
                client_user_id,
                audit_email,
                normalize_email(target.email),
            )

        # Idempotent upsert on the PK (K7).
        pin = (
            self.db.query(ClientIdentityMap)
            .filter(ClientIdentityMap.vps_client_id == vps_client_id)
            .first()
        )
        if pin is None:
            pin = ClientIdentityMap(
                vps_client_id=vps_client_id,
                client_user_id=client_user_id,
                email_norm=audit_email,
            )
            self.db.add(pin)
        else:
            pin.client_user_id = client_user_id
            pin.email_norm = audit_email
        self.db.flush()
        return pin


def provision_self_pin(db: Session, client_user_id: int) -> None:
    """R0b (S178 INFRA-1): register the portal-native self-pin for a freshly
    created ClientUser so the PC→portal decision projection can resolve it.

    The portal upload path stamps the NAS object with the client's NATIVE
    ClientUser.id (see client_batches.py D2→D3 contract), so the PC decision's
    vps_client_id == this client_user_id — a self-map. Without the pin,
    upsert_projection fail-closed SKIPS every decision and the client never
    sees its processing status (the INFRA-1 root cause).

    Idempotent (upsert on the vps_client_id PK); flushes, never commits — the
    caller owns the transaction. Call AFTER db.flush() (id assigned), BEFORE
    db.commit().
    """
    IdentityPinService(db).register_pin(
        vps_client_id=client_user_id,
        client_user_id=client_user_id,
    )
