"""Add external investment trades, FIFO lots, tax rules, and sale analyses.

Revision ID: 20260929_0004
Revises: 20260929_0003
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260929_0004"
down_revision = "20260929_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_journal_entries_kind", "journal_entries", type_="check")
    op.create_check_constraint(
        "ck_journal_entries_kind", "journal_entries",
        "kind IN ('opening', 'income', 'expense', 'trade')",
    )
    op.create_table(
        "tax_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("gain_tax_rate", sa.Numeric(7, 4), nullable=False),
        sa.Column("source_note", sa.String(500), nullable=False),
        sa.Column("loss_treatment_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("gain_tax_rate >= 0 AND gain_tax_rate <= 100", name="ck_tax_rules_rate"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_tax_rules_dates"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tax_rules_user_id", "tax_rules", ["user_id"])
    op.create_table(
        "investment_trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("execution_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("fees", sa.Numeric(18, 2), nullable=False),
        sa.Column("gross_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("net_proceeds", sa.Numeric(18, 2), nullable=True),
        sa.Column("fifo_cost_basis", sa.Numeric(18, 2), nullable=True),
        sa.Column("realized_gain_loss", sa.Numeric(18, 2), nullable=True),
        sa.Column("investment_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cash_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_reference", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_investment_trades_side"),
        sa.CheckConstraint("quantity > 0", name="ck_investment_trades_quantity"),
        sa.CheckConstraint("execution_price > 0", name="ck_investment_trades_price"),
        sa.CheckConstraint("fees >= 0", name="ck_investment_trades_fees"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["investment_account_id", "user_id"], ["accounts.id", "accounts.user_id"], ondelete="RESTRICT", name="fk_investment_trades_investment_owner"),
        sa.ForeignKeyConstraint(["cash_account_id", "user_id"], ["accounts.id", "accounts.user_id"], ondelete="RESTRICT", name="fk_investment_trades_cash_owner"),
        sa.ForeignKeyConstraint(["journal_entry_id", "user_id"], ["journal_entries.id", "journal_entries.user_id"], ondelete="RESTRICT", name="fk_investment_trades_journal_owner"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_investment_trades_id_user_id"),
        sa.UniqueConstraint("journal_entry_id"),
    )
    op.create_index("ix_investment_trades_user_id", "investment_trades", ["user_id"])
    op.create_index("ix_investment_trades_symbol", "investment_trades", ["symbol"])
    op.create_table(
        "investment_lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("buy_trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investment_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        sa.Column("original_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("remaining_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("original_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("remaining_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("original_quantity > 0", name="ck_investment_lots_original_quantity"),
        sa.CheckConstraint("remaining_quantity >= 0", name="ck_investment_lots_remaining_quantity"),
        sa.CheckConstraint("remaining_quantity <= original_quantity", name="ck_investment_lots_remaining_le_original"),
        sa.CheckConstraint("original_cost >= 0 AND remaining_cost >= 0", name="ck_investment_lots_costs"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["investment_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["buy_trade_id", "user_id"], ["investment_trades.id", "investment_trades.user_id"], ondelete="CASCADE", name="fk_investment_lots_trade_owner"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("buy_trade_id"),
        sa.UniqueConstraint("id", "user_id", name="uq_investment_lots_id_user_id"),
    )
    op.create_index("ix_investment_lots_user_id", "investment_lots", ["user_id"])
    op.create_index("ix_investment_lots_investment_account_id", "investment_lots", ["investment_account_id"])
    op.create_index("ix_investment_lots_symbol", "investment_lots", ["symbol"])
    op.create_table(
        "lot_consumptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sell_trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("cost_basis", sa.Numeric(18, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_lot_consumptions_quantity"),
        sa.CheckConstraint("cost_basis >= 0", name="ck_lot_consumptions_cost_basis"),
        sa.ForeignKeyConstraint(["sell_trade_id", "user_id"], ["investment_trades.id", "investment_trades.user_id"], ondelete="CASCADE", name="fk_lot_consumptions_sell_owner"),
        sa.ForeignKeyConstraint(["lot_id", "user_id"], ["investment_lots.id", "investment_lots.user_id"], ondelete="RESTRICT", name="fk_lot_consumptions_lot_owner"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sell_trade_id", "lot_id", name="uq_lot_consumptions_trade_lot"),
    )
    op.create_table(
        "sale_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investment_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("hypothetical_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("estimated_fees", sa.Numeric(18, 2), nullable=False),
        sa.Column("gross_proceeds", sa.Numeric(18, 2), nullable=False),
        sa.Column("fifo_cost_basis", sa.Numeric(18, 2), nullable=False),
        sa.Column("gross_profit_loss", sa.Numeric(18, 2), nullable=False),
        sa.Column("estimated_tax", sa.Numeric(18, 2), nullable=True),
        sa.Column("net_proceeds", sa.Numeric(18, 2), nullable=False),
        sa.Column("net_profit_loss", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_status", sa.String(40), nullable=False),
        sa.Column("tax_rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("fifo_allocations", sa.JSON(), nullable=False),
        sa.Column("excluded_items", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0 AND hypothetical_price > 0 AND estimated_fees >= 0", name="ck_sale_analyses_inputs"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["investment_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_rule_id"], ["tax_rules.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sale_analyses_user_id", "sale_analyses", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_sale_analyses_user_id", table_name="sale_analyses")
    op.drop_table("sale_analyses")
    op.drop_table("lot_consumptions")
    op.drop_index("ix_investment_lots_symbol", table_name="investment_lots")
    op.drop_index("ix_investment_lots_investment_account_id", table_name="investment_lots")
    op.drop_index("ix_investment_lots_user_id", table_name="investment_lots")
    op.drop_table("investment_lots")
    op.drop_index("ix_investment_trades_symbol", table_name="investment_trades")
    op.drop_index("ix_investment_trades_user_id", table_name="investment_trades")
    op.drop_table("investment_trades")
    op.drop_index("ix_tax_rules_user_id", table_name="tax_rules")
    op.drop_table("tax_rules")
    op.drop_constraint("ck_journal_entries_kind", "journal_entries", type_="check")
    op.create_check_constraint("ck_journal_entries_kind", "journal_entries", "kind IN ('opening', 'income', 'expense')")
