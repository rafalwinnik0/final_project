from pydantic import BaseModel
from datetime import datetime

class DocumentBase(BaseModel):
    id: int
    filename: str

    class Config:
        from_attributes = True
class UpdateDocument(DocumentBase):
    pass

class ListDocument(DocumentBase):
    pass