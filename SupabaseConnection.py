import os
from supabase import create_client, Client
from dotenv import load_dotenv


load_dotenv()

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE"]  # backend → service_role
supabase: Client = create_client(url, key)

