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

    #user_data.pop("user_id", None)

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

#--------------------------------------------------------------------------------------------------------------------------------------------

async def find_matches(current_user_email: str):
    user_response = supabase.table("users").select("user_id").eq("email", current_user_email).maybe_single().execute()
    if not user_response.data:
        raise HTTPException(status_code=404, detail="User not found")

    current_user_id = user_response.data.get("user_id")

    current_user_artists = supabase.table("user_artists").select("artist_id").eq("user_id", current_user_id).execute()
    current_user_tracks = supabase.table("user_tracks").select("track_id").eq("user_id", current_user_id).execute()
    current_user_genres = supabase.table("user_genres").select("genre_id").eq("user_id", current_user_id).execute()

    current_artist_ids = [item.get("artist_id") for item in current_user_artists.data]
    current_track_ids = [item.get("track_id") for item in current_user_tracks.data]
    current_genre_ids = [item.get("genre_id") for item in current_user_genres.data]

    all_users = supabase.table("users").select("user_id").neq("user_id", current_user_id).execute()
    potential_matches = []

    for other_user in all_users.data:
        other_user_id = other_user.get("user_id")
        match_score = await calculate_match_score(
            current_user_id, other_user_id,
            current_artist_ids, current_track_ids, current_genre_ids
        )

        if match_score > 10:
            other_user_info = supabase.table("users").select(
                "user_id", "first_name", "last_name", "profile_picture_url"
            ).eq("user_id", other_user_id).maybe_single().execute()

            potential_matches.append({
                "user_id": other_user_id,
                "first_name": other_user_info.data.get("first_name"),
                "last_name": other_user_info.data.get("last_name"),
                "profile_picture_url": other_user_info.data.get("profile_picture_url"),
                "match_score": match_score
            })

    potential_matches.sort(key=lambda x: x["match_score"], reverse=True)

    await store_match_results(current_user_id, potential_matches)

    return potential_matches


async def calculate_match_score(current_user_id: int, other_user_id: int,
                                current_artist_ids: list, current_track_ids: list, current_genre_ids: list) -> float:
    other_user_artists = supabase.table("user_artists").select("artist_id").eq("user_id", other_user_id).execute()
    other_user_tracks = supabase.table("user_tracks").select("track_id").eq("user_id", other_user_id).execute()
    other_user_genres = supabase.table("user_genres").select("genre_id").eq("user_id", other_user_id).execute()

    other_artist_ids = [item.get("artist_id") for item in other_user_artists.data]
    other_track_ids = [item.get("track_id") for item in other_user_tracks.data]
    other_genre_ids = [item.get("genre_id") for item in other_user_genres.data]

    shared_artists = set(current_artist_ids).intersection(set(other_artist_ids))
    shared_tracks = set(current_track_ids).intersection(set(other_track_ids))
    shared_genres = set(current_genre_ids).intersection(set(other_genre_ids))

    artist_match = len(shared_artists) / max(1, min(len(current_artist_ids), len(other_artist_ids)))
    track_match = len(shared_tracks) / max(1, min(len(current_track_ids), len(other_track_ids)))
    genre_match = len(shared_genres) / max(1, min(len(current_genre_ids), len(other_genre_ids)))

    weights = {
        "artist": 0.35,
        "track": 0.25,
        "genre": 0.40
    }

    match_score = (
                          artist_match * weights["artist"] +
                          track_match * weights["track"] +
                          genre_match * weights["genre"]
                  ) * 100

    return round(match_score, 2)


async def store_match_results(user_id: int, matches: list):
    supabase.table("matches").delete().eq("user1_id", user_id).execute()
    supabase.table("matches").delete().eq("user2_id", user_id).execute()

    match_records = []
    timestamp = datetime.now(timezone.utc)

    for match in matches:
        user1, user2 = sorted([user_id, match["user_id"]])

        match_records.append({
            "user1_id": user1,
            "user2_id": user2,
            "match_score": match["match_score"]
        })

    if match_records:
        supabase.table("matches").insert(match_records).execute()

    return True


