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
    assert revision == "20261001_0010"
    assert "financial_profiles" in inspector.get_table_names()
    assert {
        "investment_trades", "investment_lots", "lot_consumptions",
        "tax_rules", "sale_analyses",
    } <= set(inspector.get_table_names())
    assert {"investment_decisions", "decision_reviews", "audit_events"} <= set(inspector.get_table_names())
    assert {"books", "book_passages", "decision_passages"} <= set(inspector.get_table_names())
    assert {"opportunity_analyses", "property_listings", "property_analyses"} <= set(inspector.get_table_names())
    assert {"marketplace_listings", "marketplace_analyses", "marketplace_outcomes"} <= set(inspector.get_table_names())
    assert {"market_locations", "marketplace_products", "marketplace_product_observations", "marketplace_sourcing_options", "marketplace_competition_signals", "marketplace_product_rankings", "marketplace_product_watchlists"} <= set(inspector.get_table_names())
    assert {"marketplace_import_batches", "marketplace_import_rows", "marketplace_product_aliases", "marketplace_product_merge_events", "marketplace_product_split_events", "marketplace_research_presets"} <= set(inspector.get_table_names())
