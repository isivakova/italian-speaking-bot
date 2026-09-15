"""
Italian Speaking Practice — Voice Reply Listener
=================================================
Flask webhook: receives voice messages from Telegram,
transcribes with OpenAI Whisper API (~$0.006/min),
assesses with Claude, replies with structured feedback.
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
OPENAI_API_KEY     = os.environ["OPENAI_API_KEY"]
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

# ── Transcribe with OpenAI Whisper ────────────────────────────────────────────

def transcribe_audio(file_url: str) -> str:
    """Download Telegram OGG audio and transcribe with OpenAI Whisper."""
    audio_resp = requests.get(file_url, timeout=60)
    
    # Send to OpenAI Whisper API
    resp = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        files={"file": ("voice.ogg", audio_resp.content, "audio/ogg")},
        data={"model": "whisper-1", "language": "it"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["text"].strip()

# ── Assess with Claude ────────────────────────────────────────────────────────

def assess_with_claude(transcription: str) -> str:
    prompt = f"""Sei un insegnante di italiano esperto per studenti di livello B2.
Uno studente ha risposto a una domanda in italiano. Ecco la sua risposta trascritta:

---
{transcription}
---

Fornisci un feedback strutturato in italiano con queste sezioni:

1. 📊 VALUTAZIONE GENERALE
[1-2 frasi positive e incoraggianti]

2. ❌ ERRORI E CORREZIONI (massimo 5 errori più importanti)
Per ogni errore:
❌ Errore: [frase/parola sbagliata]
✅ Corretto: [versione corretta]
💡 Perché: [spiegazione breve — grammatica, tempo verbale, vocabolario]

3. 📈 3 PUNTI PER MIGLIORARE IL VOCABOLARIO
[parola usata] → [alternativa B2] + esempio breve

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
        headers=headers, json=body, timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()

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
            "⏳ Sto trascrivendo e analizzando...\n"
            "<i>Ci vorranno circa 30 secondi.</i>"
        )
        try:
            file_id  = message["voice"]["file_id"]
            file_url = get_file_url(file_id)

            transcription = transcribe_audio(file_url)

            if not transcription:
                send_message(chat_id,
                    "❌ Non sono riuscito a trascrivere l'audio.\n"
                    "Prova a registrare in un posto più silenzioso."
                )
                return jsonify({"ok": True})

            send_message(chat_id,
                f"📝 <b>La tua risposta:</b>\n\n<i>{transcription}</i>\n\n"
                "🤖 <i>Sto analizzando con Claude...</i>"
            )

            feedback = assess_with_claude(transcription)
            send_message(chat_id,
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🎓 <b>FEEDBACK</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n{feedback}"
            )

        except Exception as e:
            send_message(chat_id,
                f"❌ Si è verificato un errore: {str(e)[:200]}\n"
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
