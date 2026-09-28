"""Add user accounts and balanced journal.

Revision ID: 20260929_0002
Revises: 20260929_0001
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260929_0002"
down_revision = "20260929_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("currency = 'PKR'", name="ck_accounts_currency_pkr"),
        sa.CheckConstraint("type IN ('cash', 'investment', 'income', 'expense', 'liability', 'equity')", name="ck_accounts_type"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_accounts_id_user_id"),
        sa.UniqueConstraint("user_id", "name", name="uq_accounts_user_name"),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    op.create_table(
        "journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('opening', 'income', 'expense')", name="ck_journal_entries_kind"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_journal_entries_id_user_id"),
    )
    op.create_index("ix_journal_entries_user_id", "journal_entries", ["user_id"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
    )
    op.create_index("ix_idempotency_records_user_id", "idempotency_records", ["user_id"])

    op.create_table(
        "journal_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.CheckConstraint("amount <> 0", name="ck_journal_lines_nonzero_amount"),
        sa.ForeignKeyConstraint(["account_id", "user_id"], ["accounts.id", "accounts.user_id"], name="fk_journal_lines_account_owner", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entry_id", "user_id"], ["journal_entries.id", "journal_entries.user_id"], name="fk_journal_lines_entry_owner", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id", "account_id", name="uq_journal_lines_entry_account"),
    )

    op.execute("""
        CREATE FUNCTION enforce_balanced_journal_entry() RETURNS trigger AS $$
        DECLARE target_entry uuid;
        DECLARE line_count integer;
        DECLARE line_total numeric(18,2);
        BEGIN
          target_entry := COALESCE(NEW.entry_id, OLD.entry_id);
          IF NOT EXISTS (SELECT 1 FROM journal_entries WHERE id = target_entry) THEN
            RETURN NULL;
          END IF;
          SELECT count(*), COALESCE(sum(amount), 0)
            INTO line_count, line_total
            FROM journal_lines WHERE entry_id = target_entry;
          IF line_count < 2 OR line_total <> 0 THEN
            RAISE EXCEPTION 'journal entry % must have at least two lines and balance to zero', target_entry;
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER journal_entry_balanced
        AFTER INSERT OR UPDATE OR DELETE ON journal_lines
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_balanced_journal_entry();
    """)
    op.execute("""
        CREATE FUNCTION enforce_balanced_journal_header() RETURNS trigger AS $$
        DECLARE line_count integer;
        DECLARE line_total numeric(18,2);
        BEGIN
          SELECT count(*), COALESCE(sum(amount), 0)
            INTO line_count, line_total
            FROM journal_lines WHERE entry_id = NEW.id;
          IF line_count < 2 OR line_total <> 0 THEN
            RAISE EXCEPTION 'journal entry % must have at least two lines and balance to zero', NEW.id;
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER journal_entry_has_balanced_lines
        AFTER INSERT OR UPDATE ON journal_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_balanced_journal_header();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS journal_entry_has_balanced_lines ON journal_entries")
    op.execute("DROP FUNCTION IF EXISTS enforce_balanced_journal_header()")
    op.execute("DROP TRIGGER IF EXISTS journal_entry_balanced ON journal_lines")
    op.execute("DROP FUNCTION IF EXISTS enforce_balanced_journal_entry()")
    op.drop_table("journal_lines")
    op.drop_index("ix_idempotency_records_user_id", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_journal_entries_user_id", table_name="journal_entries")
    op.drop_table("journal_entries")
    op.drop_index("ix_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