async def process_spotify_connection(spotify, current_user_email: str):
    matches = await find_matches(current_user_email)

    return {
        "message": "Match finding completed successfully",
        "matches_found": len(matches),
        "top_matches": matches[:10]
    }


async def get_match_details(current_user_id: int, match_user_id: int, match_score: float, match_id: int):
    """
    Optimized version of get_match_details that reduces database queries by batching requests.
    Gets detailed information about a match including personal data and shared musical preferences.
    """
    try:
        # Fetch basic user information
        match_user = supabase.table("users") \
            .select("user_id, first_name, last_name, profile_picture_url, birth_date, gender, bio, location") \
            .eq("user_id", match_user_id) \
            .maybe_single() \
            .execute()

        if not match_user.data:
            return None

        user_data = match_user.data

        # STEP 1: Get all IDs in a single batch for each category

        # Get genre IDs for both users
        current_user_genres = supabase.table("user_genres") \
            .select("genre_id") \
            .eq("user_id", current_user_id) \
            .execute()

        match_user_genres = supabase.table("user_genres") \
            .select("genre_id") \
            .eq("user_id", match_user_id) \
            .execute()

        # Get artist IDs for both users
        current_user_artists = supabase.table("user_artists") \
            .select("artist_id") \
            .eq("user_id", current_user_id) \
            .execute()

        match_user_artists = supabase.table("user_artists") \
            .select("artist_id") \
            .eq("user_id", match_user_id) \
            .execute()

        # Get track IDs for both users
        current_user_tracks = supabase.table("user_tracks") \
            .select("track_id") \
            .eq("user_id", current_user_id) \
            .execute()

        match_user_tracks = supabase.table("user_tracks") \
            .select("track_id") \
            .eq("user_id", match_user_id) \
            .execute()

        # STEP 2: Find intersections for each category
        current_genre_ids = [item.get("genre_id") for item in current_user_genres.data]
        match_genre_ids = [item.get("genre_id") for item in match_user_genres.data]
        shared_genre_ids = list(set(current_genre_ids).intersection(set(match_genre_ids)))

        current_artist_ids = [item.get("artist_id") for item in current_user_artists.data]
        match_artist_ids = [item.get("artist_id") for item in match_user_artists.data]
        shared_artist_ids = list(set(current_artist_ids).intersection(set(match_artist_ids)))

        current_track_ids = [item.get("track_id") for item in current_user_tracks.data]
        match_track_ids = [item.get("track_id") for item in match_user_tracks.data]
        shared_track_ids = list(set(current_track_ids).intersection(set(match_track_ids)))

        # STEP 3: Batch fetch names for each category using "in" filter

        # Get genre names in a single query
        shared_genres = []
        if shared_genre_ids:
            genres_data = supabase.table("genres") \
                .select("genre_id, name") \
                .in_("genre_id", shared_genre_ids) \
                .execute()

            genre_map = {item.get("genre_id"): item.get("name") for item in genres_data.data}
            shared_genres = [genre_map.get(genre_id) for genre_id in shared_genre_ids if genre_id in genre_map]

        # Get artist names in a single query
        shared_artists = []
        if shared_artist_ids:
            artists_data = supabase.table("artists") \
                .select("artist_id, name") \
                .in_("artist_id", shared_artist_ids) \
                .execute()

            artist_map = {item.get("artist_id"): item.get("name") for item in artists_data.data}
            shared_artists = [artist_map.get(artist_id) for artist_id in shared_artist_ids if artist_id in artist_map]

        # Get track names in a single query
        shared_tracks = []
        if shared_track_ids:
            tracks_data = supabase.table("tracks") \
                .select("track_id, name") \
                .in_("track_id", shared_track_ids) \
                .execute()

            track_map = {item.get("track_id"): item.get("name") for item in tracks_data.data}
            shared_tracks = [track_map.get(track_id) for track_id in shared_track_ids if track_id in track_map]

        # Calculate the age from birth_date
        age = None
        if user_data.get("birth_date"):
            from datetime import datetime
            birth_date = datetime.strptime(user_data.get("birth_date"), "%Y-%m-%d").date()
            today = datetime.now().date()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

        # Construct the response
        return {
            "match_id": match_id,
            "user_id": match_user_id,
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name"),
            "profile_picture_url": user_data.get("profile_picture_url"),
            "age": age,
            "birth_date": user_data.get("birth_date"),
            "gender": user_data.get("gender"),
            "bio": user_data.get("bio"),
            "location": user_data.get("location"),
            "match_score": match_score,
            "shared_music": {
                "genres": shared_genres,
                "artists": shared_artists,
                "tracks": shared_tracks,
                "genre_count": len(shared_genres),
                "artist_count": len(shared_artists),
                "track_count": len(shared_tracks)
            }
        }

    except Exception as e:
        print(f"Error getting match details: {str(e)}")
        return None

