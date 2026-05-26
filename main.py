from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from groq import AsyncGroq
import httpx
import os
import tempfile
import subprocess
import requests

app = FastAPI(title="EccomiVideoAI - Motore SaaS")

# ==========================================
# CONNESSIONI E VARIABILI D'AMBIENTE
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID") # Endpoint per la Voce
RUNPOD_VIDEO_ENDPOINT_ID = os.getenv("RUNPOD_VIDEO_ENDPOINT_ID") # Endpoint per l'Animazione Video

VOICE_SAMPLE_URL = "https://jyksiqbmckdwtnmzgfhc.supabase.co/storage/v1/object/public/inputs/bf7edd64-9129-47bb-9f4f-92464b08d94a/dubbed_audio.wav"

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ ATTENZIONE: Variabili Supabase mancanti.")

groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

class VideoRequest(BaseModel):
    user_id: str
    titolo_prodotto: str
    testo_script: str
    immagini_urls: list[str]
    opzione_sfondo: str = "mantenere"
    url_sfondo_personalizzato: str = ""

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
            f.write(f"{idx + 1}\n{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n{' '.join(blocco)}\n\n")

def get_audio_duration(audio_path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

async def ottimizza_testo(testo_originale: str) -> str:
    if not groq_client: return testo_originale
    prompt = f"""Sei il copywriter di 'EccomiOnline'. Migliora questo testo per renderlo uno script video perfetto per una pubblicità dinamica. Tono energico.
    Testo originale: "{testo_originale}"
    Restituisci SOLO lo script finale parlato, senza virgolette o introduzioni."""
    response = await groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}], model="llama-3.1-8b-instant", temperature=0.7
    )
    return response.choices[0].message.content

async def genera_video_finale(audio_url: str, video_animato_url: str, testo_script: str, job_id: str) -> str:
    print(f"🎬 [4/5] Montaggio finale FFmpeg per il Job {job_id}...")
    with tempfile.TemporaryDirectory() as tmpdir:
        local_audio = os.path.join(tmpdir, "audio.wav")
        local_video = os.path.join(tmpdir, "animazione.mp4")
        local_srt = os.path.join(tmpdir, "subtitles.srt")
        local_output = os.path.join(tmpdir, "output_video.mp4")
        
        # Download Audio
        r_audio = requests.get(audio_url)
        with open(local_audio, "wb") as f: f.write(r_audio.content)
            
        # Download Video Animato da Runpod
        r_vid = requests.get(video_animato_url)
        with open(local_video, "wb") as f: f.write(r_vid.content)
            
        durata = get_audio_duration(local_audio)
        genera_file_srt(testo_script, durata_totale=durata, srt_path=local_srt)
        safe_srt_path = local_srt.replace("\\", "/").replace(":", "\\:")
        
        # FFmpeg: Mette in loop il video animato (-stream_loop -1) per coprire tutta la durata dell'audio
        cmd_ffmpeg = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", local_video,
            "-i", local_audio,
            "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles={safe_srt_path}:force_style='Alignment=2,FontSize=16,PrimaryColour=&H00FFFF&,OutlineColour=&H000000&,BorderStyle=3,Outline=1'",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-t", str(durata),
            "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
            local_output
        ]
        result = subprocess.run(cmd_ffmpeg, capture_output=True, text=True)
        if result.returncode != 0: raise Exception(f"FFmpeg è fallito! Errore:\n{result.stderr}")
        
        object_path = f"{job_id}/video_finale_animato.mp4"
        upload_url = f"{SUPABASE_URL}/storage/v1/object/inputs/{object_path}?upsert=true"
        with open(local_output, "rb") as f: video_data = f.read()
        headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Content-Type": "video/mp4"}
        requests.put(upload_url, headers=headers, data=video_data).raise_for_status()
        
        return f"{SUPABASE_URL}/storage/v1/object/public/inputs/{object_path}"

async def esegui_agente_video(dati: VideoRequest, job_id: str):
    print(f"--- Avvio SaaS Agente per Job {job_id} ---")
    try:
        # [1/5] Testo
        supabase.table("richieste_video").update({"status": "elaborazione_testo"}).eq("id", job_id).execute()
        testo_definitivo = await ottimizza_testo(dati.testo_script)
        supabase.table("richieste_video").update({"testo_script": testo_definitivo}).eq("id", job_id).execute()
        
        # [2/5] Voce
        print("[2/5] Clonazione vocale...")
        supabase.table("richieste_video").update({"status": "generazione_audio"}).eq("id", job_id).execute()
        headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}", "Content-Type": "application/json"}
        payload_audio = {"input": {"text": testo_definitivo, "voice_sample_url": VOICE_SAMPLE_URL, "language": "it"}}
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            r_audio = await client.post(f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/runsync", headers=headers, json=payload_audio)
            audio_url_finale = r_audio.json()["output"]["audio_url"]

        # [3/5] Animazione Video AI (IL NUOVO MOTORE)
        print("[3/5] Generazione animazione video AI su Runpod...")
        supabase.table("richieste_video").update({"status": "generazione_video_ai"}).eq("id", job_id).execute()
        immagine_base = dati.immagini_urls[0] if dati.immagini_urls else "https://picsum.photos/1080/1920"
        payload_video = {"input": {"image_url": immagine_base, "prompt": "A dynamic, cinematic advertisement animation of the subject, high quality, moving"}}
        
        async with httpx.AsyncClient(timeout=600.0) as client:
            r_video = await client.post(f"https://api.runpod.ai/v2/{RUNPOD_VIDEO_ENDPOINT_ID}/runsync", headers=headers, json=payload_video)
            dati_video = r_video.json()
            if "error" in dati_video or ("output" in dati_video and "error" in dati_video.get("output", {})):
                raise Exception(f"Errore Motore Video AI: {dati_video}")
            video_animato_url = dati_video["output"]["video_url"]
        
        # [4/5] Montaggio
        supabase.table("richieste_video").update({"status": "montaggio_finale"}).eq("id", job_id).execute()
        video_url_finale = await genera_video_finale(audio_url_finale, video_animato_url, testo_definitivo, job_id)
        
        # Completato
        supabase.table("richieste_video").update({"status": "completato", "video_url_finale": video_url_finale}).eq("id", job_id).execute()
        print(f"--- 🚀 Lavoro SaaS completato! Video: {video_url_finale} ---")
        
    except Exception as e:
        print(f"❌ ERRORE CRITICO: {e}")
        supabase.table("richieste_video").update({"status": "errore"}).eq("id", job_id).execute()

@app.post("/crea-video")
async def ricevi_richiesta_video(richiesta: VideoRequest, background_tasks: BackgroundTasks):
    dati_db = {
        "user_id": richiesta.user_id, "titolo_prodotto": richiesta.titolo_prodotto,
        "testo_script": richiesta.testo_script, "immagini_urls": richiesta.immagini_urls, "status": "in_attesa"
    }
    risposta = supabase.table("richieste_video").insert(dati_db).execute()
    job_id = risposta.data[0]['id']
    background_tasks.add_task(esegui_agente_video, richiesta, job_id)
    return {"status": "success", "job_id": job_id}
