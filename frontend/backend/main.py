# main.py — Day 11 (robust error handling + graceful fallbacks, Py3.13-safe)

import io
import os
import uuid
import logging
from collections import defaultdict
from typing import List, Dict

import requests
from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Try to use pydub, but DO NOT crash if missing (Py3.13 lacks audioop)
HAVE_PYDUB = True
try:
    from pydub import AudioSegment
    from pydub.generators import Sine
except Exception as _e:
    HAVE_PYDUB = False
    AudioSegment = None  # type: ignore
    Sine = None  # type: ignore

# External SDKs
import assemblyai as aai
import google.generativeai as genai

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("day11")

# -----------------------------------------------------------------------------
# Environment (DO NOT crash server if a key is missing — Day 11)
# -----------------------------------------------------------------------------
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY")
MURF_API_KEY       = os.getenv("MURF_API_KEY")
DEFAULT_MURF_VOICE_ID = os.getenv("MURF_VOICE_ID", "en-UK-hazel")

if ASSEMBLYAI_API_KEY:
    aai.settings.api_key = ASSEMBLYAI_API_KEY
else:
    log.warning("ASSEMBLYAI_API_KEY is NOT set — STT will fall back.")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    log.warning("GEMINI_API_KEY is NOT set — LLM will fall back.")

if not MURF_API_KEY:
    log.warning("MURF_API_KEY is NOT set — TTS will fall back to a tone/text.")

if not HAVE_PYDUB:
    log.warning("pydub/audioop not available (likely Python 3.13). "
                "Will skip local audio conversions and stitching.")

# -----------------------------------------------------------------------------
# FastAPI app + CORS + static
# -----------------------------------------------------------------------------
app = FastAPI(title="Day 11 — Error Handling Voice Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten if needed
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# -----------------------------------------------------------------------------
# In‑memory chat history (prototype)
# -----------------------------------------------------------------------------
CHAT_HISTORY: Dict[str, List[Dict[str, str]]] = defaultdict(list)

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def split_text_for_murf(text: str, limit: int = 3000) -> List[str]:
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]

    out, cur = [], ""
    import re
    sentences = re.split(r"(?<=[\.\?\!])\s+", text)
    for s in sentences:
        if len(cur) + len(s) + (1 if cur else 0) <= limit:
            cur = (cur + " " + s).strip()
        else:
            if cur:
                out.append(cur)
            while len(s) > limit:
                out.append(s[:limit])
                s = s[limit:]
            cur = s
    if cur:
        out.append(cur)
    return out


def murf_generate_url(text: str, voice_id: str) -> str:
    """
    Call Murf /v1/speech/generate and return an audio URL.
    On error, raise; caller will handle fallback.
    """
    if not MURF_API_KEY:
        raise RuntimeError("MURF_API_KEY missing")

    url = "https://api.murf.ai/v1/speech/generate"
    headers = {
        "api-key": MURF_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "voiceId": voice_id,
        "text": text,
        "format": "mp3",
        "sampleRate": 24000,
        "style": "Conversational",
    }
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Murf failed {r.status_code}: {r.text}")
    data = r.json()
    audio_url = data.get("audioFile") or data.get("audioUrl") or data.get("data", {}).get("audioFile")
    if not audio_url:
        raise RuntimeError(f"Murf response missing audio URL: {data}")
    return audio_url


def download_mp3(url: str):
    """Return AudioSegment if pydub is present; else return (bytes, 'mp3')."""
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    if HAVE_PYDUB:
        return AudioSegment.from_file(io.BytesIO(r.content), format="mp3")
    return r.content, "mp3"


def save_audiosegment(seg) -> str:
    """
    Save either an AudioSegment or (bytes, 'mp3') into /static and return /static path.
    """
    out_name = f"reply_{uuid.uuid4().hex}.mp3"
    out_path = os.path.join(STATIC_DIR, out_name)

    if HAVE_PYDUB and isinstance(seg, type(AudioSegment.silent())):  # AudioSegment
        seg.export(out_path, format="mp3")
    else:
        # seg is (bytes, 'mp3')
        data = seg[0] if isinstance(seg, tuple) else seg
        with open(out_path, "wb") as f:
            f.write(data)

    return f"/static/{out_name}"


def fallback_tone_mp3() -> str:
    """
    Generate a short audible tone as a TTS fallback when Murf is unavailable.
    If pydub is not available, return an empty string (frontend will still show text).
    """
    if not HAVE_PYDUB:
        log.warning("Cannot generate tone fallback without pydub; returning empty audio_url.")
        return ""
    tone = Sine(440).to_audio_segment(duration=600).apply_gain(-6)  # 0.6s tone
    silence = AudioSegment.silent(duration=200)
    combined = tone + silence + tone
    return save_audiosegment(combined)

# -----------------------------------------------------------------------------
# Health & simple test endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/__test/assembly")
def test_assembly():
    try:
        r = requests.get(
            "https://api.assemblyai.com/v2/account",
            headers={"Authorization": ASSEMBLYAI_API_KEY or ""},
            timeout=15,
        )
        return {"ok": r.ok, "status": r.status_code}
    except Exception as e:
        raise HTTPException(500, f"AssemblyAI test failed: {e}")

