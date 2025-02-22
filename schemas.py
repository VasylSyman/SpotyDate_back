from pydantic import BaseModel

class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    surname: str
    date_of_birth: str

class Token(BaseModel):
    access_token: str
    token_type: str

class Email(BaseModel):
    email:str