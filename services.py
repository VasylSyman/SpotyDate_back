from supabase_client import get_supabase_client
from schemas import *
from fastapi import HTTPException
from auth import *
from datetime import timezone, datetime
import os
from dotenv import load_dotenv
import spotipy

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
    user_response = (
        supabase.table("users")
        .select("user_id", "first_name", "last_name", "birth_date", "gender", "bio", "location", "profile_picture_url")
        .eq("email", email)
        .maybe_single()
        .execute()
    )

    if not user_response.data:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = user_response.data
    user_id = user_data.get("user_id")

    genre_response = (
        supabase.table("user_genres")
        .select("genres(name)")
        .eq("user_id", user_id)
        .execute()
    )

    genres = [
        item["genres"]["name"]
        for item in genre_response.data
        if item.get("genres") and item["genres"].get("name")
    ] if genre_response.data else []

    user_data["genres"] = genres

    user_data.pop("user_id", None)

    return user_data

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
        if track_id and track_name:
            tracks_to_insert.append({"track_id": track_id, "name": track_name})
            valid_track_ids.add(track_id)

    response_tracks = supabase.table("tracks").upsert(
        tracks_to_insert,
        ignore_duplicates=True,
        on_conflict='track_id'
    ).execute()

    user_tracks_to_insert = []
    for track_id in valid_track_ids:
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
    for artist_id in valid_artist_ids:
        user_artists_to_insert.append({"user_id": user_id, "artist_id": artist_id})

    response_user_artists = supabase.table("user_artists").upsert(
        user_artists_to_insert,
        ignore_duplicates=True,
    ).execute()


async def genres_upload(input_genres: List[str], current_user_email: str):
    user_response = supabase.table("users").select("user_id").eq("email", current_user_email).maybe_single().execute()
    user_id = user_response.data.get("user_id")

    genres_to_upsert = [{"name": genre} for genre in input_genres if genre]

    if genres_to_upsert:
        supabase.table("genres").upsert(
            genres_to_upsert,
            on_conflict='name'
        ).execute()

    genre_name_to_id_map = {}
    if input_genres:
        response_fetch_genres = supabase.table("genres").select("genre_id", "name").in_("name", input_genres).execute()
        genre_name_to_id_map = {genre["name"]: genre["genre_id"] for genre in response_fetch_genres.data}

    user_genres_to_insert = []
    for genre_name in input_genres:
        genre_id = genre_name_to_id_map.get(genre_name)
        if user_id and genre_id:
            user_genres_to_insert.append({"user_id": user_id, "genre_id": genre_id})

    if user_genres_to_insert:
        supabase.table("user_genres").upsert(
            user_genres_to_insert,
        ).execute()


async def fetch_and_process_top_artists(spotify, current_user_email):
    top_artists_data = spotify.current_user_top_artists(
        limit=50,
        time_range='medium_term'
    )
    parsed_artists = []
    if top_artists_data and 'items' in top_artists_data:
        for artist_item in top_artists_data['items']:
            if isinstance(artist_item, dict) and 'id' in artist_item and 'name' in artist_item:
                parsed_artists.append(
                    ArtistBasicInfo(id=artist_item['id'], name=artist_item['name'])
                )

    await artists_upload(parsed_artists, current_user_email)


async def fetch_and_process_top_tracks(spotify, current_user_email):
    top_tracks_data = spotify.current_user_top_tracks(
        limit=50,
        time_range='medium_term'
    )

    parsed_tracks = []
    if top_tracks_data and 'items' in top_tracks_data:
        for track_item in top_tracks_data['items']:
            if isinstance(track_item, dict) and 'id' in track_item and 'name' in track_item:
                parsed_tracks.append(
                    TrackBasicInfo(id=track_item['id'], name=track_item['name'])
                )

    await tracks_upload(parsed_tracks, current_user_email)


async def fetch_and_process_genres(spotify, current_user_email):
    all_genres = set()
    all_artist_ids = set()
    top_limit = 50
    time_range = "medium_term"


    # --- 1. Process Saved Tracks ---
    saved_tracks_data = spotify.current_user_saved_tracks(limit=top_limit)
    if saved_tracks_data and 'items' in saved_tracks_data:
        for item in saved_tracks_data.get('items', []):
            track = item.get('track')
            if track and track.get('artists'):
                for artist in track['artists']:
                    if artist and artist.get('id'):
                        all_artist_ids.add(artist['id'])


    # --- 2. Process Top Tracks ---
    top_tracks_data = spotify.current_user_top_tracks(limit=top_limit, time_range=time_range)
    if top_tracks_data and 'items' in top_tracks_data:
        for track in top_tracks_data.get('items', []):
            if track and track.get('artists'):
                for artist in track['artists']:
                    if artist and artist.get('id'):
                        all_artist_ids.add(artist['id'])

    # --- 3. Process Top Artists (Direct Genre Addition + ID Collection) ---
    top_artists_data = spotify.current_user_top_artists(limit=top_limit, time_range=time_range)
    if top_artists_data and 'items' in top_artists_data:
        for artist in top_artists_data.get('items', []):
            if artist:
                artist_id = artist.get('id')
                artist_genres = artist.get('genres')
                if artist_id:
                    all_artist_ids.add(artist_id)
                if artist_genres:
                    all_genres.update(artist_genres)

    # --- 4. Fetch Details for All Collected Artist IDs ---
    if all_artist_ids:
        artist_ids_list = list(all_artist_ids)
        batch_size = 50
        for i in range(0, len(artist_ids_list), batch_size):
            batch_ids = artist_ids_list[i:i + batch_size]
            artists_details = spotify.artists(batch_ids)
            if artists_details and artists_details.get('artists'):
                for artist in artists_details['artists']:
                    if artist and artist.get('genres'):
                        all_genres.update(artist['genres'])


    # --- 5. Return Final Sorted List ---
    sorted_genres = sorted(list(all_genres))
    await genres_upload(sorted_genres, current_user_email)

    return sorted_genres

