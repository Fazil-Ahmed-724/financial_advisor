import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class BookUpdate(BaseModel):
    title:str=Field(min_length=1,max_length=500); author:str=Field(min_length=1,max_length=300)
    edition:str|None=Field(default=None,max_length=100); publication_year:int|None=Field(default=None,ge=1000,le=2100)
    topic:str=Field(min_length=1,max_length=200); source:str=Field(min_length=1,max_length=500); language:str=Field(default="en",min_length=2,max_length=20)
class BookResponse(BookUpdate):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID; original_filename:str; media_type:str; file_size:int; checksum_sha256:str; extraction_version:int; ingestion_status:str; status_detail:str|None; created_at:datetime; updated_at:datetime
class PassageResponse(BaseModel):
    id:uuid.UUID; book_id:uuid.UUID; book_title:str; author:str; reference_type:str; reference_label:str; excerpt:str; extraction_version:int; learning_support:bool=True; market_data:bool=False; buy_sell_instruction:bool=False
class AttachPassage(BaseModel): note:str|None=Field(default=None,max_length=1000)
