import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AccountType(str, Enum):
    cash = "cash"
    investment = "investment"
    income = "income"
    expense = "expense"
    liability = "liability"
    equity = "equity"


class EntryKind(str, Enum):
    opening = "opening"
    income = "income"
    expense = "expense"


def normalize_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType
    currency: str = Field(default="PKR", min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_name(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        currency = value.strip().upper()
        if currency != "PKR":
            raise ValueError("Phase 1 supports PKR only")
        return currency


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: AccountType
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class JournalLineCreate(BaseModel):
    account_id: uuid.UUID
    amount: Decimal = Field(max_digits=18, decimal_places=2)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("amount must be finite")
        if value == 0:
            raise ValueError("amount must be nonzero")
        return value


class JournalEntryCreate(BaseModel):
    kind: EntryKind
    description: str | None = Field(default=None, max_length=255)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lines: list[JournalLineCreate] = Field(min_length=2, max_length=2)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        return normalized or None

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_lines(self):
        if self.lines[0].account_id == self.lines[1].account_id:
            raise ValueError("journal lines must use different accounts")
        if sum((line.amount for line in self.lines), Decimal("0.00")) != Decimal(
            "0.00"
        ):
            raise ValueError("journal entry must balance to zero")
        return self


class JournalLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    amount: Decimal


class JournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: EntryKind
    description: str | None
    occurred_at: datetime
    created_at: datetime
    lines: list[JournalLineResponse]


class AccountBalanceResponse(BaseModel):
    account: AccountResponse
    balance: Decimal
