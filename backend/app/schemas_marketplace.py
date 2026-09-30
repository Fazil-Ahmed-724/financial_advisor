import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Platform=Literal["Daraz","Temu","SHEIN","Other"]
SourceMethod=Literal["user_entered","authorized_export","permitted_api"]

class MarketplaceListingCreate(BaseModel):
    source_method:SourceMethod="user_entered";source_platform:Platform;product_name:str=Field(min_length=1,max_length=300);sku:str|None=Field(default=None,max_length=100);source_listing_id:str|None=Field(default=None,max_length=200);canonical_url:str|None=Field(default=None,max_length=1000);observed_at:datetime;currency:str=Field(min_length=3,max_length=3);source_price:Decimal=Field(gt=0,max_digits=18,decimal_places=4);attributes:dict=Field(default_factory=dict);evidence:dict=Field(default_factory=dict);expected_karachi_selling_price:Decimal|None=Field(default=None,gt=0,max_digits=18,decimal_places=2);local_sales_channel:str|None=Field(default=None,max_length=100);confirmed_inventory_value:Decimal|None=Field(default=None,ge=0,max_digits=18,decimal_places=2);inventory_valued_at:datetime|None=None
    @field_validator("observed_at","inventory_valued_at")
    @classmethod
    def timezone_required(cls,v):
        if v is not None and (v.tzinfo is None or v.utcoffset() is None):raise ValueError("timestamp must include a timezone")
        return v
    @field_validator("currency")
    @classmethod
    def currency_code(cls,v):return v.upper()
    @model_validator(mode="after")
    def valuation_pair(self):
        if (self.confirmed_inventory_value is None)!=(self.inventory_valued_at is None):raise ValueError("confirmed inventory value and valuation timestamp must be supplied together")
        return self

class MarketplaceListingResponse(MarketplaceListingCreate):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID;information_quality:str;created_at:datetime;stale:bool=False;stale_after_days:int=60;source_data_status:Literal["user_or_authorized_unverified"]="user_or_authorized_unverified";purchase_executed:Literal[False]=False;marketplace_listing_created:Literal[False]=False

class ResaleAnalysisInput(BaseModel):
    listing_id:uuid.UUID;quantity:Decimal=Field(gt=0,max_digits=18,decimal_places=4);expected_selling_price_pkr:Decimal|None=Field(default=None,gt=0,max_digits=18,decimal_places=2);exchange_rate_to_pkr:Decimal|None=Field(default=None,gt=0,max_digits=18,decimal_places=6);exchange_rate_observed_at:datetime|None=None;exchange_rate_source:str|None=Field(default=None,max_length=500);shipping_per_unit:Decimal|None=Field(default=None,ge=0);customs_per_unit:Decimal|None=Field(default=None,ge=0);conversion_fee_per_unit:Decimal|None=Field(default=None,ge=0);marketplace_fee_per_unit:Decimal|None=Field(default=None,ge=0);payment_fee_per_unit:Decimal|None=Field(default=None,ge=0);packaging_per_unit:Decimal|None=Field(default=None,ge=0);delivery_per_unit:Decimal|None=Field(default=None,ge=0);other_costs_per_unit:Decimal|None=Field(default=None,ge=0);returns_allowance_per_unit:Decimal|None=Field(default=None,ge=0);damage_allowance_per_unit:Decimal|None=Field(default=None,ge=0);unsold_allowance_per_unit:Decimal|None=Field(default=None,ge=0)
    @field_validator("exchange_rate_observed_at")
    @classmethod
    def rate_timezone(cls,v):
        if v is not None and (v.tzinfo is None or v.utcoffset() is None):raise ValueError("exchange-rate date must include a timezone")
        return v

class MarketplaceOutcomeCreate(BaseModel):
    analysis_id:uuid.UUID;recorded_at:datetime;purchased_quantity:Decimal=Field(ge=0,decimal_places=4);actual_purchase_cost:Decimal=Field(ge=0,decimal_places=2);actual_other_costs:Decimal=Field(ge=0,decimal_places=2);sold_quantity:Decimal=Field(ge=0,decimal_places=4);actual_sales_revenue:Decimal=Field(ge=0,decimal_places=2);actual_sales_fees:Decimal=Field(ge=0,decimal_places=2);returned_quantity:Decimal=Field(ge=0,decimal_places=4);return_costs:Decimal=Field(ge=0,decimal_places=2);remaining_quantity:Decimal=Field(ge=0,decimal_places=4);notes:str|None=Field(default=None,max_length=2000)
    @field_validator("recorded_at")
    @classmethod
    def outcome_timezone(cls,v):
        if v.tzinfo is None or v.utcoffset() is None:raise ValueError("recorded_at must include a timezone")
        return v
    @model_validator(mode="after")
    def quantities(self):
        if self.sold_quantity+self.returned_quantity+self.remaining_quantity>self.purchased_quantity:raise ValueError("sold, returned, and remaining quantity cannot exceed purchased quantity")
        return self

class MarketplaceOutcomeResponse(MarketplaceOutcomeCreate):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID;actual_net_result:Decimal;forecast_error:Decimal|None;assumption_differences:dict;created_at:datetime;external_transactions_only:Literal[True]=True;success_label:Literal["not_assigned"]="not_assigned"
