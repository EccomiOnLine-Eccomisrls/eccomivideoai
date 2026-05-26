# Usa un'immagine ufficiale di Python leggera
FROM python:3.10-slim

# Installa FFmpeg nel sistema operativo
RUN apt-get update && apt-get install -y ffmpeg

# Imposta la cartella di lavoro
WORKDIR /app

# Copia i requisiti e installali
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il resto del codice
COPY . .

# Comando per avviare il server sulla porta richiesta da Render
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
