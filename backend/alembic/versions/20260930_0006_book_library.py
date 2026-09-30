"""Add private book library, passages, and decision learning links.

Revision ID: 20260930_0006
Revises: 20260929_0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="20260930_0006"; down_revision="20260929_0005"; branch_labels=None; depends_on=None

def upgrade():
    op.create_table("books",
      sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True), sa.Column("user_id",postgresql.UUID(as_uuid=True),nullable=False),
      sa.Column("title",sa.String(500),nullable=False),sa.Column("author",sa.String(300),nullable=False),sa.Column("edition",sa.String(100)),sa.Column("publication_year",sa.Integer()),sa.Column("topic",sa.String(200),nullable=False),sa.Column("source",sa.String(500),nullable=False),sa.Column("language",sa.String(20),nullable=False),
      sa.Column("original_filename",sa.String(255),nullable=False),sa.Column("media_type",sa.String(100),nullable=False),sa.Column("storage_key",sa.String(100),nullable=False,unique=True),sa.Column("file_size",sa.Integer(),nullable=False),sa.Column("checksum_sha256",sa.String(64),nullable=False),sa.Column("extraction_version",sa.Integer(),nullable=False),sa.Column("ingestion_status",sa.String(40),nullable=False),sa.Column("status_detail",sa.String(500)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),
      sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"),sa.UniqueConstraint("id","user_id",name="uq_books_id_user_id"))
    op.create_index("ix_books_user_id","books",["user_id"])
    op.create_table("book_passages",
      sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("book_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("user_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("extraction_version",sa.Integer(),nullable=False),sa.Column("sequence",sa.Integer(),nullable=False),sa.Column("reference_type",sa.String(20),nullable=False),sa.Column("reference_label",sa.String(300),nullable=False),sa.Column("content",sa.String(4000),nullable=False),sa.Column("search_vector",postgresql.TSVECTOR(),nullable=False),
      sa.ForeignKeyConstraint(["book_id","user_id"],["books.id","books.user_id"],ondelete="CASCADE",name="fk_book_passages_owner"),sa.UniqueConstraint("book_id","extraction_version","sequence",name="uq_book_passages_version_sequence"),sa.UniqueConstraint("id","user_id",name="uq_book_passages_id_user_id"))
    op.create_index("ix_book_passages_book_id","book_passages",["book_id"]);op.create_index("ix_book_passages_user_id","book_passages",["user_id"]);op.create_index("ix_book_passages_search_vector","book_passages",["search_vector"],postgresql_using="gin")
    op.create_table("decision_passages",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("user_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("decision_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("passage_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("note",sa.String(1000)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["decision_id"],["investment_decisions.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["passage_id","user_id"],["book_passages.id","book_passages.user_id"],ondelete="CASCADE",name="fk_decision_passages_passage_owner"),sa.UniqueConstraint("decision_id","passage_id",name="uq_decision_passages_link"))
    op.create_index("ix_decision_passages_user_id","decision_passages",["user_id"]);op.create_index("ix_decision_passages_decision_id","decision_passages",["decision_id"])
def downgrade():
    op.drop_table("decision_passages");op.drop_index("ix_book_passages_search_vector",table_name="book_passages");op.drop_table("book_passages");op.drop_table("books")
