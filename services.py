from supabase_client import get_supabase_client
from schemas import *
from fastapi import HTTPException
from auth import *
from datetime import timezone, datetime
import os
from dotenv import load_dotenv

load_dotenv()
SUPABASE_STORAGE_URL = os.getenv("SUPABASE_STORAGE_URL")
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


async def current_user_data(email: str) -> dict:
    response = (
        supabase.table("users")
        .select("first_name", "last_name", "birth_date", "gender", "bio", "location", "profile_picture_url")
        .eq("email", email)
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=404, detail="User not found")

    return response.data[0]

async def current_user_data_update(first_name, last_name, birth_date, gender,
                                              bio, location, file, current_user_email):
        request_body = {
            "first_name": first_name,
            "last_name": last_name,
            "birth_date": birth_date,
            "gender": gender,
            "bio": bio,
            "location": location,
        }

        if file is not None:
            request_body["profile_picture_url"] = await upload_image(file, current_user_email)

        request_body = {k: v for k, v in request_body.items() if v is not None}

        response = (
            supabase.table("users")
            .update(request_body)
            .eq("email", current_user_email)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=400, detail="User update failed")

        return {"code": 200, "message": "User updated successfully"}


async def upload_image(file, current_user_email):
    try:
        file_ext = file.filename.split(".")[-1]
        current_time = datetime.now(timezone.utc)
        file_name = f"public/{current_user_email}_{current_time.timestamp()}.{file_ext}"

        file_content = await file.read()

        upload_response = supabase.storage.from_("SpotyDate").upload(file_name, file_content)

        return SUPABASE_STORAGE_URL + upload_response.full_path
    except Exception as e:
        raise e