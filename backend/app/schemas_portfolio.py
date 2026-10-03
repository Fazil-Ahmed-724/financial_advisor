import re,uuid
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel,Field,field_validator
SYMBOL=re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,19}$")
class MappingPayload(BaseModel):
    investment_account_id:uuid.UUID;holding_symbol:str;psx_symbol:str;confirmed:Literal[True];confirmation_note:str|None=Field(default=None,max_length=500)
    @field_validator("holding_symbol","psx_symbol")
    @classmethod
    def symbol(cls,v):
        v=v.strip().upper()
        if not SYMBOL.fullmatch(v):raise ValueError("invalid symbol")
        return v
class SaleEstimatePayload(BaseModel):
    investment_account_id:uuid.UUID;holding_symbol:str;quantity:Decimal=Field(gt=0,max_digits=24,decimal_places=8);estimated_fees:Decimal=Field(default=Decimal("0"),ge=0,max_digits=18,decimal_places=2);as_of_date:date|None=None
    @field_validator("holding_symbol")
    @classmethod
    def symbol(cls,v):return v.strip().upper()
