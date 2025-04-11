import spotipy
from spotipy.oauth2 import SpotifyOAuth
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from fastapi import HTTPException
from supabase_client import get_supabase_client
import json

load_dotenv()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

# In-memory storage
spotify_connections = {}


load_dotenv()
SUPABASE_STORAGE_URL = os.getenv("SUPABASE_STORAGE_URL")
supabase = get_supabase_client()


async def get_spotify_client(email: str) -> spotipy.Spotify:
    try:
        cache_path = f".cache-{email}"

        auth_manager = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope="user-library-read user-read-recently-played user-top-read user-read-currently-playing",
            cache_path=cache_path
        )

        user_response = supabase.table("users").select("user_id").eq("email",
                                                                     email).maybe_single().execute()
        user_id = user_response.data.get("user_id")

        response = supabase.table("spotify_accounts").select("token_info").eq("user_id", user_id).execute()

        if response.data and len(response.data) > 0 and response.data[0]["token_info"]:
            token_info = json.loads(response.data[0]["token_info"])
            auth_manager.cache_handler.save_token_to_cache(token_info)

        return spotipy.Spotify(auth_manager=auth_manager)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def save_spotify_connection(email: str, spotify_client: spotipy.Spotify):
    try:
        # Get the token info directly from the cache handler
        token_info = spotify_client.auth_manager.cache_handler.get_cached_token()
        if not token_info:
            raise Exception("No token information available")

        # Get the user information
        spotify_user = spotify_client.me()

        token_info_json = json.dumps(token_info)

        print(token_info_json)

        user_response = supabase.table("users").select("user_id").eq("email", email).maybe_single().execute()
        user_id = user_response.data.get("user_id")

        connection_data = {
            "user_id": user_id,
            "spotify_id": spotify_user["id"],
            "display_name": spotify_user.get("display_name"),
            "token_info": token_info_json,  # Store the full token info as JSON string
            "expires_at": datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc).isoformat(),
            "connected_at": datetime.now(timezone.utc).isoformat()
        }

        response = supabase.table("spotify_accounts").upsert(connection_data).execute()

        if hasattr(response, 'error') and response.error:
            raise Exception(f"Supabase error: {response.error.message}")

        return connection_data

    except Exception as e:
        import traceback
        print(f"Error saving connection: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to save Spotify connection: {str(e)}")


async def get_user_spotify_data(email: str) -> dict:
    try:
        user_response = supabase.table("users").select("user_id").eq("email", email).maybe_single().execute()
        user_id = user_response.data.get("user_id")

        response = supabase.table("spotify_accounts").select("*").eq("user_id", user_id).execute()

        if response.data and len(response.data) > 0:
            # Parse the stored token info JSON
            if response.data[0]["token_info"]:
                response.data[0]["token_info"] = json.loads(response.data[0]["token_info"])
            return response.data[0]

        return None

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def refresh_spotify_token(email: str):
    try:
        user_response = supabase.table("users").select("user_id").eq("email", email).maybe_single().execute()
        user_id = user_response.data.get("user_id")

        spotify_client = await get_spotify_client(email)
        token_info = spotify_client.auth_manager.cache_handler.get_cached_token()

        if token_info:
            supabase.table("spotify_accounts").update({
                "token_info": json.dumps(token_info),
                "expires_at": datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc).isoformat()
            }).eq("user_id", user_id).execute()

        return spotify_client

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh Spotify token: {str(e)}")
