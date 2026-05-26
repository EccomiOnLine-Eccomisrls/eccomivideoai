from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import os

app = FastAPI(title="EccomiVideoAI - Motore")

# ==========================================
# CONNESSIONE A SUPABASE
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Connessione a Supabase stabilita!")
else:
    print("⚠️ ATTENZIONE: Variabili Supabase mancanti.")

# ==========================================
# MODELLO DATI (Da eccomionline.com)
# ==========================================
class VideoRequest(BaseModel):
    user_id: str
    titolo_prodotto: str
    testo_script: str
    immagini_urls: list[str]

# ==========================================
# L'AGENTE IN BACKGROUND
# ==========================================
async def esegui_agente_video(dati: VideoRequest, job_id: str):
    print(f"--- Avvio Agente per Job {job_id} ---")
    
    try:
        # Aggiorniamo lo stato su Supabase a "elaborazione"
        supabase.table("richieste_video").update({"status": "elaborazione"}).eq("id", job_id).execute()
        
        print("[1/5] In attesa del LLM su Runpod...")
        # Qui in futuro chiameremo Runpod
        
        print("[2/5] In attesa del TTS su Runpod...")
        # Qui in futuro genereremo la voce
        
        print("[3/5] Download asset da Supabase in corso...")
        # Qui scaricheremo le immagini
        
        print("[4/5] Renderizzazione FFmpeg in corso...")
        # Qui useremo FFmpeg
        
        # Finta fine del lavoro per ora
        supabase.table("richieste_video").update({"status": "completato", "video_url_finale": "https://link-finto.mp4"}).eq("id", job_id).execute()
        print("--- Lavoro completato! Database aggiornato. ---")
        
    except Exception as e:
        print(f"ERRORE CRITICO: {e}")
        supabase.table("richieste_video").update({"status": "errore"}).eq("id", job_id).execute()

# ==========================================
# ENDPOINT PRINCIPALE
# ==========================================
@app.post("/crea-video")
async def ricevi_richiesta_video(richiesta: VideoRequest, background_tasks: BackgroundTasks):
    if not richiesta.testo_script or not richiesta.immagini_urls:
        raise HTTPException(status_code=400, detail="Testo e immagini mancanti")

    # 1. SALVIAMO I DATI SU SUPABASE NELLA TUA NUOVA TABELLA
    dati_db = {
        "user_id": richiesta.user_id,
        "titolo_prodotto": richiesta.titolo_prodotto,
        "testo_script": richiesta.testo_script,
        "immagini_urls": richiesta.immagini_urls,
        "status": "in_attesa"
    }
    
    risposta = supabase.table("richieste_video").insert(dati_db).execute()
    
    # Recuperiamo l'ID unico che Supabase ha assegnato a questo lavoro
    job_id = risposta.data[0]['id']

    # 2. AVVIAMO L'AGENTE
    background_tasks.add_task(esegui_agente_video, richiesta, job_id)
    
    return {
        "status": "success", 
        "message": "Richiesta salvata nel database! L'Agente sta lavorando.",
        "job_id": job_id
    }
