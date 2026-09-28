from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.database import engine


def test_initial_migration_builds_schema_from_clean_database():
    config = Config("alembic.ini")

    command.downgrade(config, "base")
    assert "users" not in inspect(engine).get_table_names()

    command.upgrade(config, "20260929_0001")
    inspector = inspect(engine)
    assert "users" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("users")} == {
        "id",
        "email",
        "password_hash",
        "created_at",
    }
    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert revision == "20260929_0001"

    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert {"accounts", "journal_entries", "journal_lines", "idempotency_records"} <= set(
        inspector.get_table_names()
    )
    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert revision == "20260929_0002"
