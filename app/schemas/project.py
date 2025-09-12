from pydantic import BaseModel
from datetime import datetime
from .document import DocumentBase

class ProjectBase(BaseModel):
    name: str
    description: str

    class Config:
        from_attributes = True

class CreateProject(ProjectBase):
    pass

class UpdateProject(ProjectBase):
    pass

class ListProject(ProjectBase):
    pass

class ProjectWithDocs(ProjectBase):
    documents: list[DocumentBase] = []