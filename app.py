from fastapi import FastAPI, HTTPException, File, Form, UploadFile, Query, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from schemas import UserCreate
from services import *
from fastapi.responses import RedirectResponse, JSONResponse
from auth import *
from spotify_service import *
import logging
from typing import Set, Dict

app = FastAPI()


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    async def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_message(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                await connection.send_json(message)


manager = ConnectionManager()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        email = verify_token(token)  # Your function to verify the token and extract user info
        if not email:
            await websocket.close(code=1008, reason="Authentication failed")
            return

        user_id_data = await current_user_data(email)
        user_id = user_id_data.get("user_id")

        if not user_id:
            await websocket.close(code=1008, reason="User not found")
            return

        user_email = email  # You already have the email from the token

        await manager.connect(websocket, str(user_id)) # Ensure user_id is a string if used as key
        try:
            while True:
                data = await websocket.receive_json()

                # Process message based on type
                if data.get('type') == 'message':
                    message_data = MessageCreate(
                        match_id=data['match_id'],
                        message_text=data['message_text']
                    )
                    new_message = await create_chat_message_service(message_data, user_email)
                    match_data = await get_match_by_id(data['match_id'])
                    recipient_id = match_data['user1_id'] if match_data['user1_id'] != user_id else match_data['user2_id']
                    message_response = {
                        "message_id": new_message.message_id,
                        "match_id": new_message.match_id,
                        "sender_id": new_message.sender_id,
                        "message_text": new_message.message_text,
                        "sent_at": new_message.sent_at.isoformat(),
                        "read_at": new_message.read_at.isoformat() if new_message.read_at else None
                    }
                    await manager.send_message(message_response, str(user_id))
                    await manager.send_message(message_response, str(recipient_id))

                elif data.get('type') == 'read':
                    await mark_messages_as_read_service(data['match_id'], user_email)
                    match_data = await get_match_by_id(data['match_id'])
                    other_user_id = match_data['user1_id'] if match_data['user1_id'] != user_id else match_data['user2_id']
                    await manager.send_message({
                        "type": "read_receipt",
                        "match_id": data['match_id'],
                        "reader_id": str(user_id),
                        "read_at": datetime.utcnow().isoformat()
                    }, str(other_user_id))

        except WebSocketDisconnect:
            await manager.disconnect(websocket, str(user_id))

    except HTTPException as e:
        await websocket.close(code=1008, reason=e.detail)
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        await websocket.close(code=1011, reason="Internal server error")

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

        matches_result = await find_matches(current_user_email)

        return {
            'code': 200,
            'message': 'Successfully connected spotify.',
            'matches_found': len(matches_result),
            'top_matches': matches_result[:5]
        }
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


@app.get("/matches")
async def get_user_matches(current_user_email: str = Depends(get_current_user)):
    """
    Fetch all matches for the current user with detailed information.
    Returns match details including personal info and shared musical preferences.
    """
    try:
        # Get the current user's ID
        user_response = supabase.table("users").select("user_id").eq("email",
                                                                     current_user_email).maybe_single().execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")

        current_user_id = user_response.data.get("user_id")

        # Find all matches where the current user is either user1_id or user2_id
        matches_as_user1 = supabase.table("matches") \
            .select("match_id, user1_id, user2_id, match_score") \
            .eq("user1_id", current_user_id) \
            .execute()

        matches_as_user2 = supabase.table("matches") \
            .select("match_id, user1_id, user2_id, match_score") \
            .eq("user2_id", current_user_id) \
            .execute()

        # Combine and process match data
        detailed_matches = []

        # Process matches where current user is user1
        for match in matches_as_user1.data:
            match_details = await get_match_details(current_user_id, match["user2_id"], match["match_score"], match["match_id"])
            if match_details:
                detailed_matches.append(match_details)

        # Process matches where current user is user2
        for match in matches_as_user2.data:
            match_details = await get_match_details(current_user_id, match["user1_id"], match["match_score"], match["match_id"])
            if match_details:
                detailed_matches.append(match_details)

        # Sort matches by score (highest first)
        detailed_matches.sort(key=lambda x: x["match_score"], reverse=True)

        return {
            "matches_count": len(detailed_matches),
            "matches": detailed_matches
        }

    except Exception as e:
        import traceback
        print(f"Error fetching matches: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error fetching matches: {str(e)}")


#-----------------------------------------------------------------------------------------------------------------------

@app.post("/chat/messages", response_model=Message, status_code=201)
async def send_chat_message(
    message_data: MessageCreate,
    current_user_email: str = Depends(get_current_user)
):
    """
    Send a chat message to a match.
    The `match_id` in the request body specifies the conversation.
    The sender is identified by the authentication token.
    """
    try:
        # The service function will handle fetching sender_id from email
        # and verifying if the sender is part of the match_id
        new_message = await create_chat_message_service(message_data, current_user_email)
        return new_message
    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error(f"Error sending message: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Could not send message.")

@app.get("/chat/matches/{match_id}/messages", response_model=List[Message])
async def get_chat_messages(
    match_id: int,
    current_user_email: str = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100) # Max 100 messages per page
):
    """
    Retrieve chat messages for a specific match (conversation).
    Implements pagination.
    """
    try:
        # The service function will handle verifying if the current user is part of the match
        messages = await get_chat_messages_service(match_id, current_user_email, page, page_size)
        return messages
    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error(f"Error getting messages for match {match_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not retrieve messages.")

@app.post("/chat/matches/{match_id}/read", status_code=200)
async def mark_match_messages_as_read(
    match_id: int,
    current_user_email: str = Depends(get_current_user)
):
    """
    Mark all messages in a match (sent by the other user) as read by the current user.
    """
    try:
        # The service will get the reader_id from email and update messages
        result = await mark_messages_as_read_service(match_id, current_user_email)
        return {"message": "Messages marked as read successfully", "details": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error(f"Error marking messages as read for match {match_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not mark messages as read.")

@app.get("/chat/conversations", response_model=List[dict])
async def get_my_conversations(
    current_user_email: str = Depends(get_current_user)
):

    try:
        conversations = await get_user_conversations_service(current_user_email)
        return conversations
    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error(f"Error fetching conversations for user {current_user_email}: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not retrieve conversations.")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
