import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    JSON,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


ACCOUNT_TYPES = ("cash", "investment", "income", "expense", "liability", "equity")
ENTRY_KINDS = ("opening", "income", "expense", "trade")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "type IN ('cash', 'investment', 'income', 'expense', 'liability', 'equity')",
            name="ck_accounts_type",
        ),
        CheckConstraint("currency = 'PKR'", name="ck_accounts_currency_pkr"),
        UniqueConstraint("id", "user_id", name="uq_accounts_id_user_id"),
        UniqueConstraint("user_id", "name", name="uq_accounts_user_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('opening', 'income', 'expense', 'trade')", name="ck_journal_entries_kind"
        ),
        UniqueConstraint("id", "user_id", name="uq_journal_entries_id_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", lazy="selectin"
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_journal_lines_nonzero_amount"),
        ForeignKeyConstraint(
            ["entry_id", "user_id"],
            ["journal_entries.id", "journal_entries.user_id"],
            ondelete="CASCADE",
            name="fk_journal_lines_entry_owner",
        ),
        ForeignKeyConstraint(
            ["account_id", "user_id"],
            ["accounts.id", "accounts.user_id"],
            ondelete="RESTRICT",
            name="fk_journal_lines_account_owner",
        ),
        UniqueConstraint("entry_id", "account_id", name="uq_journal_lines_entry_account"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    entry: Mapped[JournalEntry] = relationship(back_populates="lines")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(200))
    operation: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FinancialProfile(Base):
    __tablename__ = "financial_profiles"
    __table_args__ = (
        CheckConstraint(
            "monthly_essential_expenses >= 0",
            name="ck_financial_profiles_nonnegative_expenses",
        ),
        CheckConstraint(
            "reserve_months >= 0 AND reserve_months <= 24",
            name="ck_financial_profiles_reserve_months",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    monthly_essential_expenses: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), server_default="0.00"
    )
    reserve_months: Mapped[int] = mapped_column(default=3, server_default="3")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InvestmentTrade(Base):
    __tablename__ = "investment_trades"
    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_investment_trades_side"),
        CheckConstraint("quantity > 0", name="ck_investment_trades_quantity"),
        CheckConstraint("execution_price > 0", name="ck_investment_trades_price"),
        CheckConstraint("fees >= 0", name="ck_investment_trades_fees"),
        ForeignKeyConstraint(
            ["investment_account_id", "user_id"], ["accounts.id", "accounts.user_id"],
            ondelete="RESTRICT", name="fk_investment_trades_investment_owner",
        ),
        ForeignKeyConstraint(
            ["cash_account_id", "user_id"], ["accounts.id", "accounts.user_id"],
            ondelete="RESTRICT", name="fk_investment_trades_cash_owner",
        ),
        ForeignKeyConstraint(
            ["journal_entry_id", "user_id"], ["journal_entries.id", "journal_entries.user_id"],
            ondelete="RESTRICT", name="fk_investment_trades_journal_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_investment_trades_id_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    side: Mapped[str] = mapped_column(String(4))
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    trade_date: Mapped[date] = mapped_column(nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    execution_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    net_proceeds: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    fifo_cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    realized_gain_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    investment_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cash_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvestmentLot(Base):
    __tablename__ = "investment_lots"
    __table_args__ = (
        CheckConstraint("original_quantity > 0", name="ck_investment_lots_original_quantity"),
        CheckConstraint("remaining_quantity >= 0", name="ck_investment_lots_remaining_quantity"),
        CheckConstraint("remaining_quantity <= original_quantity", name="ck_investment_lots_remaining_le_original"),
        CheckConstraint("original_cost >= 0 AND remaining_cost >= 0", name="ck_investment_lots_costs"),
        ForeignKeyConstraint(
            ["buy_trade_id", "user_id"], ["investment_trades.id", "investment_trades.user_id"],
            ondelete="CASCADE", name="fk_investment_lots_trade_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_investment_lots_id_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    buy_trade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    investment_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    acquired_on: Mapped[date] = mapped_column(nullable=False)
    original_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    original_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    remaining_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LotConsumption(Base):
    __tablename__ = "lot_consumptions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_lot_consumptions_quantity"),
        CheckConstraint("cost_basis >= 0", name="ck_lot_consumptions_cost_basis"),
        ForeignKeyConstraint(["sell_trade_id", "user_id"], ["investment_trades.id", "investment_trades.user_id"], ondelete="CASCADE", name="fk_lot_consumptions_sell_owner"),
        ForeignKeyConstraint(["lot_id", "user_id"], ["investment_lots.id", "investment_lots.user_id"], ondelete="RESTRICT", name="fk_lot_consumptions_lot_owner"),
        UniqueConstraint("sell_trade_id", "lot_id", name="uq_lot_consumptions_trade_lot"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sell_trade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class TaxRule(Base):
    __tablename__ = "tax_rules"
    __table_args__ = (
        CheckConstraint("gain_tax_rate >= 0 AND gain_tax_rate <= 100", name="ck_tax_rules_rate"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_tax_rules_dates"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    effective_from: Mapped[date] = mapped_column(nullable=False)
    effective_to: Mapped[date | None] = mapped_column(nullable=True)
    gain_tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    source_note: Mapped[str] = mapped_column(String(500))
    loss_treatment_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SaleAnalysis(Base):
    __tablename__ = "sale_analyses"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND hypothetical_price > 0 AND estimated_fees >= 0", name="ck_sale_analyses_inputs"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    investment_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"))
    symbol: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    hypothetical_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    estimated_fees: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    gross_proceeds: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    fifo_cost_basis: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    gross_profit_loss: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    estimated_tax: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    net_proceeds: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    net_profit_loss: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    tax_status: Mapped[str] = mapped_column(String(40))
    tax_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_rules.id", ondelete="SET NULL"), nullable=True)
    assumptions: Mapped[dict] = mapped_column(JSON)
    fifo_allocations: Mapped[list] = mapped_column(JSON)
    excluded_items: Mapped[list] = mapped_column(JSON)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvestmentDecision(Base):
    __tablename__ = "investment_decisions"
    __table_args__ = (
        CheckConstraint("action_considered IN ('BUY', 'SELL', 'HOLD', 'AVOID')", name="ck_investment_decisions_action"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 100)", name="ck_investment_decisions_confidence"),
        CheckConstraint("NOT (trade_id IS NOT NULL AND sale_analysis_id IS NOT NULL)", name="ck_investment_decisions_one_link"),
        ForeignKeyConstraint(["trade_id", "user_id"], ["investment_trades.id", "investment_trades.user_id"], ondelete="RESTRICT", name="fk_investment_decisions_trade_owner"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trade_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sale_analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_analyses.id", ondelete="RESTRICT"), nullable=True)
    decision_date: Mapped[date] = mapped_column(nullable=False)
    instrument: Mapped[str] = mapped_column(String(20))
    action_considered: Mapped[str] = mapped_column(String(10))
    rationale: Mapped[str] = mapped_column(String(4000))
    goal: Mapped[str] = mapped_column(String(1000))
    expected_holding_period: Mapped[str] = mapped_column(String(500))
    risk_factors: Mapped[str] = mapped_column(String(2000))
    expected_outcome: Mapped[str] = mapped_column(String(1000))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    planned_review_date: Mapped[date | None] = mapped_column(nullable=True)
    exit_conditions: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DecisionReview(Base):
    __tablename__ = "decision_reviews"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("investment_decisions.id", ondelete="CASCADE"), index=True)
    what_happened: Mapped[str] = mapped_column(String(4000))
    assumptions_held: Mapped[str] = mapped_column(String(2000))
    assumptions_failed: Mapped[str] = mapped_column(String(2000))
    lessons_learned: Mapped[str] = mapped_column(String(4000))
    thesis_written_before_trade: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    risks_considered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    concentration_considered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    within_recorded_limits: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    followed_original_plan: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outcome_snapshot: Mapped[dict] = mapped_column(JSON)
    process_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_books_id_user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(300))
    edition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(nullable=True)
    topic: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(20), default="en")
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    file_size: Mapped[int] = mapped_column()
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    extraction_version: Mapped[int] = mapped_column(default=1)
    ingestion_status: Mapped[str] = mapped_column(String(40))
    status_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BookPassage(Base):
    __tablename__ = "book_passages"
    __table_args__ = (
        ForeignKeyConstraint(["book_id", "user_id"], ["books.id", "books.user_id"], ondelete="CASCADE", name="fk_book_passages_owner"),
        UniqueConstraint("book_id", "extraction_version", "sequence", name="uq_book_passages_version_sequence"),
        UniqueConstraint("id", "user_id", name="uq_book_passages_id_user_id"),
        Index("ix_book_passages_search_vector", "search_vector", postgresql_using="gin"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    extraction_version: Mapped[int] = mapped_column()
    sequence: Mapped[int] = mapped_column()
    reference_type: Mapped[str] = mapped_column(String(20))
    reference_label: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(String(4000))
    search_vector: Mapped[str] = mapped_column(TSVECTOR)


class DecisionPassage(Base):
    __tablename__ = "decision_passages"
    __table_args__ = (
        ForeignKeyConstraint(["passage_id", "user_id"], ["book_passages.id", "book_passages.user_id"], ondelete="CASCADE", name="fk_decision_passages_passage_owner"),
        UniqueConstraint("decision_id", "passage_id", name="uq_decision_passages_link"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("investment_decisions.id", ondelete="CASCADE"), index=True)
    passage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpportunityAnalysis(Base):
    __tablename__ = "opportunity_analyses"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_opportunity_analyses_id_user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(50), index=True)
    source: Mapped[str] = mapped_column(String(200))
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    source_evidence: Mapped[dict] = mapped_column(JSON)
    assumptions: Mapped[dict] = mapped_column(JSON)
    calculated_metrics: Mapped[dict] = mapped_column(JSON)
    recommendation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    limitations: Mapped[list] = mapped_column(JSON)
    analyzer_version: Mapped[str] = mapped_column(String(50))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PropertyListing(Base):
    __tablename__ = "property_listings"
    __table_args__ = (
        CheckConstraint("city = 'Karachi'", name="ck_property_listings_karachi"),
        CheckConstraint("purpose IN ('sale', 'rent')", name="ck_property_listings_purpose"),
        CheckConstraint("area_amount > 0 AND asking_amount > 0", name="ck_property_listings_positive_values"),
        CheckConstraint("area_unit IN ('sq_ft','sq_yd','marla_225_sq_ft','marla_272_25_sq_ft','kanal_4500_sq_ft','kanal_5445_sq_ft')", name="ck_property_listings_area_unit"),
        UniqueConstraint("id", "user_id", name="uq_property_listings_id_user_id"),
        Index("uq_property_listings_user_url", "user_id", "canonical_url", unique=True, postgresql_where=text("canonical_url IS NOT NULL")),
        Index("uq_property_listings_user_source_id", "user_id", "source_name", "source_id", unique=True, postgresql_where=text("source_id IS NOT NULL")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    city: Mapped[str] = mapped_column(String(50), default="Karachi")
    source_type: Mapped[str] = mapped_column(String(30))
    source_name: Mapped[str] = mapped_column(String(200))
    canonical_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    listing_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    purpose: Mapped[str] = mapped_column(String(10), index=True)
    property_type: Mapped[str] = mapped_column(String(80), index=True)
    area_name: Mapped[str] = mapped_column(String(200), index=True)
    area_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    area_unit: Mapped[str] = mapped_column(String(30))
    asking_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    attributes: Mapped[dict] = mapped_column(JSON)
    information_quality: Mapped[str] = mapped_column(String(30))
    owned_by_user: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    confirmed_valuation: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    valuation_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PropertyAnalysis(Base):
    __tablename__ = "property_analyses"
    __table_args__ = (CheckConstraint("analysis_type IN ('comparables','yield')", name="ck_property_analyses_type"),)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunity_analyses.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    analysis_type: Mapped[str] = mapped_column(String(20))
    comparable_count: Mapped[int | None] = mapped_column(nullable=True)
    median_asking_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    minimum_asking_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    maximum_asking_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    monthly_rent: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    annual_expenses: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    annual_tax_assumption: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    gross_yield_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)
    net_yield_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)
