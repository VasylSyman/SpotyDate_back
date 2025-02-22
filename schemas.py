from pydantic import BaseModel
from datetime import date
from typing import Optional

class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    surname: str
    date_of_birth: str

class LoginUser(BaseModel):
    email: str
    password: str

class User(BaseModel):
    first_name: str
    last_name: str
    birth_date: date
    gender: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    profile_picture_url: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class Email(BaseModel):
    email:str