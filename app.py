from enum import unique

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from schemas import UserCreate
from services import *

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/register")
async def register(user: UserCreate):
    try:
        return await register_user(user)
    except HTTPException as e:
        raise e

@app.post("/unique_email")
async def check_unique_email(email: Email):
    try:
        return await unique_email(email)
    except HTTPException as e:
        raise e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
