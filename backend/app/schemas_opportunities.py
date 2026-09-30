import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AreaUnit=Literal["sq_ft","sq_yd","marla_225_sq_ft","marla_272_25_sq_ft","kanal_4500_sq_ft","kanal_5445_sq_ft"]
class PropertyListingCreate(BaseModel):
    city:str="Karachi";source_type:Literal["user_entered","authorized_export"]="user_entered";source_name:str=Field(min_length=1,max_length=200);canonical_url:str|None=Field(default=None,max_length=1000);source_id:str|None=Field(default=None,max_length=200);observed_at:datetime;listing_status:str|None=Field(default=None,max_length=40);purpose:Literal["sale","rent"];property_type:str=Field(min_length=1,max_length=80);area_name:str=Field(min_length=1,max_length=200);area_amount:Decimal=Field(gt=0,max_digits=18,decimal_places=4);area_unit:AreaUnit;asking_amount:Decimal=Field(gt=0,max_digits=18,decimal_places=2);attributes:dict=Field(default_factory=dict);owned_by_user:bool=False;confirmed_valuation:Decimal|None=Field(default=None,gt=0,max_digits=18,decimal_places=2);valuation_confirmed_at:datetime|None=None
    @field_validator("city")
    @classmethod
    def karachi(cls,v):
        if v.strip().lower()!="karachi": raise ValueError("Part 8 supports Karachi only")
        return "Karachi"
    @field_validator("observed_at", "valuation_confirmed_at")
    @classmethod
    def timezone_required(cls,v):
        if v is not None and (v.tzinfo is None or v.utcoffset() is None):
            raise ValueError("timestamp must include a timezone")
        return v
    @model_validator(mode="after")
    def valuation(self):
        if self.confirmed_valuation is not None and (not self.owned_by_user or self.valuation_confirmed_at is None): raise ValueError("confirmed valuation requires owned_by_user and valuation_confirmed_at")
        return self
class PropertyListingResponse(PropertyListingCreate):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID;information_quality:str;created_at:datetime;asking_price_status:Literal["unverified_asking_price"]="unverified_asking_price";confirmed_transaction_price:Literal[False]=False;stale:bool=False;stale_after_days:int=90
class PropertyFilters(BaseModel):
    area_name:str|None=None;property_type:str;purpose:Literal["sale","rent"];area_min:Decimal|None=Field(default=None,gt=0);area_max:Decimal|None=Field(default=None,gt=0);area_unit:AreaUnit;asking_min:Decimal|None=Field(default=None,gt=0);asking_max:Decimal|None=Field(default=None,gt=0)
    @model_validator(mode="after")
    def ordered_ranges(self):
        if self.area_min is not None and self.area_max is not None and self.area_min > self.area_max:
            raise ValueError("area_min cannot exceed area_max")
        if self.asking_min is not None and self.asking_max is not None and self.asking_min > self.asking_max:
            raise ValueError("asking_min cannot exceed asking_max")
        return self
class YieldInput(BaseModel):
    purchase_price:Decimal=Field(gt=0,max_digits=18,decimal_places=2);monthly_rent:Decimal=Field(gt=0,max_digits=18,decimal_places=2);annual_expenses:dict[str,Decimal]|None=None;annual_property_tax:Decimal|None=Field(default=None,ge=0,max_digits=18,decimal_places=2);source_reference:str|None=None
    @field_validator("annual_expenses")
    @classmethod
    def expenses(cls,v):
        if v is not None and any((not x.is_finite()) or x<0 for x in v.values()): raise ValueError("expense assumptions must be finite and nonnegative")
        return v
class AnalysisResponse(BaseModel):
    id:uuid.UUID;domain:str;analysis_type:str;source_evidence:dict;assumptions:dict;calculated_metrics:dict;recommendation:dict|None;limitations:list;analyzer_version:str;calculated_at:datetime|None=None;estimate_only:bool=True;transaction_executed:bool=False
