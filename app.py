from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from schemas import UserCreate
from services import *
from auth import *

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

@app.post("/login")
async def login(user: LoginUser):
    try:
        return await login_user(user)

    except HTTPException as e:
        raise e

@app.post("/unique_email")
async def check_unique_email(email: Email):
    try:
        return await unique_email(email.email)
    except HTTPException as e:
        raise e

@app.get("/verify_token")
async def verify_token_route(email: str = Depends(get_current_user)):
    return {"email": email, "message": "Token is valid"}

@app.get("/user/me", response_model=User)
async def get_current_user_data(current_user_email: str = Depends(get_current_user)):
    try:
        return await current_user_data(current_user_email)
    except HTTPException as e:
        raise e

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
