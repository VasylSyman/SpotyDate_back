from supabase_client import get_supabase_client
from schemas import *
from fastapi import HTTPException
from auth import *
from datetime import timedelta


supabase = get_supabase_client()

async def register_user(user: UserCreate):
    if not await unique_email(user.email):
        raise HTTPException(status_code=400, detail="Email is already in use")

    hashed_password = hash_password(user.password)

    request_body = {
        "email": user.email,
        "password_hash": hashed_password,
        "first_name": user.name,
        "last_name": user.surname,
        "birth_date": user.date_of_birth,
    }

    response = (
        supabase.table("users")
        .insert(request_body)
        .execute()
    )

    if response.error:
        raise HTTPException(status_code=500, detail="Database error")

    access_token = create_access_token(data={"sub": user.email}, expires_delta=30)
    return {"access_token": access_token, "token_type": "bearer"}


async def login_user(user: LoginUser):
    response = (
        supabase.table("users")
        .select("*")
        .eq("email", user.email)
        .execute()
    )

    if not response.data or not verify_password(user.password, response.data[0]["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(data={"sub": user.email}, expires_delta=30)
    return {"access_token": access_token, "token_type": "bearer"}


async def unique_email(email: str) -> bool:
    response = (
        supabase.table("users")
        .select("*")
        .eq("email", email)
        .execute()
    )

    return len(response.data) == 0