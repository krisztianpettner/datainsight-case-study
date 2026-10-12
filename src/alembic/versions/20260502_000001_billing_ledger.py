"""BLOKK 7 #1: BillingLedger append-only event log + DB-level no-update/delete trigger

Revision ID: 20260502_000001
Revises: 20260501_000001
Create Date: 2026-05-02

L2 vízió Iter 28 SoT (2026-04-28) — append-only billing event log:

  - ``billing_ledger`` tábla: minden billing-relevans pipeline esemény ide ír
    (parsing_auto_approve, hitl_approve, hitl_reject, manual_adj, refund,
    self_billing_inject_meta).
  - ``idempotency_key`` UNIQUE — composite natural-key
    ('{batch_file_id}:{event_type}:{minute_iso}' a hookokra; '{operator}:{ts}'
    a manual_adj-nál) — duplikált event-rögzítés ellen.
  - Append-only invariant DB-szinten: BEFORE UPDATE/DELETE trigger raise-el,
    kivéve ha session-var ``billing.allow_correction`` = 'true' (Ops-bypass
    audit-trail manual korrekcióhoz; preferált: új `manual_adj` row).
  - Hónap végi aggregáció (tasks/billing_aggregation.py, BLOKK 7 #4) per-client
    SUM-ot olvas és ClearAdmin invoice CSV-t generál; Stripe = csak
    fizetés-intéző (SEPA DD), MeterEvent KIVEZETÉS pipeline-ban.

Idempotent (table + trigger existence check) — re-run safe.
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260502_000001"
down_revision = "20260501_000001"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def _has_trigger(bind, trigger_name: str, table_name: str) -> bool:
    """Postgres-specific trigger existence check."""
    result = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_trigger t "
            "JOIN pg_class c ON t.tgrelid = c.oid "
            "WHERE t.tgname = :trigger_name AND c.relname = :table_name"
        ),
        {"trigger_name": trigger_name, "table_name": table_name},
    ).first()
    return result is not None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Create the billing_ledger table (idempotent)
    if not _has_table(bind, "billing_ledger"):
        op.create_table(
            "billing_ledger",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "client_user_id",
                sa.Integer(),
                sa.ForeignKey(
                    "client_users.id",
                    name="billing_ledger_client_user_id_fkey",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
            sa.Column(
                "batch_file_id",
                sa.Integer(),
                sa.ForeignKey(
                    "client_batch_files.id",
                    name="billing_ledger_batch_file_id_fkey",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
            sa.Column("event_type", sa.String(40), nullable=False),
            sa.Column("pipeline_stage", sa.String(32), nullable=True),
            sa.Column("amount_change", sa.Numeric(10, 2), nullable=False),
            sa.Column("currency", sa.String(8), nullable=False, server_default="EUR"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("idempotency_key", sa.String(128), nullable=False),
            sa.Column(
                "source_event_id",
                sa.Integer(),
                sa.ForeignKey(
                    "billing_ledger.id",
                    name="billing_ledger_source_event_id_fkey",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
            sa.Column("created_by", sa.String(64), nullable=False, server_default="system"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("details", JSONB, nullable=True),
            sa.UniqueConstraint("idempotency_key", name="uq_billing_ledger_idempotency_key"),
        )
        op.create_index(
            "ix_billing_ledger_client_user_id",
            "billing_ledger",
            ["client_user_id"],
        )
        op.create_index(
            "ix_billing_ledger_batch_file_id",
            "billing_ledger",
            ["batch_file_id"],
        )
        op.create_index(
            "ix_billing_ledger_idempotency_key",
            "billing_ledger",
            ["idempotency_key"],
        )
        op.create_index(
            "ix_billing_ledger_client_created",
            "billing_ledger",
            ["client_user_id", "created_at"],
        )
        op.create_index(
            "ix_billing_ledger_event_type",
            "billing_ledger",
            ["event_type"],
        )

    # 2) Append-only enforcement: BEFORE UPDATE / DELETE trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION billing_ledger_prevent_modification()
        RETURNS TRIGGER AS $TRG$
        BEGIN
            -- Ops-bypass: SET LOCAL "billing.allow_correction" = 'true' a session-en
            BEGIN
                IF current_setting('billing.allow_correction', true) = 'true' THEN
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    ELSE
                        RETURN NEW;
                    END IF;
                END IF;
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END;
            RAISE EXCEPTION
                'billing_ledger is append-only -- use manual_adj entry-point '
                'for corrections (op=%, id=%)',
                TG_OP, COALESCE(OLD.id, NEW.id);
        END;
        $TRG$ LANGUAGE plpgsql;
        """
    )

    if not _has_trigger(bind, "billing_ledger_no_update_trg", "billing_ledger"):
        op.execute(
            """
            CREATE TRIGGER billing_ledger_no_update_trg
                BEFORE UPDATE ON billing_ledger
                FOR EACH ROW
                EXECUTE FUNCTION billing_ledger_prevent_modification();
            """
        )

    if not _has_trigger(bind, "billing_ledger_no_delete_trg", "billing_ledger"):
        op.execute(
            """
            CREATE TRIGGER billing_ledger_no_delete_trg
                BEFORE DELETE ON billing_ledger
                FOR EACH ROW
                EXECUTE FUNCTION billing_ledger_prevent_modification();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_trigger(bind, "billing_ledger_no_update_trg", "billing_ledger"):
        op.execute("DROP TRIGGER billing_ledger_no_update_trg ON billing_ledger;")
    if _has_trigger(bind, "billing_ledger_no_delete_trg", "billing_ledger"):
        op.execute("DROP TRIGGER billing_ledger_no_delete_trg ON billing_ledger;")
    op.execute("DROP FUNCTION IF EXISTS billing_ledger_prevent_modification();")

    if _has_table(bind, "billing_ledger"):
        op.drop_table("billing_ledger")
