# main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import jwt
from datetime import datetime, timedelta
import os
from fastapi.security import OAuth2PasswordBearer

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Secret key for JWT
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"

# Mock database
users_db = {}
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class UserCreate(BaseModel):
    email: str
    password: str


class User(BaseModel):
    email: str
    music_preferences: Optional[dict] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class UserLogin(BaseModel):
    email: str
    password: str


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return email


@app.post("/register", response_model=Token)
async def register(user: UserCreate):
    if user.email in users_db:
        raise HTTPException(status_code=400, detail="Email already registered")

    # In a real app, hash the password before storing
    users_db[user.email] = {
        "password": user.password,
        "music_preferences": {
            "favorite_genres": ["pop", "rock"],
            "monthly_listening": "45 hours",
            "top_artists": [
                {"name": "Tame Impala", "plays": 120},
                {"name": "The Strokes", "plays": 98}
            ]
        }
    }

    access_token = create_access_token({"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/login", response_model=Token)
async def login(user: UserLogin):
    if user.email not in users_db or users_db[user.email]["password"] != user.password:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token({"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/profile", response_model=User)
async def get_profile(current_user: str = Depends(get_current_user)):
    return {
        "email": current_user,
        "music_preferences": users_db[current_user]["music_preferences"]
    }


@app.get("/matches")
async def get_matches(current_user: str = Depends(get_current_user)):
    # Mock matches data
    return [
        {
            "name": "Sarah",
            "age": 25,
            "matchPercentage": 90,
            "topArtist": "The Weeknd",
            "genres": ["Pop", "R&B", "Hip-Hop"]
        },
        {
            "name": "Mike",
            "age": 28,
            "matchPercentage": 85,
            "topArtist": "Arctic Monkeys",
            "genres": ["Indie", "Rock", "Alternative"]
        }
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)