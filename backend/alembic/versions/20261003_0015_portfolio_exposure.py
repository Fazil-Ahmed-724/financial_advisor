"""Add confirmed holding to PSX instrument mappings.

Revision ID: 20261003_0015
Revises: 20261003_0014
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="20261003_0015";down_revision="20261003_0014";branch_labels=None;depends_on=None
U=postgresql.UUID(as_uuid=True)
def upgrade():
    op.create_table("portfolio_instrument_mappings",sa.Column("id",U,primary_key=True),sa.Column("user_id",U,sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("investment_account_id",U,nullable=False),sa.Column("holding_symbol",sa.String(20),nullable=False),sa.Column("psx_symbol",sa.String(20),nullable=False),sa.Column("confirmation_note",sa.String(500)),sa.Column("confirmed_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(["investment_account_id","user_id"],["accounts.id","accounts.user_id"],ondelete="CASCADE",name="fk_portfolio_mapping_account_owner"),sa.UniqueConstraint("user_id","investment_account_id","holding_symbol",name="uq_portfolio_holding_mapping"))
    op.create_index("ix_portfolio_instrument_mappings_user_id","portfolio_instrument_mappings",["user_id"])
def downgrade():op.drop_table("portfolio_instrument_mappings")
