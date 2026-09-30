"""Add investment decision journal, reviews, and audit events.

Revision ID: 20260929_0005
Revises: 20260929_0004
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260929_0005"
down_revision = "20260929_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("investment_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sale_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("instrument", sa.String(20), nullable=False),
        sa.Column("action_considered", sa.String(10), nullable=False),
        sa.Column("rationale", sa.String(4000), nullable=False),
        sa.Column("goal", sa.String(1000), nullable=False),
        sa.Column("expected_holding_period", sa.String(500), nullable=False),
        sa.Column("risk_factors", sa.String(2000), nullable=False),
        sa.Column("expected_outcome", sa.String(1000), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("planned_review_date", sa.Date(), nullable=True),
        sa.Column("exit_conditions", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("action_considered IN ('BUY', 'SELL', 'HOLD', 'AVOID')", name="ck_investment_decisions_action"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 100)", name="ck_investment_decisions_confidence"),
        sa.CheckConstraint("NOT (trade_id IS NOT NULL AND sale_analysis_id IS NOT NULL)", name="ck_investment_decisions_one_link"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trade_id", "user_id"], ["investment_trades.id", "investment_trades.user_id"], ondelete="RESTRICT", name="fk_investment_decisions_trade_owner"),
        sa.ForeignKeyConstraint(["sale_analysis_id"], ["sale_analyses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_investment_decisions_user_id", "investment_decisions", ["user_id"])
    op.create_table("decision_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("what_happened", sa.String(4000), nullable=False),
        sa.Column("assumptions_held", sa.String(2000), nullable=False),
        sa.Column("assumptions_failed", sa.String(2000), nullable=False),
        sa.Column("lessons_learned", sa.String(4000), nullable=False),
        sa.Column("thesis_written_before_trade", sa.Boolean(), nullable=True),
        sa.Column("risks_considered", sa.Boolean(), nullable=True),
        sa.Column("concentration_considered", sa.Boolean(), nullable=True),
        sa.Column("within_recorded_limits", sa.Boolean(), nullable=True),
        sa.Column("followed_original_plan", sa.Boolean(), nullable=True),
        sa.Column("outcome_snapshot", sa.JSON(), nullable=False),
        sa.Column("process_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_id"], ["investment_decisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_decision_reviews_user_id", "decision_reviews", ["user_id"])
    op.create_index("ix_decision_reviews_decision_id", "decision_reviews", ["decision_id"])
    op.create_table("audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_decision_reviews_decision_id", table_name="decision_reviews")
    op.drop_index("ix_decision_reviews_user_id", table_name="decision_reviews")
    op.drop_table("decision_reviews")
    op.drop_index("ix_investment_decisions_user_id", table_name="investment_decisions")
    op.drop_table("investment_decisions")
