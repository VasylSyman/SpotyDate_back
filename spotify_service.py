import spotipy
from spotipy.oauth2 import SpotifyOAuth
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

# In-memory storage
spotify_connections = {}


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

        if email in spotify_connections:
            token_info = spotify_connections[email]
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

        connection_data = {
            "user_email": email,
            "spotify_id": spotify_user["id"],
            "display_name": spotify_user.get("display_name"),
            "access_token": token_info["access_token"],
            "refresh_token": token_info["refresh_token"],
            "token_type": token_info["token_type"],
            "scope": token_info["scope"],
            "expires_at": datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc),
            "connected_at": datetime.now(timezone.utc)
        }

        # Store in our in-memory dictionary
        spotify_connections[email] = token_info  # Store the raw token_info
        return connection_data

    except Exception as e:
        import traceback
        print(f"Error saving connection: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to save Spotify connection: {str(e)}")


async def get_user_spotify_data(email: str) -> dict:
    try:
        return spotify_connections.get(email, None)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
