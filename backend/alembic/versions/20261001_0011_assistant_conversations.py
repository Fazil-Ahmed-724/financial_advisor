"""Add read-only research assistant conversations.

Revision ID: 20261001_0011
Revises: 20261001_0010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="20261001_0011";down_revision="20261001_0010";branch_labels=None;depends_on=None
U=postgresql.UUID(as_uuid=True)

def upgrade():
    op.create_table("assistant_conversations",sa.Column("id",U,primary_key=True),sa.Column("user_id",U,nullable=False),sa.Column("title",sa.String(120),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"),sa.UniqueConstraint("id","user_id",name="uq_assistant_conversation_owner"))
    op.create_index("ix_assistant_conversations_user_id","assistant_conversations",["user_id"])
    op.create_table("assistant_messages",sa.Column("id",U,primary_key=True),sa.Column("conversation_id",U,nullable=False),sa.Column("user_id",U,nullable=False),sa.Column("sequence",sa.Integer(),nullable=False),sa.Column("role",sa.String(10),nullable=False),sa.Column("content",sa.String(12000),nullable=False),sa.Column("response_data",sa.JSON(),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),sa.CheckConstraint("role IN ('user','assistant')",name="ck_assistant_messages_role"),sa.ForeignKeyConstraint(["conversation_id","user_id"],["assistant_conversations.id","assistant_conversations.user_id"],ondelete="CASCADE",name="fk_assistant_messages_owner"),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"),sa.UniqueConstraint("conversation_id","sequence",name="uq_assistant_message_sequence"))
    op.create_index("ix_assistant_messages_conversation_id","assistant_messages",["conversation_id"]);op.create_index("ix_assistant_messages_user_id","assistant_messages",["user_id"])

def downgrade():
    op.drop_table("assistant_messages");op.drop_table("assistant_conversations")
