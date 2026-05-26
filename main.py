from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from groq import AsyncGroq
import httpx
import os
import re
import tempfile
import subprocess
import requests

app = FastAPI(title="EccomiVideoAI - Motore")

# ==========================================
# CONNESSIONI E VARIABILI D'AMBIENTE
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")

VOICE_SAMPLE_URL = "https://jyksiqbmckdwtnmzgfhc.supabase.co/storage/v1/object/public/inputs/bf7edd64-9129-47bb-9f4f-92464b08d94a/dubbed_audio.wav"

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ ATTENZIONE: Variabili Supabase mancanti.")

groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ==========================================
# MODELLO DATI
# ==========================================
class VideoRequest(BaseModel):
    user_id: str
    titolo_prodotto: str
    testo_script: str
    immagini_urls: list[str]
    opzione_sfondo: str = "mantenere"
    url_sfondo_personalizzato: str = ""

# ==========================================
# AUX: UTILITY PER TEMPI E SOTTOTITOLI
# ==========================================
def format_srt_time(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"

def genera_file_srt(testo: str, durata_totale: float, srt_path: str):
    parole = testo.split()
    if not parole:
        return
    
    parole_per_blocco = 4
    blocchi = [parole[i:i + parole_per_blocco] for i in range(0, len(parole), parole_per_blocco)]
    durata_blocco = durata_totale / len(blocchi)
    
    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, blocco in enumerate(blocchi):
            start_time = idx * durata_blocco
            end_time = (idx + 1) * durata_blocco
            testo_blocco = " ".join(blocco)
            
            f.write(f"{idx + 1}\n")
            f.write(f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n")
            f.write(f"{testo_blocco}\n\n")

def get_audio_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

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
    
    Regola fondamentale: Restituisci SOLO il testo finale che la mascotte dovrà leggere ad alta voce. Niente introduzioni, niente commenti, niente virgolette."""

    response = await groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        temperature=0.7
    )
    return response.choices[0].message.content

# ==========================================
# FASE 3: MONTAGGIO VIDEO REALE (LIGHT VERSION)
# ==========================================
async def genera_video_finale(audio_url: str, immagini: list[str], testo_script: str, job_id: str) -> str:
    print(f"🎬 [3/5] Avvio montaggio video FFmpeg ultra-leggero per il Job {job_id}...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        local_audio = os.path.join(tmpdir, "audio.wav")
        local_image = os.path.join(tmpdir, "input_image.jpg")
        local_srt = os.path.join(tmpdir, "subtitles.srt")
        local_output = os.path.join(tmpdir, "output_video.mp4")
        
        # 1. Download dell'Audio
        r_audio = requests.get(audio_url)
        with open(local_audio, "wb") as f:
            f.write(r_audio.content)
            
        # 2. Download dell'immagine di background
        url_immagine = immagini[0] if immagini else "https://picsum.photos/1080/1920"
        if "tuo-supabase.co" in url_immagine:
            url_immagine = "https://images.unsplash.com/photo-1542496658-e33a6d0d50f6?q=80&w=1080&auto=format&fit=crop"
            
        r_img = requests.get(url_immagine)
        with open(local_image, "wb") as f:
            f.write(r_img.content)
            
        # 3. Calcolo durata audio
        durata = get_audio_duration(local_audio)
        print(f"⏱️ Durata audio: {durata} secondi. Genero SRT...")
        
        # 4. Generazione Sottotitoli
        genera_file_srt(testo_script, duration_totale=durata, srt_path=local_srt)
        
        # 5. Rendering Video con FFmpeg - VERSIONE SALVA-RAM
        print("🎥 Rendering FFmpeg (Modalità Low-RAM attive)...")
        safe_srt_path = local_srt.replace("\\", "/").replace(":", "\\:")
        
        cmd_ffmpeg = [
            "ffmpeg", "-y",
            "-loop", "1", "-r", "10", "-i", local_image,   # -r 10 riduce il framerate all'origine risparmiando RAM
            "-i", local_audio,
            "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles={safe_srt_path}:force_style='Alignment=2,FontSize=16,PrimaryColour=&H00FFFF&,OutlineColour=&H000000&,BorderStyle=3,Outline=1'",
            "-c:v", "libx264", 
            "-preset", "ultrafast",                        # Velocizza l'editing abbattendo l'uso di memoria
            "-crf", "28",                                  # Compressione ottimale per ambienti cloud leggeri
            "-t", str(durata),
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            local_output
        ]
        
        result = subprocess.run(cmd_ffmpeg, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ FFmpeg fallito. STDERR: {result.stderr}")
            raise Exception(f"FFmpeg è fallito! Errore:\n{result.stderr}")
            
        print("✅ Rendering FFmpeg completato con successo!")
        
        # 6. Upload del video su Supabase Storage
        print("☁️ Carico il video finale su Supabase...")
        object_path = f"{job_id}/video_finale.mp4"
        upload_url = f"{SUPABASE_URL}/storage/v1/object/inputs/{object_path}?upsert=true"
        
        with open(local_output, "rb") as f:
            video_data = f.read()
            
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "Content-Type": "video/mp4",
        }
        
        r_upload = requests.put(upload_url, headers=headers, data=video_data)
        if r_upload.status_code not in (200, 201):
            raise Exception(f"Upload video fallito: {r_upload.text}")
            
        return f"{SUPABASE_URL}/storage/v1/object/public/inputs/{object_path}"

# ==========================================
# L'AGENTE IN BACKGROUND
# ==========================================
async def esegui_agente_video(dati: VideoRequest, job_id: str):
    print(f"--- Avvio Agente per Job {job_id} ---")
    try:
        supabase.table("richieste_video").update({"status": "elaborazione_testo"}).eq("id", job_id).execute()
        
        print("[1/5] Elaborazione testo con Groq...")
        testo_definitivo = await ottimizza_testo(dati.testo_script)
        supabase.table("richieste_video").update({"testo_script": testo_definitivo}).eq("id", job_id).execute()
        
        print("[2/5] Invio testo a Runpod...")
        supabase.table("richieste_video").update({"status": "generazione_audio"}).eq("id", job_id).execute()

        runpod_url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/runsync"
        headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}", "Content-Type": "application/json"}
        payload = {"input": {"text": testo_definitivo, "voice_sample_url": VOICE_SAMPLE_URL, "language": "it"}}
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            risposta_runpod = await client.post(runpod_url, headers=headers, json=payload)
            dati_runpod = risposta_runpod.json()
        
        if "error" in dati_runpod or ("output" in dati_runpod and dati_runpod["output"].get("ok") == False):
            raise Exception(f"Errore da Runpod: {dati_runpod}")
            
        audio_url_finale = dati_runpod["output"]["audio_url"]
        
        # --- FASE 3: VIDEO ---
        supabase.table("richieste_video").update({"status": "generazione_video"}).eq("id", job_id).execute()
        
        video_url_finale = await genera_video_finale(
            audio_url=audio_url_finale,
            immagini=dati.immagini_urls,
            testo_script=testo_definitivo,
            job_id=job_id
        )
        
        supabase.table("richieste_video").update({
            "status": "completato", 
            "video_url_finale": video_url_finale
        }).eq("id", job_id).execute()
        
        print(f"--- Lavoro completato! Video pronto: {video_url_finale} ---")
        
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
    return {"status": "success", "message": "L'Agente video è partito!", "job_id": job_id}
