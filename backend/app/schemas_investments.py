import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MONEY = dict(max_digits=18, decimal_places=2)


class TradeSide(str, Enum):
    buy = "BUY"
    sell = "SELL"


def normalized_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,19}", symbol):
        raise ValueError("symbol must contain only letters, numbers, dot, or hyphen")
    return symbol


class TradeCreate(BaseModel):
    side: TradeSide
    symbol: str
    trade_date: date
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    execution_price: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    fees: Decimal = Field(default=Decimal("0.00"), ge=0, **MONEY)
    investment_account_id: uuid.UUID
    cash_account_id: uuid.UUID
    external_reference: str | None = Field(default=None, max_length=255)

    _symbol = field_validator("symbol")(normalized_symbol)

    @field_validator("quantity", "execution_price", "fees")
    @classmethod
    def finite_decimals(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("numeric values must be finite")
        return value

    @field_validator("external_reference")
    @classmethod
    def clean_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("trade_date")
    @classmethod
    def completed_trade_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("completed external trades cannot have a future date")
        return value


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    side: Literal["BUY", "SELL"]
    symbol: str
    trade_date: date
    quantity: Decimal
    execution_price: Decimal
    fees: Decimal
    gross_amount: Decimal
    net_proceeds: Decimal | None
    fifo_cost_basis: Decimal | None
    realized_gain_loss: Decimal | None
    investment_account_id: uuid.UUID
    cash_account_id: uuid.UUID
    journal_entry_id: uuid.UUID
    external_reference: str | None
    created_at: datetime
    execution_boundary: Literal["recorded_external_transaction"] = "recorded_external_transaction"


class LotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    buy_trade_id: uuid.UUID
    investment_account_id: uuid.UUID
    symbol: str
    acquired_on: date
    original_quantity: Decimal
    remaining_quantity: Decimal
    original_cost: Decimal
    remaining_cost: Decimal


class HoldingResponse(BaseModel):
    symbol: str
    investment_account_id: uuid.UUID
    quantity: Decimal
    remaining_book_cost: Decimal
    realized_gain_loss: Decimal
    currency: Literal["PKR"] = "PKR"
    valuation_basis: Literal["ledger_book_value"] = "ledger_book_value"
    lots: list[LotResponse]


class TaxRuleCreate(BaseModel):
    effective_from: date
    effective_to: date | None = None
    gain_tax_rate: Decimal = Field(ge=0, le=100, max_digits=7, decimal_places=4)
    source_note: str = Field(min_length=1, max_length=500)
    loss_treatment_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        if not self.gain_tax_rate.is_finite():
            raise ValueError("gain_tax_rate must be finite")
        self.source_note = " ".join(self.source_note.split())
        if self.loss_treatment_note is not None:
            self.loss_treatment_note = " ".join(self.loss_treatment_note.split()) or None
        return self


class TaxRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    effective_from: date
    effective_to: date | None
    gain_tax_rate: Decimal
    source_note: str
    loss_treatment_note: str | None
    created_at: datetime


class SaleAnalysisCreate(BaseModel):
    investment_account_id: uuid.UUID
    symbol: str
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    hypothetical_price: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    estimated_fees: Decimal = Field(default=Decimal("0.00"), ge=0, **MONEY)
    calculation_date: date

    _symbol = field_validator("symbol")(normalized_symbol)

    @field_validator("quantity", "hypothetical_price", "estimated_fees")
    @classmethod
    def finite_values(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("numeric values must be finite")
        return value


class SaleAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    investment_account_id: uuid.UUID
    symbol: str
    quantity: Decimal
    hypothetical_price: Decimal
    estimated_fees: Decimal
    gross_proceeds: Decimal
    fifo_cost_basis: Decimal
    gross_profit_loss: Decimal
    estimated_tax: Decimal | None
    net_proceeds: Decimal
    net_profit_loss: Decimal
    tax_status: str
    tax_rule_id: uuid.UUID | None
    assumptions: dict
    fifo_allocations: list
    excluded_items: list
    calculated_at: datetime
    result_type: Literal["estimate_only"] = "estimate_only"
    order_placed: Literal[False] = False
