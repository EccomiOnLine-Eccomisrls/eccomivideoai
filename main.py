from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from groq import AsyncGroq
import httpx
import os

app = FastAPI(title="EccomiVideoAI - Motore")

# ==========================================
# CONNESSIONI E VARIABILI D'AMBIENTE
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")

# Il timbro vocale ufficiale di Eccomi Man
VOICE_SAMPLE_URL = "https://jyksiqbmckdwtnmzgfhc.supabase.co/storage/v1/object/public/inputs/bf7edd64-9129-47bb-9f4f-92464b08d94a/dubbed_audio.wav"

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ ATTENZIONE: Variabili Supabase mancanti.")

groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ==========================================
# MODELLO DATI (AGGIORNATO CON OPZIONI SFONDO)
# ==========================================
class VideoRequest(BaseModel):
    user_id: str
    titolo_prodotto: str
    testo_script: str
    immagini_urls: list[str]
    opzione_sfondo: str = "mantenere"  # Scelte possibili: mantenere, cambiare, inventa
    url_sfondo_personalizzato: str = "" # URL se l'utente carica uno sfondo specifico

# ==========================================
# FASE 1: IL CERVELLO (Groq)
# ==========================================
async def ottimizza_testo(testo_originale: str) -> str:
    if not groq_client:
        return testo_originale
    
    prompt = f"""Sei il copywriter ed esperto di marketing di 'EccomiOnline'.
    Il tuo compito è prendere il testo inserito dall'utente e migliorarlo per renderlo uno script video perfetto per la nostra mascotte virtuale (un supereroe blu).
    Il tono deve essere energico, accattivante e persuasivo.
    
    Testo originale dell'utente: "{testo_originale}"
    
    Regola fondamentale: Restituisci SOLO il testo finale che la mascotte dovrà leggere ad alta voce. Niente introduzioni ("Ecco il testo:"), niente commenti, niente virgolette."""

    print("🧠 Sto chiedendo a Groq (Llama 3.1) di ottimizzare il testo...")
    response = await groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        temperature=0.7
    )
    return response.choices[0].message.content

# ==========================================
# FASE 3: MONTAGGIO VIDEO (FFMPEG) - BOZZA LOGICA
# ==========================================
async def genera_video_finale(audio_url: str, immagini: list[str], opzione_sfondo: str, sfondi_url: str, job_id: str):
    """
    Questa funzione prenderà l'audio generato da Runpod e le immagini del prodotto
    e userà FFmpeg per comporre il video finale con i sottotitoli.
    """
    print(f"🎬 [3/5] Avvio montaggio video per Sfondo: {opzione_sfondo}...")
    
    # TODO: Logica di download dei file locali, creazione file .srt per i sottotitoli
    # ed esecuzione del comando FFmpeg.
    
    # Per ora simuliamo la chiusura rimandando l'audio nel DB per i test
    return audio_url

# ==========================================
# L'AGENTE IN BACKGROUND
# ==========================================
async def esegui_agente_video(dati: VideoRequest, job_id: str):
    print(f"--- Avvio Agente per Job {job_id} ---")
    try:
        supabase.table("richieste_video").update({"status": "elaborazione_testo"}).eq("id", job_id).execute()
        
        # --- FASE 1: TESTO ---
        print("[1/5] Elaborazione testo con Groq...")
        testo_definitivo = await ottimizza_testo(dati.testo_script)
        print(f"✅ Testo finale generato: {testo_definitivo}")
        supabase.table("richieste_video").update({"testo_script": testo_definitivo}).eq("id", job_id).execute()
        
        # --- FASE 2: AUDIO (RUNPOD) ---
        print("[2/5] Invio testo a Runpod per la clonazione vocale...")
        supabase.table("richieste_video").update({"status": "generazione_audio"}).eq("id", job_id).execute()

        if not RUNPOD_API_KEY or not RUNPOD_ENDPOINT_ID:
            raise Exception("Chiavi Runpod mancanti nelle variabili d'ambiente!")

        runpod_url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/runsync"
        headers = {
            "Authorization": f"Bearer {RUNPOD_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": {
                "text": testo_definitivo,
                "voice_sample_url": VOICE_SAMPLE_URL,
                "language": "it"
            }
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            risposta_runpod = await client.post(runpod_url, headers=headers, json=payload)
            dati_runpod = risposta_runpod.json()
        
        if "error" in dati_runpod or ("output" in dati_runpod and dati_runpod["output"].get("ok") == False):
            raise Exception(f"Errore da Runpod: {dati_runpod}")
            
        audio_url_finale = dati_runpod["output"]["audio_url"]
        print(f"✅ Audio generato con successo: {audio_url_finale}")
        
        # --- FASE 3: VIDEO ---
        supabase.table("richieste_video").update({"status": "generazione_video"}).eq("id", job_id).execute()
        
        # Chiamata alla nostra nuova funzione di montaggio video
        video_url_render = await genera_video_finale(
            audio_url=audio_url_finale,
            immagini=dati.immagini_urls,
            opzione_sfondo=dati.opzione_sfondo,
            sfondi_url=dati.url_sfondo_personalizzato,
            job_id=job_id
        )
        
        # Lavoro completato con successo
        supabase.table("richieste_video").update({
            "status": "completato", 
            "video_url_finale": video_url_render
        }).eq("id", job_id).execute()
        
        print("--- Lavoro completato! Video pronto. ---")
        
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
    return {"status": "success", "message": "L'Agente ha iniziato a elaborare il video!", "job_id": job_id}
