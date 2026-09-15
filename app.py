"""
Italian Speaking Practice — Voice Reply Listener
=================================================
A Flask webhook that:
1. Receives voice messages from Telegram
2. Downloads and transcribes with Whisper
3. Sends transcription to Claude for B2 assessment
4. Replies with structured feedback via Telegram

Deploy on Railway.app (free tier).
"""

import os
import json
import tempfile
import requests
import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ── Telegram helpers ──────────────────────────────────────────────────────────

def send_message(chat_id: str, text: str):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }, timeout=30)

def get_file_url(file_id: str) -> str:
    resp = requests.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id})
    file_path = resp.json()["result"]["file_path"]
    return f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

def download_audio(file_url: str, dest_path: str):
    resp = requests.get(file_url, timeout=60)
    with open(dest_path, "wb") as f:
        f.write(resp.content)

# ── Whisper transcription ─────────────────────────────────────────────────────

def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio using local Whisper (free)."""
    # Install whisper if not present
    try:
        import whisper
    except ImportError:
        subprocess.run(["pip", "install", "openai-whisper"], check=True)
        import whisper

    model = whisper.load_model("base")
    result = model.transcribe(audio_path, language="it")
    return result["text"].strip()

# ── Claude assessment ─────────────────────────────────────────────────────────

def assess_with_claude(transcription: str) -> str:
    """Send transcription to Claude for B2 Italian assessment."""

    prompt = f"""Sei un insegnante di italiano esperto per studenti di livello B2.
Uno studente ha risposto a una domanda in italiano. Ecco la sua risposta trascritta:

---
{transcription}
---

Fornisci un feedback strutturato in italiano con queste sezioni:

1. 📊 VALUTAZIONE GENERALE (1-2 frasi positive, incoraggianti)

2. ❌ ERRORI E CORREZIONI (massimo 5 errori più importanti)
Per ogni errore:
- ❌ Errore: [la frase/parola sbagliata]
- ✅ Corretto: [la versione corretta]
- 💡 Perché: [spiegazione breve — grammatica, tempo verbale, vocabolario]

3. 📈 3 PUNTI PER MIGLIORARE IL VOCABOLARIO
- Suggerisci 3 parole o espressioni più sofisticate per sostituire quelle usate
- Formato: "[parola usata]" → "[alternativa B2]" + esempio breve

Sii specifico, costruttivo e incoraggiante. Scrivi tutto in italiano."""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()

# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"ok": True})

    message = data.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))

    # Only respond to your own chat
    if chat_id != TELEGRAM_CHAT_ID:
        return jsonify({"ok": True})

    # Handle voice messages
    if "voice" in message:
        send_message(chat_id,
            "🎙️ <b>Ho ricevuto il tuo messaggio vocale!</b>\n\n"
            "⏳ Sto trascrivendo e analizzando la tua risposta...\n"
            "<i>Ci vorranno 2-3 minuti.</i>"
        )

        try:
            # Download audio
            file_id  = message["voice"]["file_id"]
            file_url = get_file_url(file_id)

            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                tmp_path = tmp.name
            download_audio(file_url, tmp_path)

            # Transcribe
            send_message(chat_id, "🔤 <i>Trascrizione in corso...</i>")
            transcription = transcribe_audio(tmp_path)
            os.unlink(tmp_path)

            if not transcription:
                send_message(chat_id,
                    "❌ Non sono riuscito a trascrivere l'audio.\n"
                    "Prova a registrare in un posto più silenzioso."
                )
                return jsonify({"ok": True})

            # Show transcription
            send_message(chat_id,
                f"📝 <b>La tua risposta:</b>\n\n<i>{transcription}</i>\n\n"
                "🤖 <i>Sto analizzando con Claude...</i>"
            )

            # Assess with Claude
            feedback = assess_with_claude(transcription)

            # Send feedback
            send_message(chat_id,
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🎓 <b>FEEDBACK</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{feedback}"
            )

        except Exception as e:
            send_message(chat_id,
                f"❌ Si è verificato un errore: {str(e)}\n"
                "Riprova tra qualche minuto."
            )

    # Handle text messages (optional friendly response)
    elif "text" in message:
        text = message["text"].lower()
        if text in ("/start", "ciao", "hello", "hi"):
            send_message(chat_id,
                "🇮🇹 <b>Benvenuta Ingrid!</b>\n\n"
                "Sono il tuo assistente per la pratica orale in italiano.\n\n"
                "Ogni giorno riceverai una domanda a cui rispondere "
                "con un messaggio vocale. Ti darò poi un feedback dettagliato!\n\n"
                "A domani! 🎙️"
            )

    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def health():
    return "Italian Speaking Practice Bot is running! 🇮🇹"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
