from fastapi import FastAPI
from supabase import create_client, Client
import os

app = FastAPI(title="EccomiVideoAI - Motore")

# Inizializzazione Supabase
# Render prenderà queste chiavi dalle "Environment Variables" per sicurezza
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Connettiti a Supabase solo se le chiavi sono presenti
if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Connessione a Supabase stabilita!")
else:
    print("⚠️ ATTENZIONE: Variabili SUPABASE_URL o SUPABASE_KEY mancanti.")

@app.get("/")
async def root():
    return {"status": "online", "message": "EccomiVideoAI è operativo e pronto a renderizzare!"}