#----------------------------------------------------------------------------------------------------

async def get_user_id_from_email(email: str) -> int:
    """Helper function to get user_id from email."""
    user_response =  supabase.table("users").select("user_id").eq("email", email).maybe_single().execute()
    if not user_response.data:
        raise HTTPException(status_code=404, detail="User not found")
    return user_response.data["user_id"]


async def get_user_email_from_id(user_id: int) -> str:
    """Helper function to get email from user_id."""
    user_response = supabase.table("users").select("email").eq("user_id", user_id).maybe_single().execute()
    if not user_response.data:
        raise ValueError("User not found")
    return user_response.data["email"]


async def get_match_by_id(match_id: int):
    """Helper to check if a match exists and retrieve its participants."""
    match_response =  supabase.table("matches").select("user1_id, user2_id").eq("match_id",
                                                                                     match_id).maybe_single().execute()
    if not match_response.data:
        return None
    return match_response.data


async def create_chat_message_service(message: MessageCreate, sender_email: str) -> Message:
    sender_id = await get_user_id_from_email(sender_email)

    # Verify the sender is part of the match
    match_data = await get_match_by_id(message.match_id)
    if not match_data:
        raise HTTPException(status_code=404, detail="Match not found")

    if sender_id not in [match_data['user1_id'], match_data['user2_id']]:
        raise HTTPException(status_code=403, detail="Sender is not part of this match")

    new_message_data = {
        "match_id": message.match_id,
        "sender_id": sender_id,
        "message_text": message.message_text,
        "sent_at": datetime.utcnow().isoformat()  # Store as ISO format string, Supabase handles timestamp
    }

    try:
        response =  supabase.table("messages").insert(new_message_data).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Could not send message")

        # Assuming the response.data[0] contains the newly created message with all fields
        # Adjust based on actual Supabase response structure
        created_message = response.data[0]
        return Message(
            message_id=created_message['message_id'],
            match_id=created_message['match_id'],
            sender_id=created_message['sender_id'],
            message_text=created_message['message_text'],
            sent_at=datetime.fromisoformat(created_message['sent_at'].replace('Z', '+00:00')),
            # Ensure timezone handling
            read_at=datetime.fromisoformat(created_message['read_at'].replace('Z', '+00:00')) if created_message.get(
                'read_at') else None
        )
    except Exception as e:
        # Log the error e
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


async def get_chat_messages_service(match_id: int, current_user_email: str, page: int = 1, page_size: int = 20) -> List[
    Message]:
    current_user_id = await get_user_id_from_email(current_user_email)

    # Verify the current user is part of the match
    match_data = await get_match_by_id(match_id)
    if not match_data:
        raise HTTPException(status_code=404, detail="Match not found")

    if current_user_id not in [match_data['user1_id'], match_data['user2_id']]:
        raise HTTPException(status_code=403, detail="User is not part of this match")

    offset = (page - 1) * page_size
    try:
        response =  supabase.table("messages") \
            .select("*") \
            .eq("match_id", match_id) \
            .order("sent_at", desc=True) \
            .limit(page_size) \
            .offset(offset) \
            .execute()

        if not response.data:
            return []

        messages = []
        for msg_data in response.data:
            messages.append(Message(
                message_id=msg_data['message_id'],
                match_id=msg_data['match_id'],
                sender_id=msg_data['sender_id'],
                message_text=msg_data['message_text'],
                sent_at=datetime.fromisoformat(msg_data['sent_at'].replace('Z', '+00:00')),
                read_at=datetime.fromisoformat(msg_data['read_at'].replace('Z', '+00:00')) if msg_data.get(
                    'read_at') else None
            ))
        return messages  # Messages will be newest first, you might want to reverse this on the client or here
    except Exception as e:
        # Log the error e
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


