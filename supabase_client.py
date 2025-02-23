import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
SUPABASE_URL= os.getenv("SUPABASE_URL")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_API_KEY)

def get_supabase_client():
    return supabase

