import uuid
from datetime import date,datetime
from typing import Literal
from pydantic import BaseModel,Field,field_validator
class RowAction(BaseModel):action:Literal["import","skip","replace_existing"]
class AnalysisRequest(BaseModel):
    symbols:list[str]=Field(min_length=1,max_length=10);lookback:int=Field(default=14,ge=2,le=252);start_date:date|None=None;end_date:date|None=None;as_of_date:date|None=None
    @field_validator("symbols")
    @classmethod
    def symbols_valid(cls,v):return list(dict.fromkeys(x.strip().upper() for x in v))
class ImportResponse(BaseModel):
    id:uuid.UUID;status:str;source_name:str;original_filename:str;total_rows:int;valid_rows:int;invalid_rows:int;warning_rows:int;committed_rows:int;created_at:datetime
