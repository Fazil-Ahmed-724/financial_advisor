import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    BigInteger,
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
from sqlalchemy.dialects.postgresql import JSONB,TSVECTOR, UUID
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


class MarketplaceListing(Base):
    __tablename__ = "marketplace_listings"
    __table_args__ = (
        CheckConstraint("source_platform IN ('Daraz','Temu','SHEIN','Other')", name="ck_marketplace_listings_platform"),
        CheckConstraint("source_price > 0", name="ck_marketplace_listings_price"),
        UniqueConstraint("id", "user_id", name="uq_marketplace_listings_id_user_id"),
        Index("uq_marketplace_listings_user_url", "user_id", "canonical_url", unique=True, postgresql_where=text("canonical_url IS NOT NULL")),
        Index("uq_marketplace_listings_user_source_id", "user_id", "source_platform", "source_listing_id", unique=True, postgresql_where=text("source_listing_id IS NOT NULL")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_method: Mapped[str] = mapped_column(String(30))
    source_platform: Mapped[str] = mapped_column(String(30), index=True)
    product_name: Mapped[str] = mapped_column(String(300))
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_listing_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    source_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    attributes: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[dict] = mapped_column(JSON)
    expected_karachi_selling_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    local_sales_channel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    information_quality: Mapped[str] = mapped_column(String(30))
    confirmed_inventory_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    inventory_valued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketplaceAnalysis(Base):
    __tablename__ = "marketplace_analyses"
    __table_args__ = (ForeignKeyConstraint(["listing_id", "user_id"], ["marketplace_listings.id", "marketplace_listings.user_id"], ondelete="RESTRICT", name="fk_marketplace_analyses_listing_owner"),)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunity_analyses.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    landed_cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    break_even_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    gross_margin_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    net_margin_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    inventory_cash_roi_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)


class MarketplaceOutcome(Base):
    __tablename__ = "marketplace_outcomes"
    __table_args__ = (
        CheckConstraint("purchased_quantity >= 0 AND sold_quantity >= 0 AND returned_quantity >= 0 AND remaining_quantity >= 0", name="ck_marketplace_outcomes_quantities"),
        UniqueConstraint("id", "user_id", name="uq_marketplace_outcomes_id_user_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("marketplace_analyses.analysis_id", ondelete="RESTRICT"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purchased_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    actual_purchase_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    actual_other_costs: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    sold_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    actual_sales_revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    actual_sales_fees: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    returned_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    return_costs: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    actual_net_result: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    forecast_error: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    assumption_differences: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketLocation(Base):
    __tablename__="market_locations"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    country_code:Mapped[str]=mapped_column(String(2));country_name:Mapped[str]=mapped_column(String(100));region_name:Mapped[str]=mapped_column(String(100));city_name:Mapped[str]=mapped_column(String(100));currency_code:Mapped[str]=mapped_column(String(3));timezone:Mapped[str]=mapped_column(String(60));is_active:Mapped[bool]=mapped_column(Boolean,server_default="true");created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class MarketplaceProduct(Base):
    __tablename__="marketplace_products";__table_args__=(UniqueConstraint("id","user_id",name="uq_marketplace_products_id_user_id"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);normalized_name:Mapped[str]=mapped_column(String(300),index=True);match_key:Mapped[str]=mapped_column(String(500),index=True);brand:Mapped[str|None]=mapped_column(String(100),nullable=True);model:Mapped[str|None]=mapped_column(String(100),nullable=True);category:Mapped[str|None]=mapped_column(String(100),nullable=True,index=True);canonical_attributes:Mapped[dict]=mapped_column(JSON);is_archived:Mapped[bool]=mapped_column(Boolean,server_default="false");merged_into_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_products.id",ondelete="RESTRICT"),nullable=True);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class MarketplaceProductObservation(Base):
    __tablename__="marketplace_product_observations";__table_args__=(ForeignKeyConstraint(["product_id","user_id"],["marketplace_products.id","marketplace_products.user_id"],ondelete="CASCADE",name="fk_marketplace_observations_owner"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),index=True);marketplace:Mapped[str]=mapped_column(String(30),index=True);source_type:Mapped[str]=mapped_column(String(30));source_reference:Mapped[str]=mapped_column(String(500));source_url:Mapped[str|None]=mapped_column(String(1000),nullable=True);observed_name:Mapped[str]=mapped_column(String(300));observed_price:Mapped[Decimal]=mapped_column(Numeric(18,4));currency_code:Mapped[str]=mapped_column(String(3));observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True);seller_name:Mapped[str|None]=mapped_column(String(200),nullable=True);seller_location:Mapped[str|None]=mapped_column(String(200),nullable=True);rating:Mapped[Decimal|None]=mapped_column(Numeric(3,2),nullable=True);rating_count:Mapped[int|None]=mapped_column(nullable=True);review_count:Mapped[int|None]=mapped_column(nullable=True);sold_count:Mapped[int|None]=mapped_column(nullable=True);listing_age_days:Mapped[int|None]=mapped_column(nullable=True);raw_attributes:Mapped[dict]=mapped_column(JSON);evidence:Mapped[dict]=mapped_column(JSON);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class MarketplaceSourcingOption(Base):
    __tablename__="marketplace_sourcing_options";__table_args__=(ForeignKeyConstraint(["product_id","user_id"],["marketplace_products.id","marketplace_products.user_id"],ondelete="CASCADE",name="fk_marketplace_sourcing_owner"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),index=True);market_location_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("market_locations.id",ondelete="RESTRICT"));source_type:Mapped[str]=mapped_column(String(30));supplier_name:Mapped[str|None]=mapped_column(String(200),nullable=True);source_channel:Mapped[str]=mapped_column(String(40));source_reference:Mapped[str|None]=mapped_column(String(500),nullable=True);unit_cost:Mapped[Decimal]=mapped_column(Numeric(18,2));currency_code:Mapped[str]=mapped_column(String(3));minimum_order_quantity:Mapped[Decimal|None]=mapped_column(Numeric(18,4),nullable=True);local_transport_cost:Mapped[Decimal|None]=mapped_column(Numeric(18,2),nullable=True);packaging_cost:Mapped[Decimal|None]=mapped_column(Numeric(18,2),nullable=True);lead_time_days:Mapped[int|None]=mapped_column(nullable=True);stock_available:Mapped[bool|None]=mapped_column(Boolean,nullable=True);observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True));evidence:Mapped[dict]=mapped_column(JSON);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class MarketplaceCompetitionSignal(Base):
    __tablename__="marketplace_competition_signals";__table_args__=(ForeignKeyConstraint(["product_id","user_id"],["marketplace_products.id","marketplace_products.user_id"],ondelete="CASCADE",name="fk_marketplace_competition_owner"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),index=True);market_location_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("market_locations.id",ondelete="RESTRICT"));source_type:Mapped[str]=mapped_column(String(30));source_reference:Mapped[str]=mapped_column(String(500));comparable_listing_count:Mapped[int|None]=mapped_column(nullable=True);seller_count:Mapped[int|None]=mapped_column(nullable=True);lowest_price:Mapped[Decimal|None]=mapped_column(Numeric(18,2),nullable=True);median_price:Mapped[Decimal|None]=mapped_column(Numeric(18,2),nullable=True);highest_price:Mapped[Decimal|None]=mapped_column(Numeric(18,2),nullable=True);price_dispersion:Mapped[Decimal|None]=mapped_column(Numeric(9,4),nullable=True);observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True));evidence:Mapped[dict]=mapped_column(JSON);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class MarketplaceProductRanking(Base):
    __tablename__="marketplace_product_rankings"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_products.id",ondelete="CASCADE"),index=True);market_location_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("market_locations.id",ondelete="RESTRICT"));marketplace_analysis_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_analyses.analysis_id",ondelete="RESTRICT"),nullable=True);demand_score:Mapped[Decimal|None]=mapped_column(Numeric(5,2),nullable=True);margin_score:Mapped[Decimal|None]=mapped_column(Numeric(5,2),nullable=True);competition_score:Mapped[Decimal|None]=mapped_column(Numeric(5,2),nullable=True);sourcing_score:Mapped[Decimal|None]=mapped_column(Numeric(5,2),nullable=True);logistics_score:Mapped[Decimal|None]=mapped_column(Numeric(5,2),nullable=True);evidence_confidence_score:Mapped[Decimal]=mapped_column(Numeric(5,2));overall_research_score:Mapped[Decimal|None]=mapped_column(Numeric(5,2),nullable=True);ranking_version:Mapped[str]=mapped_column(String(50));explanation:Mapped[dict]=mapped_column(JSON);calculated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True));created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class MarketplaceProductWatchlist(Base):
    __tablename__="marketplace_product_watchlists";__table_args__=(UniqueConstraint("user_id","product_id","market_location_id",name="uq_marketplace_watchlist_entry"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_products.id",ondelete="CASCADE"));market_location_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("market_locations.id",ondelete="RESTRICT"));notes:Mapped[str|None]=mapped_column(String(1000),nullable=True);is_active:Mapped[bool]=mapped_column(Boolean,server_default="true");created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class MarketplaceImportBatch(Base):
    __tablename__="marketplace_import_batches"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);import_type:Mapped[str]=mapped_column(String(30));source_classification:Mapped[str]=mapped_column(String(30));original_filename:Mapped[str]=mapped_column(String(255));status:Mapped[str]=mapped_column(String(20));column_mapping:Mapped[dict]=mapped_column(JSON);total_rows:Mapped[int]=mapped_column();valid_rows:Mapped[int]=mapped_column();invalid_rows:Mapped[int]=mapped_column();warning_rows:Mapped[int]=mapped_column();committed_rows:Mapped[int]=mapped_column();created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());committed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class MarketplaceImportRow(Base):
    __tablename__="marketplace_import_rows";__table_args__=(UniqueConstraint("import_batch_id","row_number",name="uq_marketplace_import_row_number"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);import_batch_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_import_batches.id",ondelete="CASCADE"),index=True);row_number:Mapped[int]=mapped_column();raw_data:Mapped[dict]=mapped_column(JSON);normalized_data:Mapped[dict|None]=mapped_column(JSON,nullable=True);validation_status:Mapped[str]=mapped_column(String(20));warnings:Mapped[list]=mapped_column(JSON);errors:Mapped[list]=mapped_column(JSON);duplicate_status:Mapped[str|None]=mapped_column(String(20),nullable=True);proposed_product_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_products.id",ondelete="SET NULL"),nullable=True);action:Mapped[str|None]=mapped_column(String(40),nullable=True);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class MarketplaceProductAlias(Base):
    __tablename__="marketplace_product_aliases";__table_args__=(UniqueConstraint("user_id","product_id","normalized_alias",name="uq_marketplace_product_alias"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_products.id",ondelete="CASCADE"),index=True);alias:Mapped[str]=mapped_column(String(300));normalized_alias:Mapped[str]=mapped_column(String(300),index=True);source:Mapped[str]=mapped_column(String(30));created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class MarketplaceProductMergeEvent(Base):
    __tablename__="marketplace_product_merge_events"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);source_product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_products.id",ondelete="RESTRICT"));target_product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_products.id",ondelete="RESTRICT"));reason:Mapped[str|None]=mapped_column(String(1000),nullable=True);snapshot:Mapped[dict]=mapped_column(JSON);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class MarketplaceProductSplitEvent(Base):
    __tablename__="marketplace_product_split_events"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);original_product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_products.id",ondelete="RESTRICT"));new_product_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("marketplace_products.id",ondelete="RESTRICT"));moved_observation_ids:Mapped[list]=mapped_column(JSON);reason:Mapped[str|None]=mapped_column(String(1000),nullable=True);snapshot:Mapped[dict]=mapped_column(JSON);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class MarketplaceResearchPreset(Base):
    __tablename__="marketplace_research_presets";__table_args__=(UniqueConstraint("user_id","name",name="uq_marketplace_research_preset_name"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);name:Mapped[str]=mapped_column(String(100));market_location_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("market_locations.id",ondelete="RESTRICT"));filters:Mapped[dict]=mapped_column(JSON);sorting:Mapped[dict]=mapped_column(JSON);is_default:Mapped[bool]=mapped_column(Boolean,server_default="false");created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class PsxImportBatch(Base):
    __tablename__="psx_import_batches";__table_args__=(UniqueConstraint("user_id","idempotency_key",name="uq_psx_import_idempotency"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);idempotency_key:Mapped[str]=mapped_column(String(120));original_filename:Mapped[str]=mapped_column(String(255));source_name:Mapped[str]=mapped_column(String(200));status:Mapped[str]=mapped_column(String(20));total_rows:Mapped[int]=mapped_column();valid_rows:Mapped[int]=mapped_column();invalid_rows:Mapped[int]=mapped_column();warning_rows:Mapped[int]=mapped_column();committed_rows:Mapped[int]=mapped_column();created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());committed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class PsxImportRow(Base):
    __tablename__="psx_import_rows";__table_args__=(UniqueConstraint("import_batch_id","row_number",name="uq_psx_import_row_number"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);import_batch_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("psx_import_batches.id",ondelete="CASCADE"),index=True);row_number:Mapped[int]=mapped_column();raw_data:Mapped[dict]=mapped_column(JSONB);normalized_data:Mapped[dict|None]=mapped_column(JSONB,nullable=True);validation_status:Mapped[str]=mapped_column(String(20));warnings:Mapped[list]=mapped_column(JSONB);errors:Mapped[list]=mapped_column(JSONB);duplicate_status:Mapped[str]=mapped_column(String(20));action:Mapped[str]=mapped_column(String(20));created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class PsxPriceObservation(Base):
    __tablename__="psx_price_observations";__table_args__=(UniqueConstraint("user_id","symbol","observation_date","adjustment_type",name="uq_psx_user_symbol_date_adjustment"),CheckConstraint("open_price>0 AND high_price>0 AND low_price>0 AND close_price>0",name="ck_psx_positive_prices"),CheckConstraint("volume>=0",name="ck_psx_nonnegative_volume"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);import_batch_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("psx_import_batches.id",ondelete="RESTRICT"),index=True);symbol:Mapped[str]=mapped_column(String(20),index=True);observation_date:Mapped[date]=mapped_column(index=True);open_price:Mapped[Decimal]=mapped_column(Numeric(18,4));high_price:Mapped[Decimal]=mapped_column(Numeric(18,4));low_price:Mapped[Decimal]=mapped_column(Numeric(18,4));close_price:Mapped[Decimal]=mapped_column(Numeric(18,4));volume:Mapped[int]=mapped_column(BigInteger);currency:Mapped[str]=mapped_column(String(3));source_name:Mapped[str]=mapped_column(String(200));adjustment_type:Mapped[str]=mapped_column(String(10));verification_status:Mapped[str]=mapped_column(String(20),server_default="unverified");created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class PortfolioInstrumentMapping(Base):
    __tablename__="portfolio_instrument_mappings"
    __table_args__=(UniqueConstraint("user_id","investment_account_id","holding_symbol",name="uq_portfolio_holding_mapping"),ForeignKeyConstraint(["investment_account_id","user_id"],["accounts.id","accounts.user_id"],ondelete="CASCADE",name="fk_portfolio_mapping_account_owner"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True)
    investment_account_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),nullable=False)
    holding_symbol:Mapped[str]=mapped_column(String(20))
    psx_symbol:Mapped[str]=mapped_column(String(20))
    confirmation_note:Mapped[str|None]=mapped_column(String(500),nullable=True)
    confirmed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class AssistantConversation(Base):
    __tablename__="assistant_conversations"
    __table_args__=(UniqueConstraint("id","user_id",name="uq_assistant_conversation_owner"),)
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True)
    title:Mapped[str]=mapped_column(String(120))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class AssistantMessage(Base):
    __tablename__="assistant_messages"
    __table_args__=(CheckConstraint("role IN ('user','assistant')",name="ck_assistant_messages_role"),ForeignKeyConstraint(["conversation_id","user_id"],["assistant_conversations.id","assistant_conversations.user_id"],ondelete="CASCADE",name="fk_assistant_messages_owner"),UniqueConstraint("conversation_id","sequence",name="uq_assistant_message_sequence"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    conversation_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),index=True)
    user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True)
    sequence:Mapped[int]=mapped_column()
    role:Mapped[str]=mapped_column(String(10))
    content:Mapped[str]=mapped_column(String(12000))
    response_data:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

