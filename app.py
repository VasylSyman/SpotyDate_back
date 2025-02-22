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
        if not await unique_email(user.email):
            raise HTTPException(status_code=400, detail="Email already in use")

        return await register_user(user)

    except HTTPException as e:
        raise e

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
