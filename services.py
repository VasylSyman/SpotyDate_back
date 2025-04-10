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


async def tracks_upload(input_tracks, current_user_email):
    user_response = supabase.table("users").select("user_id").eq("email", current_user_email).maybe_single().execute()
    user_id = user_response.data.get("user_id")

    tracks_to_insert = []
    valid_track_ids = set()
    for track in input_tracks:
        track_id = track.id
        track_name = track.name
        if track_id and track_name:  # Basic validation
            tracks_to_insert.append({"track_id": track_id, "name": track_name})
            valid_track_ids.add(track_id)

    response_tracks = supabase.table("tracks").upsert(
        tracks_to_insert,
        ignore_duplicates=True,
        on_conflict='track_id'
    ).execute()

    user_tracks_to_insert = []
    for track_id in valid_track_ids:  # Use only the valid IDs prepared earlier
        user_tracks_to_insert.append({"user_id": user_id, "track_id": track_id})

    response_user_tracks = supabase.table("user_tracks").upsert(
        user_tracks_to_insert,
        ignore_duplicates=True,
    ).execute()



async def artists_upload(input_artists, current_user_email):
    user_response = supabase.table("users").select("user_id").eq("email", current_user_email).maybe_single().execute()
    user_id = user_response.data.get("user_id")

    artists_to_insert = []
    valid_artist_ids = set()
    for artist in input_artists:
        artist_id = artist.id
        artist_name = artist.name
        if artist_id and artist_name:
            artists_to_insert.append({"artist_id": artist_id, "name": artist_name})
            valid_artist_ids.add(artist_id)

    response_artists = supabase.table("artists").upsert(
        artists_to_insert,
        ignore_duplicates=True,
        on_conflict='artist_id'
    ).execute()


    user_artists_to_insert = []
    for artist_id in valid_artist_ids:  # Use only the valid IDs prepared earlier
        user_artists_to_insert.append({"user_id": user_id, "artist_id": artist_id})

    response_user_artists = supabase.table("user_artists").upsert(
        user_artists_to_insert,
        ignore_duplicates=True,
    ).execute()


async def genres_upload(input_genres: List[str], current_user_email: str):
    # 1. Get User ID
    user_response = supabase.table("users").select("user_id").eq("email", current_user_email).maybe_single().execute()
    # Assume user_response.data is not None and contains 'user_id'
    user_id = user_response.data.get("user_id")

    # 2. Prepare genre data for upsert
    genres_to_upsert = [{"name": genre} for genre in input_genres if genre] # Ensure genre is not empty

    # 3. Upsert genres into the 'genres' table
    # This ensures all genres exist. Handles conflicts based on the 'name' column.
    if genres_to_upsert: # Avoid running upsert with empty list
        supabase.table("genres").upsert(
            genres_to_upsert,
            on_conflict='name' # Assumes 'name' has a unique constraint
        ).execute()
        # Ignore response/error as requested

    # 4. Fetch IDs for all relevant genres (now that they exist)
    # Fetch only if there were input genres to avoid empty 'in_' clause error
    genre_name_to_id_map = {}
    if input_genres:
        response_fetch_genres = supabase.table("genres").select("genre_id", "name").in_("name", input_genres).execute()
        # Assume response_fetch_genres.data is a list of dicts
        genre_name_to_id_map = {genre["name"]: genre["genre_id"] for genre in response_fetch_genres.data}

    # 5. Prepare user-genre links
    user_genres_to_insert = []
    for genre_name in input_genres: # Iterate through the input strings
        # Use the string directly to look up in the map
        genre_id = genre_name_to_id_map.get(genre_name)
        if user_id and genre_id: # Ensure both IDs are valid
            user_genres_to_insert.append({"user_id": user_id, "genre_id": genre_id})

    # 6. Insert user-genre links
    # Use upsert or insert based on whether you want to ignore existing links
    # Assuming user_id, genre_id is the primary/unique key for user_genres
    if user_genres_to_insert:
        supabase.table("user_genres").upsert(
            user_genres_to_insert,
            # on_conflict='user_id, genre_id' # More explicit if constraint exists
            # ignore_duplicates=True # Alternative if you just want to skip existing pairs
        ).execute() # Using upsert as per user's last version, might need on_conflict based on schema
        # Ignore response/error as requested