async def mark_messages_as_read_service(match_id: int, reader_email: str):
    reader_id = await get_user_id_from_email(reader_email)

    match_data = await get_match_by_id(match_id)
    if not match_data:
        raise HTTPException(status_code=404, detail="Match not found")

    if reader_id not in [match_data['user1_id'], match_data['user2_id']]:
        raise HTTPException(status_code=403, detail="User is not part of this match")

    try:
        # Update messages where the reader is NOT the sender and read_at is null
        response =  supabase.table("messages") \
            .update({"read_at": datetime.utcnow().isoformat()}) \
            .eq("match_id", match_id) \
            .neq("sender_id", reader_id) \
            .is_("read_at", None) \
            .execute()

        # response.data might be empty even on success for updates, check count if available or rely on no exception
        return {"status": "success", "updated_count": len(
            response.data) if response.data else "unknown (check Supabase logs for actual count)"}
    except Exception as e:
        # Log the error e
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


async def get_user_conversations_service(current_user_email: str):
    """
    Fetches all matches (conversations) for the current user,
    optionally with the last message for each.
    This is a simplified version; you might want more complex logic for last message.
    """
    current_user_id = await get_user_id_from_email(current_user_email)

    # Get matches where the current user is user1_id or user2_id
    query1 = supabase.table("matches").select("match_id, user1_id, user2_id").eq("user1_id", current_user_id)
    query2 = supabase.table("matches").select("match_id, user1_id, user2_id").eq("user2_id", current_user_id)

    response1 = query1.execute()
    response2 = query2.execute()

    all_matches_data = []
    if response1.data:
        all_matches_data.extend(response1.data)
    if response2.data:
        all_matches_data.extend(response2.data)

    # Deduplicate matches if necessary
    unique_matches = {m['match_id']: m for m in all_matches_data}.values()

    conversations_summary = []
    for match_info in unique_matches:
        other_user_id = match_info['user2_id'] if match_info['user1_id'] == current_user_id else match_info['user1_id']

        # Fetch other user's info
        other_user_response = supabase.table("users").select(
            "user_id, first_name, last_name, profile_picture_url"
        ).eq("user_id", other_user_id).maybe_single().execute()

        other_user_details = {}
        if other_user_response and other_user_response.data:
            other_user_details = {
                "user_id": other_user_response.data['user_id'],
                "name": f"{other_user_response.data.get('first_name', '')} {other_user_response.data.get('last_name', '')}".strip(),
                "profile_picture_url": other_user_response.data.get('profile_picture_url')
            }

        # Get last message for the match
        last_message_summary = None
        last_message_response = supabase.table("messages") \
            .select("message_text, sent_at, sender_id") \
            .eq("match_id", match_info['match_id']) \
            .order("sent_at", desc=True) \
            .limit(1) \
            .maybe_single() \
            .execute()

        if last_message_response and last_message_response.data:
            try:
                last_message_summary = {
                    "text": last_message_response.data['message_text'],
                    "sent_at": datetime.fromisoformat(last_message_response.data['sent_at'].replace('Z', '+00:00')),
                    "is_sender_current_user": last_message_response.data['sender_id'] == current_user_id
                }
            except Exception as e:
                print(f"Error parsing last message: {e}")

        conversations_summary.append({
            "match_id": match_info['match_id'],
            "other_user": other_user_details,
            "last_message": last_message_summary
        })

    return conversations_summary

# ... (keep your existing service functions)