@app.get("/__test/gemini")
def test_gemini():
    try:
        if not GEMINI_API_KEY:
            return {"ok": False, "detail": "GEMINI_API_KEY missing"}
        model = genai.GenerativeModel("gemini-1.5-flash")
        out = model.generate_content("Say OK")
        text = (getattr(out, "text", None) or out.candidates[0].content.parts[0].text).strip()
        return {"ok": True, "reply": text}
    except Exception as e:
        raise HTTPException(500, f"Gemini test failed: {e}")

@app.get("/__test/murf")
def test_murf():
    try:
        url = murf_generate_url("This is a Murf test.", DEFAULT_MURF_VOICE_ID)
        return {"ok": True, "audio_url": url}
    except Exception as e:
        raise HTTPException(500, f"Murf test failed: {e}")

# -----------------------------------------------------------------------------
# History endpoints
# -----------------------------------------------------------------------------
@app.get("/agent/history/{session_id}")
def get_history(session_id: str):
    return {"session_id": session_id, "messages": CHAT_HISTORY.get(session_id, [])}

@app.delete("/agent/history/{session_id}")
def clear_history(session_id: str):
    CHAT_HISTORY.pop(session_id, None)
    return {"session_id": session_id, "cleared": True}

# -----------------------------------------------------------------------------
# Main chat endpoint (Day 10 pipeline + Day 11 fallbacks)
# -----------------------------------------------------------------------------
@app.post("/agent/chat/{session_id}")
async def agent_chat(
    session_id: str,
    file: UploadFile = File(...),
    voiceId: str | None = Query(default=None, description="Optional Murf voiceId"),
):
    """
    Flow:
      1) Audio -> (WAV 16k mono if pydub available; otherwise raw bytes)
      2) STT (AssemblyAI)  -> fallback transcript if missing
      3) Append 'user' to history
      4) LLM (Gemini) with history -> fallback message if LLM fails
      5) Append 'assistant' to history
      6) TTS (Murf) -> stitch when pydub is present, else return Murf URL
      7) Return JSON with transcript, llm_text, audio_url
    """
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(400, "No audio data received.")

        # --- 1) Convert to WAV only if pydub exists; else send raw bytes to STT
        wav_bytes = raw
        if HAVE_PYDUB:
            try:
                audio_in = AudioSegment.from_file(io.BytesIO(raw))
            except Exception:
                # MediaRecorder default in browsers is often webm
                audio_in = AudioSegment.from_file(io.BytesIO(raw), format="webm")
            wav_io = io.BytesIO()
            audio_in.set_frame_rate(16000).set_channels(1).export(wav_io, format="wav")
            wav_bytes = wav_io.getvalue()

        # --- 2) STT with fallback ---
        transcript_text = ""
        try:
            if not ASSEMBLYAI_API_KEY:
                raise RuntimeError("ASSEMBLYAI_API_KEY missing")
            transcriber = aai.Transcriber()
            # AssemblyAI accepts bytes; we give it wav if we have it, else raw
            transcript_obj = transcriber.transcribe(wav_bytes)
            transcript_text = (transcript_obj.text or "").strip()
            if not transcript_text:
                raise RuntimeError("Empty transcript from STT")
        except Exception as e:
            log.error("STT error: %s", e)
            transcript_text = "(Sorry, I couldn't transcribe that.)"

        # Save user message
        CHAT_HISTORY[session_id].append({"role": "user", "content": transcript_text})

        # --- 3) LLM with fallback ---
        llm_text = ""
        try:
            if not GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY missing")
            model = genai.GenerativeModel("gemini-1.5-flash")

            # Build short prompt from last ~8 messages
            history = CHAT_HISTORY[session_id][-8:]
            convo_lines = []
            for m in history:
                who = "User" if m["role"] == "user" else "Assistant"
                convo_lines.append(f"{who}: {m['content']}")
            prompt = (
                "You are a friendly, concise voice assistant. Keep replies under 120 words.\n\n"
                + "\n".join(convo_lines)
                + "\nAssistant:"
            )

            out = model.generate_content(prompt)
            llm_text = (getattr(out, "text", None) or out.candidates[0].content.parts[0].text).strip()
            if not llm_text:
                raise RuntimeError("Empty LLM response")
        except Exception as e:
            log.error("LLM error: %s", e)
            llm_text = "I'm having trouble connecting right now. Please try again in a moment."

        # Save assistant message
        CHAT_HISTORY[session_id].append({"role": "assistant", "content": llm_text})

        # --- 4) TTS with fallback ---
        audio_url = ""
        try:
            parts = split_text_for_murf(llm_text, 3000)
            voice = voiceId or DEFAULT_MURF_VOICE_ID

            if HAVE_PYDUB:
                # Download each part, stitch locally, serve from /static
                segments = []
                for p in parts:
                    seg = download_mp3(murf_generate_url(p, voice))
                    segments.append(seg if HAVE_PYDUB else None)  # type: ignore

                combined = segments[0]
                for seg in segments[1:]:
                    combined += seg  # type: ignore

                audio_url = save_audiosegment(combined)
            else:
                # No pydub: just return the first Murf URL (frontend supports absolute URLs)
                audio_url = murf_generate_url(parts[0], voice)
        except Exception as e:
            log.error("TTS error: %s", e)
            # Fallback: short tone if we can, else no audio (text reply still returned)
            audio_url = fallback_tone_mp3()

        return {
            "session_id": session_id,
            "transcript": transcript_text,
            "llm_text": llm_text,
            "audio_url": audio_url,
        }

    except HTTPException:
        raise
    except Exception as e:
        log.exception("Unexpected server error")
        raise HTTPException(500, f"Server error: {e}")