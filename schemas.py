from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List

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

class SpotifyToken(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: str
    scope: str

class SpotifyProfile(BaseModel):
    spotify_id: str
    display_name: Optional[str]
    connected_at: datetime

class SpotifyCallbackRequest(BaseModel):
    code: str

class ArtistBasicInfo(BaseModel):
    id: str
    name: str

class TrackBasicInfo(BaseModel):
    id: str
    name: str

class GenreList(BaseModel):
    genres: List[str]