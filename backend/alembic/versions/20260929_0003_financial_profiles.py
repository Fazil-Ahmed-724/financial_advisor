"""Add financial profile and emergency reserve settings.

Revision ID: 20260929_0003
Revises: 20260929_0002
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260929_0003"
down_revision = "20260929_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "monthly_essential_expenses",
            sa.Numeric(precision=18, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column("reserve_months", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "monthly_essential_expenses >= 0",
            name="ck_financial_profiles_nonnegative_expenses",
        ),
        sa.CheckConstraint(
            "reserve_months >= 0 AND reserve_months <= 24",
            name="ck_financial_profiles_reserve_months",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.execute("""
        INSERT INTO financial_profiles (user_id)
        SELECT id FROM users
        ON CONFLICT (user_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("financial_profiles")
