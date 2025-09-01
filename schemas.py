from pydantic import BaseModel
from datetime import datetime

class UserBase(BaseModel):
    username: str
    password: str
    repeat_password: str

    class Config:
        from_attributes = True

class CreateUser(UserBase):
    pass

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

class DocumentBase(BaseModel):
    id: int
    filename: str

    class Config:
        from_attributes = True
class UpdateDocument(DocumentBase):
    pass

class ListDocument(DocumentBase):
    pass

class ProjectWithDocs(ProjectBase):
    documents: list[DocumentBase] = []
