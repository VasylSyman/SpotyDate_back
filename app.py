from fastapi import FastAPI, HTTPException, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from schemas import UserCreate
from services import *
from fastapi.responses import RedirectResponse, JSONResponse
from auth import *
from spotify_service import *
import logging
from typing import Set

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

@app.get("/user/me")
async def get_current_user_data(current_user_email: str = Depends(get_current_user)):
    try:
        return await current_user_data(current_user_email)
    except HTTPException as e:
        raise e

@app.post("/update_user/me")
async def update_current_user_data(
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    birth_date: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    bio: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user_email: str = Depends(get_current_user)
):
    try:
        return await current_user_data_update(first_name, last_name, birth_date, gender,
                                              bio, location, file, current_user_email)
    except HTTPException as e:
        raise e

@app.get("/auth/spotify")
async def spotify_auth(current_user_email: str = Depends(get_current_user)):
    """Initiate Spotify OAuth flow"""
    try:
        spotify = await refresh_spotify_token(current_user_email)
        auth_url = spotify.auth_manager.get_authorize_url()
        return JSONResponse({"url": auth_url})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/callback")
async def spotify_callback(
        request: SpotifyCallbackRequest,
        current_user_email: str = Depends(get_current_user)
):
    try:
        cache_path = f".cache-{current_user_email}"
        if os.path.exists(cache_path):
            os.remove(cache_path)

        spotify = await refresh_spotify_token(current_user_email)

        token_info = spotify.auth_manager.get_access_token(request.code)

        if not token_info:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        connection_data = await save_spotify_connection(current_user_email, spotify)

        await fetch_and_process_top_artists(spotify, current_user_email)
        await fetch_and_process_top_tracks(spotify, current_user_email)
        await fetch_and_process_genres(spotify, current_user_email)


        return {'code': 200, 'message': 'Successfully connected spotify.'}
    except Exception as e:
        import traceback
        print(f"Error in callback: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Spotify auth error: {str(e)}")

@app.get("/spotify/me", response_model=SpotifyProfile)
async def get_spotify_profile(current_user_email: str = Depends(get_current_user)):
    """Get user's Spotify connection status"""
    try:
        return await get_user_spotify_data(current_user_email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/spotify/genres")
async def get_combined_genres(
    current_user_email: str = Depends(get_current_user),
):
    master_context = "aggregating genres"
    all_genres: Set[str] = set()
    all_artist_ids: Set[str] = set()
    top_limit = 50
    time_range = "medium_term"

    try:
        spotify = await refresh_spotify_token(current_user_email)

        # --- 1. Process Saved Tracks ---
        context = f"processing {top_limit} saved tracks"
        logging.info(f"Starting: {context} for {current_user_email}")

        saved_tracks_data = spotify.current_user_saved_tracks(limit=top_limit)
        if saved_tracks_data and 'items' in saved_tracks_data:
            for item in saved_tracks_data.get('items', []):
                track = item.get('track')
                if track and track.get('artists'):
                    for artist in track['artists']:
                        if artist and artist.get('id'):
                            all_artist_ids.add(artist['id'])


        # --- 2. Process Top Tracks ---
        context = f"processing top {top_limit} tracks ({time_range})"
        logging.info(f"Starting: {context} for {current_user_email}")

        top_tracks_data = spotify.current_user_top_tracks(limit=top_limit, time_range=time_range)
        if top_tracks_data and 'items' in top_tracks_data:
            for track in top_tracks_data.get('items', []):
                if track and track.get('artists'):
                    for artist in track['artists']:
                        if artist and artist.get('id'):
                            all_artist_ids.add(artist['id'])

        # --- 3. Process Top Artists (Direct Genre Addition + ID Collection) ---
        context = f"processing top {top_limit} artists ({time_range})"
        logging.info(f"Starting: {context} for {current_user_email}")

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
        context = "fetching details for collected artist IDs"
        if not all_artist_ids:
            logging.info(f"No artist IDs collected from any source for {current_user_email}.")
        else:
            logging.info(f"Starting: {context} for {len(all_artist_ids)} unique IDs for {current_user_email}")
            artist_ids_list = list(all_artist_ids)
            batch_size = 50
            for i in range(0, len(artist_ids_list), batch_size):
                batch_ids = artist_ids_list[i:i + batch_size]
                batch_context = f"{context} (batch {i//batch_size + 1})"
                artists_details = spotify.artists(batch_ids)
                if artists_details and artists_details.get('artists'):
                    for artist in artists_details['artists']:
                        if artist and artist.get('genres'):
                            all_genres.update(artist['genres'])



        # --- 5. Return Final Sorted List ---
        sorted_genres = sorted(list(all_genres))
        logging.info(f"Finished {master_context} for {current_user_email}. Found {len(sorted_genres)} unique genres.")

        await genres_upload(sorted_genres, current_user_email)
        return {'code': 200, 'message': 'Successfully parsed and uploaded genres.'}

    except HTTPException as e:
         raise e
    except Exception as e:
        logging.error(f"Critical unexpected error during {master_context} for {current_user_email}: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred while aggregating genres.")

@app.get("/spotify/top-artists")
async def get_top_artists(
    current_user_email: str = Depends(get_current_user)
):
        spotify = await refresh_spotify_token(current_user_email)
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
        return {'code': 200, 'message': 'Successfully parsed and uploaded artists.'}

@app.get("/spotify/top-tracks")
async def get_top_tracks(
    current_user_email: str = Depends(get_current_user),
):
        spotify = await refresh_spotify_token(current_user_email)

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
        return {'code': 200, 'message': 'Successfully parsed and uploaded tracks.'}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
