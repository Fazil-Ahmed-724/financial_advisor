import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
SourceType=Literal["user_entered","authorized_export","permitted_api"]
Platform=Literal["Daraz","Temu","SHEIN","Other"]
def aware(v):
    if v.tzinfo is None or v.utcoffset() is None:raise ValueError("timestamp must include a timezone")
    return v
class ProductCreate(BaseModel):
    normalized_name:str=Field(min_length=1,max_length=300);brand:str|None=Field(default=None,max_length=100);model:str|None=Field(default=None,max_length=100);category:str|None=Field(default=None,max_length=100);canonical_attributes:dict=Field(default_factory=dict)
class ProductResponse(ProductCreate):
    model_config=ConfigDict(from_attributes=True);id:uuid.UUID;match_status:Literal["exact_match","probable_match","unmatched"]="unmatched";match_candidates:list[uuid.UUID]=Field(default_factory=list);created_at:datetime;updated_at:datetime
class ObservationCreate(BaseModel):
    marketplace:Platform;source_type:SourceType;source_reference:str=Field(min_length=1,max_length=500);source_url:str|None=Field(default=None,max_length=1000);observed_name:str=Field(min_length=1,max_length=300);observed_price:Decimal=Field(gt=0,max_digits=18,decimal_places=4);currency_code:str=Field(min_length=3,max_length=3);observed_at:datetime;seller_name:str|None=None;seller_location:str|None=None;rating:Decimal|None=Field(default=None,ge=0,le=5);rating_count:int|None=Field(default=None,ge=0);review_count:int|None=Field(default=None,ge=0);sold_count:int|None=Field(default=None,ge=0);listing_age_days:int|None=Field(default=None,ge=0);raw_attributes:dict=Field(default_factory=dict);evidence:dict=Field(default_factory=dict)
    _aware=field_validator("observed_at")(aware)
    @field_validator("currency_code")
    @classmethod
    def currency(cls,v):return v.upper()
class ObservationResponse(ObservationCreate):
    model_config=ConfigDict(from_attributes=True);id:uuid.UUID;product_id:uuid.UUID;created_at:datetime;stale:bool=False;freshness_status:Literal["fresh","aging","stale"]="fresh";age_days:int=0;threshold_days:dict=Field(default_factory=dict);price_change_percent:Decimal|None=None
class SourcingCreate(BaseModel):
    source_type:SourceType;supplier_name:str|None=None;source_channel:Literal["local_wholesaler","distributor","importer","retail_market","online_local","other"];source_reference:str|None=None;unit_cost:Decimal=Field(gt=0,decimal_places=2);currency_code:Literal["PKR"]="PKR";minimum_order_quantity:Decimal|None=Field(default=None,gt=0);local_transport_cost:Decimal|None=Field(default=None,ge=0);packaging_cost:Decimal|None=Field(default=None,ge=0);lead_time_days:int|None=Field(default=None,ge=0);stock_available:bool|None=None;observed_at:datetime;evidence:dict=Field(default_factory=dict)
    _aware=field_validator("observed_at")(aware)
class SourcingResponse(SourcingCreate):
    model_config=ConfigDict(from_attributes=True);id:uuid.UUID;product_id:uuid.UUID;market_location_id:uuid.UUID;created_at:datetime;updated_at:datetime;stale:bool=False;freshness_status:Literal["fresh","aging","stale"]="fresh";age_days:int=0;threshold_days:dict=Field(default_factory=dict)
class CompetitionCreate(BaseModel):
    source_type:SourceType;source_reference:str=Field(min_length=1,max_length=500);comparable_listing_count:int|None=Field(default=None,ge=0);seller_count:int|None=Field(default=None,ge=0);lowest_price:Decimal|None=Field(default=None,ge=0);median_price:Decimal|None=Field(default=None,ge=0);highest_price:Decimal|None=Field(default=None,ge=0);price_dispersion:Decimal|None=Field(default=None,ge=0);observed_at:datetime;evidence:dict=Field(default_factory=dict)
    _aware=field_validator("observed_at")(aware)
    @model_validator(mode="after")
    def prices(self):
        values=[x for x in (self.lowest_price,self.median_price,self.highest_price) if x is not None]
        if len(values)==3 and not self.lowest_price<=self.median_price<=self.highest_price:raise ValueError("competition prices must be ordered")
        return self
class RankingCreate(BaseModel):marketplace_analysis_id:uuid.UUID|None=None
class WatchlistCreate(BaseModel):product_id:uuid.UUID;notes:str|None=Field(default=None,max_length=1000)
class WatchlistUpdate(BaseModel):notes:str|None=Field(default=None,max_length=1000);is_active:bool=True
class CompareRequest(BaseModel):product_ids:list[uuid.UUID]=Field(min_length=2,max_length=4)
class MergeRequest(BaseModel):source_product_id:uuid.UUID;target_product_id:uuid.UUID;reason:str|None=Field(default=None,max_length=1000)
class SplitRequest(BaseModel):new_product:ProductCreate;observation_ids:list[uuid.UUID]=Field(min_length=1);sourcing_ids:list[uuid.UUID]=Field(default_factory=list);competition_ids:list[uuid.UUID]=Field(default_factory=list);reason:str|None=Field(default=None,max_length=1000)
class ImportMapping(BaseModel):mapping:dict[str,str]
class ImportRowUpdate(BaseModel):action:Literal["create_product","attach_to_existing_product","skip","requires_review"];proposed_product_id:uuid.UUID|None=None
class PresetPayload(BaseModel):
    name:str=Field(min_length=1,max_length=100);filters:dict=Field(default_factory=dict);sorting:dict=Field(default_factory=lambda:{"field":"research_score","direction":"desc"});is_default:bool=False
class BatchRankingRequest(BaseModel):product_ids:list[uuid.UUID]=Field(min_length=1)
