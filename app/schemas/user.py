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