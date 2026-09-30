from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FinancialProfileUpdate(BaseModel):
    monthly_essential_expenses: Decimal = Field(
        ge=Decimal("0.00"), max_digits=18, decimal_places=2
    )
    reserve_months: int = Field(ge=0, le=24)

    @field_validator("monthly_essential_expenses")
    @classmethod
    def validate_expenses(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("monthly essential expenses must be finite")
        return value


class FinancialProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    monthly_essential_expenses: Decimal
    reserve_months: int
    currency: Literal["PKR"] = "PKR"
    created_at: datetime
    updated_at: datetime


class DashboardResponse(BaseModel):
    currency: Literal["PKR"] = "PKR"
    cash_balance: Decimal
    investment_book_value: Decimal
    liability_balance: Decimal
    net_worth_book_value: Decimal
    monthly_essential_expenses: Decimal
    reserve_months: int
    reserve_target: Decimal
    protected_emergency_cash: Decimal
    investable_cash: Decimal
    valuation_basis: Literal["ledger_book_value"] = "ledger_book_value"
    market_values_available: Literal[False] = False
    confirmed_property_value: Decimal = Decimal("0.00")
    net_worth_with_confirmed_property: Decimal = Decimal("0.00")
    property_value_basis: Literal["user_confirmed_only"] = "user_confirmed_only"
    confirmed_resale_inventory_value: Decimal = Decimal("0.00")
    net_worth_with_confirmed_assets: Decimal = Decimal("0.00")
    inventory_value_basis: Literal["user_confirmed_only"] = "user_confirmed_only"
