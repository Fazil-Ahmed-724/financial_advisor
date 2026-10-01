import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator

EventType=Literal["reminder_due","assistant_response_ready","feedback_review_status_changed"]
Platform=Literal["android","ios"]

class DeviceRegister(BaseModel):
    installation_id:uuid.UUID;platform:Platform;display_name:str=Field(min_length=1,max_length=80);expo_push_token:str|None=Field(default=None,max_length=300);notifications_enabled:bool=False
    @field_validator("display_name")
    @classmethod
    def clean_name(cls,v):return " ".join(v.split())
    @field_validator("expo_push_token")
    @classmethod
    def token_shape(cls,v):
        if v is not None and not (v.startswith("ExponentPushToken[") or v.startswith("ExpoPushToken[")):raise ValueError("Invalid Expo push token")
        return v
class DeviceUpdate(BaseModel):notifications_enabled:bool
class PreferenceUpdate(BaseModel):event_type:EventType;enabled:bool;device_id:uuid.UUID|None=None
class DeviceResponse(BaseModel):
    id:uuid.UUID;installation_id:uuid.UUID;platform:str;display_name:str;push_status:str;notifications_enabled:bool;last_seen_at:datetime;revoked_at:datetime|None;preferences:dict[str,bool]
class PreferenceResponse(BaseModel):event_type:str;enabled:bool;device_id:uuid.UUID|None=None
class ReminderCreate(BaseModel):
    dedupe_key:str=Field(min_length=1,max_length=120);deep_link:Literal["/","/decisions","/assistant","/assistant-feedback"]="/"
    @field_validator("dedupe_key")
    @classmethod
    def clean_key(cls,v):return " ".join(v.split())
class DeliveryResponse(BaseModel):
    id:uuid.UUID;event_id:uuid.UUID;device_id:uuid.UUID;event_type:str;status:str;attempt_count:int;last_error_code:str|None;created_at:datetime;updated_at:datetime;acknowledged_at:datetime|None;provider_acceptance_is_device_display:bool=False
