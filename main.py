from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from groq import AsyncGroq
import os

app = FastAPI(title="EccomiVideoAI - Motore")

# ==========================================
# CONNESSIONI
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ ATTENZIONE: Variabili Supabase mancanti.")

# Inizializziamo il "Cervello" di Groq
groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ==========================================
# MODELLO DATI
# ==========================================
class VideoRequest(BaseModel):
    user_id: str
    titolo_prodotto: str
    testo_script: str
    immagini_urls: list[str]

# ==========================================
# LE FUNZIONI DEL CERVELLO (Nuovo blocco)
# ==========================================
async def ottimizza_testo(testo_originale: str) -> str:
    if not groq_client:
        return testo_originale # Se manca la chiave, usa il testo base
    
    prompt = f"""Sei il copywriter ed esperto di marketing di 'EccomiOnline'.
    Il tuo compito è prendere il testo inserito dall'utente e migliorarlo per renderlo uno script video perfetto per la nostra mascotte virtuale (un supereroe blu).
    Il tono deve essere energico, accattivante e persuasivo.
    
    Testo originale dell'utente: "{testo_originale}"
    
    Regola fondamentale: Restituisci SOLO il testo finale che la mascotte dovrà leggere ad alta voce. Niente introduzioni, niente commenti, niente virgolette."""

    print("🧠 Sto chiedendo a Groq (Llama 3) di ottimizzare il testo...")
    response = await groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant", # Modello velocissimo e potente
        temperature=0.7
    )
    return response.choices[0].message.content

# ==========================================
# L'AGENTE IN BACKGROUND
# ==========================================
async def esegui_agente_video(dati: VideoRequest, job_id: str):
    print(f"--- Avvio Agente per Job {job_id} ---")
    try:
        supabase.table("richieste_video").update({"status": "elaborazione"}).eq("id", job_id).execute()
        
        # FASE 1: Il Cervello (Groq) lavora il testo
        print("[1/5] Elaborazione testo con Groq...")
        testo_definitivo = await ottimizza_testo(dati.testo_script)
        print(f"✅ Testo finale generato: {testo_definitivo}")
        
        # Salviamo il testo migliorato su Supabase per tenerne traccia
        supabase.table("richieste_video").update({"testo_script": testo_definitivo}).eq("id", job_id).execute()
        
        print("[2/5] In attesa del TTS su Runpod...")
        print("[3/5] Download asset da Supabase in corso...")
        print("[4/5] Renderizzazione FFmpeg in corso...")
        
        supabase.table("richieste_video").update({"status": "completato", "video_url_finale": "https://link-finto.mp4"}).eq("id", job_id).execute()
        print("--- Lavoro completato! ---")
        
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

    dati_db = {
        "user_id": richiesta.user_id,
        "titolo_prodotto": richiesta.titolo_prodotto,
        "testo_script": richiesta.testo_script,
        "immagini_urls": richiesta.immagini_urls,
        "status": "in_attesa"
    }
    
    risposta = supabase.table("richieste_video").insert(dati_db).execute()
    job_id = risposta.data[0]['id']

    background_tasks.add_task(esegui_agente_video, richiesta, job_id)
    return {"status": "success", "message": "L'Agente ha iniziato a pensare!", "job_id": job_id}
