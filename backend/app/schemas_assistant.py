import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator

class ConversationCreate(BaseModel):title:str|None=Field(default=None,max_length=120)
class ChatRequest(BaseModel):message:str=Field(min_length=1,max_length=4000)
class Citation(BaseModel):source_type:str;record_id:uuid.UUID;date:datetime|None;excerpt:str=Field(max_length=500);record_path:str;freshness:Literal["fresh","aging","stale","undated","estimated","unverified","user_entered"]
class AssistantAnswer(BaseModel):
    model_config=ConfigDict(extra="forbid")
    answer:str=Field(min_length=1,max_length=12000);citations:list[Citation]=Field(max_length=20);evidence_references:list[dict]=Field(max_length=20);freshness:list[str]=Field(max_length=30);limitations:list[str]=Field(min_length=1,max_length=20);mode:Literal["deterministic","llm"]
class MessageResponse(BaseModel):id:uuid.UUID;role:Literal["user","assistant"];content:str;created_at:datetime;response:AssistantAnswer|None=None
class ConversationResponse(BaseModel):id:uuid.UUID;title:str;created_at:datetime;updated_at:datetime;messages:list[MessageResponse]=Field(default_factory=list)
FeedbackCategory=Literal["helpful","inaccurate","unsupported","stale","confusing","missing_evidence"]
FeedbackStatus=Literal["submitted","reviewed","dismissed"]
_LEGACY_FEEDBACK={"incorrect_citation":"inaccurate","unsupported_claim":"unsupported","stale_or_missing":"stale","calculation_error":"inaccurate","other":"confusing"}
class FeedbackCreate(BaseModel):
    category:FeedbackCategory
    comment:str|None=Field(default=None,max_length=500)
    @field_validator("category",mode="before")
    @classmethod
    def legacy_category(cls,value):return _LEGACY_FEEDBACK.get(value,value)
    @field_validator("comment")
    @classmethod
    def clean_comment(cls,value):return (" ".join(value.split()) or None) if value is not None else None
class FeedbackUpdate(BaseModel):
    category:FeedbackCategory|None=None
    comment:str|None=Field(default=None,max_length=500)
    status:FeedbackStatus|None=None
    review_note:str|None=Field(default=None,max_length=500)
    fixture_selected:bool|None=None
    @field_validator("comment","review_note")
    @classmethod
    def clean_text(cls,value):return (" ".join(value.split()) or None) if value is not None else None
    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:raise ValueError("At least one feedback field is required")
        return self
class FeedbackResponse(BaseModel):
    id:uuid.UUID;message_id:uuid.UUID;category:FeedbackCategory;comment:str|None;status:FeedbackStatus;review_note:str|None;fixture_selected:bool;response_mode:Literal["deterministic","llm","unknown"];citation_ids:list[uuid.UUID];source_dates:list[datetime];freshness:list[str];evaluation_metadata:dict;created_at:datetime;updated_at:datetime;financial_action:Literal[False]=False
class FeedbackExportRequest(BaseModel):
    feedback_ids:list[uuid.UUID]=Field(min_length=1,max_length=50)
    confirm_sanitized_export:Literal[True]
    @field_validator("feedback_ids")
    @classmethod
    def unique_ids(cls,value):
        if len(value)!=len(set(value)):raise ValueError("feedback_ids must be unique")
        return value
class MetricsResponse(BaseModel):total_requests:int;successful:int;refused:int;abstained:int;failed:int;fallbacks:int;average_latency_ms:float;total_citations:int;provider_modes:dict[str,int]
