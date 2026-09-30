import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas_investments import normalized_symbol


class DecisionCreate(BaseModel):
    trade_id: uuid.UUID | None = None
    sale_analysis_id: uuid.UUID | None = None
    decision_date: date
    instrument: str
    action_considered: Literal["BUY", "SELL", "HOLD", "AVOID"]
    rationale: str = Field(min_length=1, max_length=4000)
    goal: str = Field(min_length=1, max_length=1000)
    expected_holding_period: str = Field(min_length=1, max_length=500)
    risk_factors: str = Field(min_length=1, max_length=2000)
    expected_outcome: str = Field(min_length=1, max_length=1000)
    confidence: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    planned_review_date: date | None = None
    exit_conditions: str | None = Field(default=None, max_length=2000)

    _instrument = field_validator("instrument")(normalized_symbol)

    @model_validator(mode="after")
    def one_link_and_clean(self):
        if self.trade_id and self.sale_analysis_id:
            raise ValueError("link either a trade or a sale analysis, not both")
        if self.confidence is not None and not self.confidence.is_finite():
            raise ValueError("confidence must be finite")
        for field in ("rationale", "goal", "expected_holding_period", "risk_factors", "expected_outcome"):
            setattr(self, field, " ".join(getattr(self, field).split()))
        if self.exit_conditions is not None:
            self.exit_conditions = " ".join(self.exit_conditions.split()) or None
        return self


class ReviewCreate(BaseModel):
    what_happened: str = Field(min_length=1, max_length=4000)
    assumptions_held: str = Field(min_length=1, max_length=2000)
    assumptions_failed: str = Field(min_length=1, max_length=2000)
    lessons_learned: str = Field(min_length=1, max_length=4000)
    thesis_written_before_trade: bool | None = None
    risks_considered: bool | None = None
    concentration_considered: bool | None = None
    within_recorded_limits: bool | None = None
    followed_original_plan: bool | None = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    what_happened: str
    assumptions_held: str
    assumptions_failed: str
    lessons_learned: str
    thesis_written_before_trade: bool | None
    risks_considered: bool | None
    concentration_considered: bool | None
    within_recorded_limits: bool | None
    followed_original_plan: bool | None
    outcome_snapshot: dict
    process_snapshot: dict
    created_at: datetime


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    trade_id: uuid.UUID | None
    sale_analysis_id: uuid.UUID | None
    decision_date: date
    instrument: str
    action_considered: str
    rationale: str
    goal: str
    expected_holding_period: str
    risk_factors: str
    expected_outcome: str
    confidence: Decimal | None
    planned_review_date: date | None
    exit_conditions: str | None
    created_at: datetime


class DecisionDetail(DecisionResponse):
    outcome: dict
    reviews: list[ReviewResponse]
    process_and_outcome_are_separate: Literal[True] = True
    informational_only: Literal[True] = True
    order_placed: Literal[False] = False


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    entity_type: str
    entity_id: uuid.UUID | None
    details: dict
    created_at: datetime
