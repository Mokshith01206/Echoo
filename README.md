# Echoo - Sweet AI Desktop Companion

Echoo is a sweet, caring, and emotionally supportive AI desktop companion that can also automate tasks on your Windows PC. Featuring a web interface with a 3D VRM model, speech recognition (STT), custom voice synthesis (TTS), and system-level task execution.

---

## Features

- **Sweet & Caring Persona:** Echoo acts as a lovely, supportive companion who is always encouraging, empathetic, and ready to listen.
- **Speech & Voice Interaction:**
  - **Speech-to-Text (STT):** Speak directly to Echoo using your microphone.
  - **Custom TTS (GPT-SoVITS):** Ultra-realistic, expressive voice synthesis driven by a locally-hosted GPT-SoVITS API.
- **PC Automation & Control:**
  - **Open & Close Apps:** Instantly control Chrome, Spotify, Notepad, Paint, Calculator, VLC, VS Code, and MS Office applications (Word, Excel, PowerPoint).
  - **Typing & Keyboard Hotkeys:** Type text into active windows and trigger system hotkeys (e.g., `Ctrl+C`, `Ctrl+V`, `Alt+F4`, etc.).
  - **Media & Volume:** Adjust system volume (up, down, mute).
  - **Browser Actions & Web Search:** Search the web or play YouTube videos automatically.
  - **Linways Auto-Evaluation:** Automatically fills out and submits Linways evaluation forms via browser DevTools automation.
- **Web Interface:**
  - Interactive web dashboard (`web.html`) with a custom 3D avatar (`ECHOOi.vrm`).
  - Supports animations, user input logging, and multiple quick interactions.

---

## Tech Stack

- **Backend:** Python, Flask, Flask-CORS
- **AI Brain:** Groq API (`llama-3.3-70b-versatile`)
- **Speech recognition:** SpeechRecognition (Google STT API), PyAudio
- **TTS Engine:** GPT-SoVITS (v2/v3) API
- **Ref Audio Generator:** Kokoro-ONNX, soundfile, pydub
- **Automation:** PyAutoGUI, pyperclip, pywin32
- **Frontend:** HTML5, CSS3, JavaScript (Three.js/VRM Loader for 3D avatar)

---

## Setup & Installation

### 1. Prerequisites
- **Python 3.10+** (ensure it's added to your system PATH)
- **Windows OS** (required for PyAutoGUI, Winsound, and PyWin32 automation)
- **GPT-SoVITS v3** local package (configured in startup scripts)

### 2. Installation
Clone the repository:
```bash
git clone https://github.com/Mokshith01206/Echoo.git
cd Echoo
```

Create a virtual environment and install the dependencies:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Environment Variables Setup
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_groq_api_key_here
GPT_SOVITS_URL=http://127.0.0.1:9880
```

---

## Voice & TTS Setup

1. Make sure your local **GPT-SoVITS** server is available.
2. In the setup files, update the paths in `start_echoo.bat` and `start_voice_api.bat` to point to your local GPT-SoVITS install directory:
   ```cmd
   cd /d "C:\Users\<Your_User>\Downloads\GPT-SoVITS-v3lora-20250228"
   ```
3. Use `make_ref_audio.py` to generate or test reference voices for GPT-SoVITS using Kokoro ONNX.

---

## How to Run

You can start the entire stack using the launcher scripts:

1. **Double-click `start_echoo.bat`**
   - This cleans up stuck ports, launches the GPT-SoVITS server in background, waits for initialization, and runs the Echoo Python Flask server.
2. **Open the Interface:**
   - Double-click `web.html` or navigate to `http://localhost:5000` (if serving static files from Flask) to interact with the 3D web character.
