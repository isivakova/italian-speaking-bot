"""
Italian Speaking Practice — Voice Reply Listener
=================================================
Flask webhook: receives voice messages from Telegram,
sends audio to Claude for transcription + assessment,
replies with structured feedback.
Deploy on Render.com (free tier).
"""

import os
import base64
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_API       = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

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

def download_audio_b64(file_url: str) -> str:
    """Download audio and return as base64 string."""
    resp = requests.get(file_url, timeout=60)
    return base64.standard_b64encode(resp.content).decode("utf-8")

# ── Claude: transcribe + assess in one call ───────────────────────────────────

def transcribe_and_assess(audio_b64: str) -> tuple[str, str]:
    """Send audio to Claude — transcribe AND assess in one API call."""

    prompt = """Sei un insegnante di italiano esperto per studenti di livello B2.

Questo è un messaggio vocale in italiano di una studentessa. Per favore:

PRIMA trascrivi esattamente quello che ha detto (anche con errori), poi fornisci il feedback.

Rispondi in questo formato esatto:

📝 TRASCRIZIONE:
[scrivi qui la trascrizione esatta]

━━━━━━━━━━━━━━━━━━━━
🎓 FEEDBACK

1. 📊 VALUTAZIONE GENERALE
[1-2 frasi positive e incoraggianti]

2. ❌ ERRORI E CORREZIONI (massimo 5)
Per ogni errore:
❌ Errore: [frase/parola sbagliata]
✅ Corretto: [versione corretta]
💡 Perché: [spiegazione breve]

3. 📈 3 PUNTI PER MIGLIORARE IL VOCABOLARIO
[parola usata] → [alternativa B2] + esempio breve

Scrivi tutto in italiano. Sii costruttivo e incoraggiante."""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1200,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "audio/ogg",
                        "data": audio_b64,
                    },
                },
                {
                    "type": "text",
                    "text": prompt,
                }
            ],
        }],
    }

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers, json=body, timeout=120,
    )
    resp.raise_for_status()
    full_response = resp.json()["content"][0]["text"].strip()

    # Split transcription from feedback
    if "FEEDBACK" in full_response:
        parts = full_response.split("━━━━━━━━━━━━━━━━━━━━", 1)
        transcription_part = parts[0].replace("📝 TRASCRIZIONE:", "").strip()
        feedback_part = parts[1].strip() if len(parts) > 1 else full_response
    else:
        transcription_part = ""
        feedback_part = full_response

    return transcription_part, feedback_part

# ── Webhook ───────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"ok": True})

    message = data.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))

    if chat_id != TELEGRAM_CHAT_ID:
        return jsonify({"ok": True})

    if "voice" in message:
        send_message(chat_id,
            "🎙️ <b>Ho ricevuto il tuo messaggio vocale!</b>\n\n"
            "⏳ Sto analizzando la tua risposta con Claude...\n"
            "<i>Ci vorranno circa 30 secondi.</i>"
        )
        try:
            file_id  = message["voice"]["file_id"]
            file_url = get_file_url(file_id)
            audio_b64 = download_audio_b64(file_url)

            transcription, feedback = transcribe_and_assess(audio_b64)

            if transcription:
                send_message(chat_id,
                    f"📝 <b>La tua risposta:</b>\n\n<i>{transcription}</i>"
                )

            send_message(chat_id,
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🎓 <b>FEEDBACK</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n{feedback}"
            )

        except Exception as e:
            send_message(chat_id,
                f"❌ Si è verificato un errore: {str(e)}\n"
                "Riprova tra qualche minuto."
            )

    elif "text" in message:
        text = message.get("text", "").lower()
        if text in ("/start", "ciao", "hello", "hi"):
            send_message(chat_id,
                "🇮🇹 <b>Benvenuta!</b>\n\n"
                "Sono il tuo assistente per la pratica orale in italiano.\n"
                "Ogni giorno riceverai una domanda — rispondi con un messaggio "
                "vocale e ti darò un feedback dettagliato! 🎙️"
            )

    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def health():
    return "Italian Speaking Practice Bot is running! 🇮🇹"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