NOTIFICATION_EVENT_TYPES=("reminder_due","assistant_response_ready","feedback_review_status_changed","test_notification")

class NotificationDevice(Base):
    __tablename__="notification_devices"
    __table_args__=(UniqueConstraint("user_id","installation_id",name="uq_notification_device_installation"),UniqueConstraint("expo_push_token",name="uq_notification_device_push_token"),CheckConstraint("platform IN ('android','ios')",name="ck_notification_device_platform"),CheckConstraint("push_status IN ('unregistered','active','disabled','invalid','revoked')",name="ck_notification_device_status"),UniqueConstraint("id","user_id",name="uq_notification_device_owner"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True)
    installation_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True))
    platform:Mapped[str]=mapped_column(String(10));display_name:Mapped[str]=mapped_column(String(80))
    expo_push_token:Mapped[str|None]=mapped_column(String(300),nullable=True)
    push_status:Mapped[str]=mapped_column(String(20),server_default="unregistered")
    notifications_enabled:Mapped[bool]=mapped_column(Boolean,server_default="false")
    session_version:Mapped[int]=mapped_column(server_default="1")
    last_seen_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class NotificationPreference(Base):
    __tablename__="notification_preferences"
    __table_args__=(CheckConstraint("event_type IN ('reminder_due','assistant_response_ready','feedback_review_status_changed')",name="ck_notification_preference_event"),UniqueConstraint("user_id","event_type",name="uq_notification_user_preference"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);event_type:Mapped[str]=mapped_column(String(50));enabled:Mapped[bool]=mapped_column(Boolean,server_default="false");updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class DeviceNotificationPreference(Base):
    __tablename__="device_notification_preferences"
    __table_args__=(CheckConstraint("event_type IN ('reminder_due','assistant_response_ready','feedback_review_status_changed')",name="ck_device_notification_preference_event"),ForeignKeyConstraint(["device_id","user_id"],["notification_devices.id","notification_devices.user_id"],ondelete="CASCADE",name="fk_device_notification_preference_owner"),UniqueConstraint("device_id","event_type",name="uq_device_notification_preference"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);device_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),index=True);event_type:Mapped[str]=mapped_column(String(50));enabled:Mapped[bool]=mapped_column(Boolean,server_default="false");updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class NotificationEvent(Base):
    __tablename__="notification_events"
    __table_args__=(CheckConstraint("event_type IN ('reminder_due','assistant_response_ready','feedback_review_status_changed','test_notification')",name="ck_notification_event_type"),UniqueConstraint("user_id","event_type","dedupe_key",name="uq_notification_event_dedupe"),UniqueConstraint("id","user_id",name="uq_notification_event_owner"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);event_type:Mapped[str]=mapped_column(String(50));dedupe_key:Mapped[str]=mapped_column(String(120));deep_link:Mapped[str]=mapped_column(String(200));created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class NotificationDelivery(Base):
    __tablename__="notification_deliveries"
    __table_args__=(ForeignKeyConstraint(["event_id","user_id"],["notification_events.id","notification_events.user_id"],ondelete="CASCADE",name="fk_notification_delivery_event_owner"),ForeignKeyConstraint(["device_id","user_id"],["notification_devices.id","notification_devices.user_id"],ondelete="CASCADE",name="fk_notification_delivery_device_owner"),UniqueConstraint("event_id","device_id",name="uq_notification_delivery_fanout"),CheckConstraint("status IN ('pending','retry','accepted','delivered','permanent_failure','dead_letter','unknown')",name="ck_notification_delivery_status"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4);user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True);event_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),index=True);device_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),index=True);status:Mapped[str]=mapped_column(String(30),server_default="pending",index=True);attempt_count:Mapped[int]=mapped_column(server_default="0");next_attempt_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),index=True);expo_ticket_id:Mapped[str|None]=mapped_column(String(100),nullable=True,index=True);last_error_code:Mapped[str|None]=mapped_column(String(60),nullable=True);accepted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True);receipt_checked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True);acknowledged_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())
