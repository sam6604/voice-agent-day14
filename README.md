# AI Conversational Voice Agent
*Built during the #30DaysofVoiceAgents Challenge by Murf AI*

This project records your voice in the browser, transcribes it with *AssemblyAI, gets a response from **Google Gemini, and speaks the reply with **Murf AI*.  
It also keeps *chat history* and has *error handling* so the app stays usable even when an API fails.

---

## Folder Structure

Project_day12/
README.md
backend/
main.py
static/
frontend/
index.html
script.js
style.css
screenshots/
ui.png

---

## Tech Stack
- *FastAPI* (Python) — API server
- *AssemblyAI* — Speech-to-Text (STT)
- *Google Gemini* — Large Language Model (LLM)
- *Murf AI* — Text-to-Speech (TTS)
- *Pydub + FFmpeg* — audio processing (optional)
- *HTML/CSS/JavaScript* — frontend UI

---

## Architecture
1. *Frontend*
   - Records mic audio → sends to backend
   - Plays the AI reply audio automatically

2. *Backend*
   - /agent/chat/{session_id}: STT → LLM → TTS → returns audio URL + transcript + LLM text
   - /agent/history/{session_id}: view/clear chat history
   - __test/*: individual API test endpoints

3. *APIs*
   - AssemblyAI (transcription)
   - Google Gemini (response generation)
   - Murf AI (voice synthesis)

---

## Setup (Windows, Drive-D)

### 1) Backend Setup
Open *PowerShell* in:

D:\30 days of voice agent\Project_day12\backend

Create & activate virtual environment (Python 3.12 recommended):
```powershell
py -3.12 -m venv .venv_d12
.\.venv_d12\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install fastapi uvicorn requests assemblyai google-generativeai python-multipart
# Optional (for advanced audio stitching)
# pip install pydub
# Install FFmpeg and add to PATH if using pydub

Set environment variables (don’t paste actual keys in screenshots):

$env:ASSEMBLYAI_API_KEY="your_assemblyai_key_here"
$env:GEMINI_API_KEY="your_gemini_key_here"
$env:MURF_API_KEY="your_murf_key_here"
$env:MURF_VOICE_ID="en-UK-hazel"   # or your preferred voice

Run server:

uvicorn main:app --reload



⸻

2) Frontend Setup

Open another PowerShell in:

D:\30 days of voice agent\Project_day12\frontend

Serve the files:

python -m http.server 5500

Open in browser:

http://127.0.0.1:5500/index.html



⸻

Quick Tests

Open these while the backend is running:
	•	http://127.0.0.1:8000/health → { "ok": true }
	•	http://127.0.0.1:8000/__test/assembly → STT test
	•	http://127.0.0.1:8000/__test/gemini → LLM test
	•	http://127.0.0.1:8000/__test/murf → TTS test

Then use the UI:
	1.	Click Record → speak → Stop
	2.	You should see transcript + LLM reply text
	3.	Hear AI voice reply (or fallback tone if TTS unavailable)

⸻

Error Handling (Day 11)
	•	If STT fails → safe transcript fallback appears
	•	If LLM fails → friendly default message
	•	If TTS fails → short tone plays so the UI doesn’t feel stuck

⸻

Screenshot

Add a screenshot in screenshots/ and reference it here:

![UI Screenshot](screenshots/ui.png)



⸻

Credits
	•	Murf AI
	•	AssemblyAI
	•	Google Gemini
Challenge: #30DaysofVoiceAgents / #BuildwithMurf

---

