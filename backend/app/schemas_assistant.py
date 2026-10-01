import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field

class ConversationCreate(BaseModel):title:str|None=Field(default=None,max_length=120)
class ChatRequest(BaseModel):message:str=Field(min_length=1,max_length=4000)
class Citation(BaseModel):source_type:str;record_id:uuid.UUID;date:datetime|None;excerpt:str=Field(max_length=500);record_path:str;freshness:Literal["fresh","aging","stale","undated","estimated","unverified","user_entered"]
class AssistantAnswer(BaseModel):
    model_config=ConfigDict(extra="forbid")
    answer:str=Field(min_length=1,max_length=12000);citations:list[Citation]=Field(max_length=20);evidence_references:list[dict]=Field(max_length=20);freshness:list[str]=Field(max_length=30);limitations:list[str]=Field(min_length=1,max_length=20);mode:Literal["deterministic","llm"]
class MessageResponse(BaseModel):id:uuid.UUID;role:Literal["user","assistant"];content:str;created_at:datetime;response:AssistantAnswer|None=None
class ConversationResponse(BaseModel):id:uuid.UUID;title:str;created_at:datetime;updated_at:datetime;messages:list[MessageResponse]=Field(default_factory=list)
class FeedbackCreate(BaseModel):category:Literal["incorrect_citation","unsupported_claim","stale_or_missing","calculation_error","other"]
class MetricsResponse(BaseModel):total_requests:int;successful:int;refused:int;abstained:int;failed:int;fallbacks:int;average_latency_ms:float;total_citations:int;provider_modes:dict[str,int]
