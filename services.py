import hashlib
from supabase_client import get_supabase_client
from schemas import *

supabase = get_supabase_client()

def hash_password(password: str) -> str :
    return hashlib.sha256(password.encode()).hexdigest()

async def register_user(user: UserCreate):
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

    return {"message": "User registered successfully"}


async def unique_email(email: str) -> bool:
    response = (
        supabase.table("users")
        .select("*")
        .eq("email", email)
        .execute()
    )

    return len(response.data) == 0