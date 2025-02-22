import hashlib
from operator import truediv

from supabase_client import get_supabase_client
from schemas import *

supabase = get_supabase_client()

def hash_password(password: str) -> str:
    """Hash a password using SHA256."""
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

    print(response)
    return {"message": "User registered successfully"}


async def unique_email(email:Email):
    response = (
        supabase.table("users")
        .select("*")
        .eq("email", email.email)
        .execute()
    )

    if len(response.data) == 0:
        return True
    else:
        return False