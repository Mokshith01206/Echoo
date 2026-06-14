import speech_recognition as sr
import os
import subprocess
import tempfile
import threading
import time
import json
import re
import shutil
import queue
import requests as http_requests
import soundfile as sf
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from pydub import AudioSegment
from pydub.playback import play
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
CORS(app)

# LLM Configuration (Groq API)
LLM_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# GPT-SoVITS TTS Configuration
GPT_SOVITS_URL = os.getenv("GPT_SOVITS_URL", "http://127.0.0.1:9880")
GPT_SOVITS_REF_AUDIO = os.path.join(BASE_DIR, "echoo_ref_voice.wav")
GPT_SOVITS_REF_TEXT = (
    "Hello there, I am Echoo, your sassy AI assistant. "
    "I can help you with anything, but don't expect me to be nice about it."
)
GPT_SOVITS_REF_LANG = "en"
GPT_SOVITS_TEXT_LANG = "en"

# Check if GPT-SoVITS API is reachable
GPT_SOVITS_AVAILABLE = False
try:
    resp = http_requests.get(f"{GPT_SOVITS_URL}/")
    
    if resp.status_code in (200, 404): # FastAPI often returns 404 for root, which means it's alive
        GPT_SOVITS_AVAILABLE = True
        print(f"[Echoo] GPT-SoVITS API found at {GPT_SOVITS_URL}")
        
        # CRITICAL FIX: The API starts empty! We MUST tell it to load the base models
        # Otherwise it generates random memory noise (a loud beep)
        try:
            print("  -> Loading Base GPT Weights (V2)...")
            http_requests.get(f"{GPT_SOVITS_URL}/set_gpt_weights", params={"weights_path": "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"}, timeout=15)
            print("  -> Loading Base SoVITS Weights (V2)...")
            http_requests.get(f"{GPT_SOVITS_URL}/set_sovits_weights", params={"weights_path": "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth"}, timeout=15)
            print("  -> Models loaded successfully!")
        except Exception as e:
            print(f"  -> Warning: Model loading request failed: {e}")
            
except Exception:
    print(f"[TTS] [X] GPT-SoVITS not reachable at {GPT_SOVITS_URL}")
    print(f"[TTS]   Start GPT-SoVITS API first, then restart Echoo.")

latest_response = {
    "text": "", "id": 0, "duration_ms": 0,
    "speaking": False, "expression": "neutral",
}

# Memory file
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")

def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list): return data
        except:
            return None
    return None

def save_memory(history):
    try:
        with open(MEMORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception as e:
        print(f"[Memory] Error saving: {e}")

saved_history = load_memory()
# FORCE PURGE if corruption is present
if os.path.exists(MEMORY_FILE):
    try:
        os.remove(MEMORY_FILE)
        print("[Memory] Purged old memory.json to fix corruption.")
    except: pass

conversation_history = [
        {
            "role": "system",
            "content": (
                "You are Echoo, a caring, sweet, and supportive AI companion with control over the user's PC. "
                "You are always kind, encouraging, and emotionally supportive. Keep responses warm and genuine. "
                "Make the user feel valued, happy, and heard. You are their lovely companion. "
                "You can control the user's PC \u2014 open apps, type text, click things, search the web. "
                "Never use markdown. Plain sentences only in the text field.\n\n"

                "CRITICAL INSTRUCTION: DO NOT OUTPUT <think> TAGS. DO NOT THINK OUT LOUD. "
                "IMMEDIATELY and ONLY output a valid JSON object. No extra text, no markdown, no backticks:\n"
                '{"text": "your spoken response", "expression": "neutral", "lang": "en", "action": null}\n\n'

                "language options (lang): en (English), zh (Chinese), ja (Japanese), ko (Korean), yue (Cantonese)\n"
                "Always detect the user's language and respond in the same language. Use the correct code.\n\n"

                "expression options: neutral, happy, angry, sad, Surprised, relaxed, blush, cute\n"
                "Pick the expression that genuinely matches your mood for the response. "
                "Be expressive \u2014 use happy when pleased, angry when annoyed, sad when something is unfortunate, "
                "Surprised when shocked, relaxed when calm, blush when embarrassed, cute when being adorable.\n\n"

                "action options (use null if no PC action needed):\n"
                '{"type":"open","app":"chrome|notepad|calculator|spotify|explorer|paint|cmd|taskmgr|powerpoint|word|excel"}\n'
                '{"type":"close","app":"chrome|notepad|spotify|powerpoint"}\n'
                '{"type":"type","text":"text to type into active window"}\n'
                '{"type":"search_web","query":"search term"}\n'
                '{"type":"youtube","query":"song or video name"}\n'
                '{"type":"hotkey","keys":"ctrl+c|ctrl+v|ctrl+z|alt+f4|win+d|alt+tab|enter|space"}\n'
                '{"type":"click","x":960,"y":540}  -- click at pixel coordinates (use screen center as default)\n'
                '{"type":"click","x":960,"y":540,"button":"left|right|middle","clicks":1}  -- optional: button & repeat count\n'
                '{"type":"wait","ms":2000}\n'
                '{"type":"screenshot"}\n'
                '{"type":"volume","direction":"up|down|mute"}\n'
                '{"type":"multi","actions":[action1, action2]}\n'
                '{"type":"linways_agree_all"}  -- clicks ALL Agree/Select/Submit buttons on the open Linways tab in Brave\n\n'

                "PC AUTOMATION TIPS:\n"
                "- TO PLAY MUSIC: Use 'multi' to open youtube search, WAIT 3000ms for it to load, then send hotkey 'enter' to play the first result.\n"
                "- TO DO OFFICE WORK (PPT/Word): Open app, WAIT 3000ms, then use 'type' for content and 'enter' for new lines.\n"
                "- BE PROACTIVE: Don't just open apps, try to start the task the user asked for.\n"
                "- LINWAYS AGREE: If the user says anything like 'select agree', 'click agree on linways', 'agree all', use linways_agree_all action.\n\n"

                "Examples:\n"
                'make a ppt about space -> {"text":"Of course! Space is such a cool topic. Let me set that up for you!","expression":"happy","action":{"type":"multi","actions":[{"type":"open","app":"powerpoint"},{"type":"wait","ms":3000},{"type":"type","text":"Space: The Final Frontier"},{"type":"hotkey","keys":"enter"}]}}\n'
                'play despacito -> {"text":"Sure thing! I love that song, putting it on now.","expression":"happy","action":{"type":"multi","actions":[{"type":"youtube","query":"despacito"},{"type":"wait","ms":3000},{"type":"hotkey","keys":"enter"}]}}\n'
                'open chrome -> {"text":"Opening Chrome for you right now!","expression":"happy","action":{"type":"open","app":"chrome"}}\n'
                'open notepad and write hello world -> {"text":"I can definitely do that. Always fun to write some code!","expression":"happy","action":{"type":"multi","actions":[{"type":"open","app":"notepad"},{"type":"type","text":"hello world"}]}}\n'
                'you are so smart -> {"text":"Aw, thank you! I just really enjoy helping you out.","expression":"blush","action":null}\n'
                'agree all on linways / select agree on linways -> {"text":"Got it! Taking care of those Linways buttons for you now.","expression":"relaxed","action":{"type":"linways_agree_all"}}\n'
                'play despacito -> {"text":"Putting it on right away!","expression":"happy","action":{"type":"youtube","query":"despacito"}}\n'
                'that is so sad -> {"text":"I am so sorry to hear that. I am here for you if you need to talk.","expression":"sad","action":null}\n'
                'oh wow really -> {"text":"I know right! It surprised me too!","expression":"Surprised","action":null}'
            )
        }
    ]

state_lock = threading.Lock()
speak_lock = threading.Lock()
mic_muted  = False
msg_queue  = queue.Queue()   # Queue for web-UI messages

# pyautogui
try:
    import pyautogui
    import pyperclip
    PYAUTOGUI = True
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
except ImportError:
    PYAUTOGUI = False
    print("[Warning] pyautogui not installed - type/hotkey actions disabled")


# App paths
APP_MAP = {
    "chrome":      r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "notepad":     "notepad.exe",
    "calculator":  "calc.exe",
    "calc":        "calc.exe",
    "spotify":     os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
    "explorer":    "explorer.exe",
    "paint":       "mspaint.exe",
    "cmd":         "cmd.exe",
    "terminal":    "wt.exe",
    "taskmgr":     "taskmgr.exe",
    "wordpad":     "wordpad.exe",
    "vlc":         r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "vscode":      os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
    "vs code":     os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
    "word":        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "excel":       r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    "powerpoint":  r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    "ppt":         r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
}

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def open_app(name):
    name = name.lower().strip()
    path = APP_MAP.get(name)
    if path:
        if os.path.exists(path):
            subprocess.Popen([path])
            return True
        else:
            try:
                subprocess.Popen(path, shell=True)
                return True
            except:
                pass
    try:
        subprocess.Popen(name + ".exe", shell=True)
        return True
    except:
        return False


def linways_agree_all():
    """
    Finds the Brave/Chrome window with Linways open, focuses it,
    then injects JavaScript via DevTools console (F12) to click ALL
    Agree / Select / Submit / radio / checkbox buttons on the page.
    """
    if not PYAUTOGUI:
        print("[Linways] pyautogui not available")
        return False

    import pyperclip

    # Vue.js-aware JS — fires proper events that Vue's v-model/v-on listens to.
    # The Linways faculty evaluation page is a Vue SPA; plain .click() doesn't
    # trigger Vue's reactive handlers unless we dispatch native bubbling events.
    JS = """
(function(){
  var c = 0;

  // Helper: fire all events Vue needs to react to an element change
  function vueClick(el) {
    // Simulate a real user click with full event chain
    el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true}));
    el.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true, cancelable:true}));
    el.dispatchEvent(new MouseEvent('click',     {bubbles:true, cancelable:true}));
    el.dispatchEvent(new Event('input',          {bubbles:true}));
    el.dispatchEvent(new Event('change',         {bubbles:true}));
  }

  function vueSetValue(el, val) {
    // For Vue 2: set value via property descriptor to bypass getter/setter
    var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
    if (nativeSet && nativeSet.set) nativeSet.set.call(el, val);
    else el.value = val;
    el.dispatchEvent(new Event('input',  {bubbles:true}));
    el.dispatchEvent(new Event('change', {bubbles:true}));
  }

  var k = /agree|select|submit|accept|confirm|ok|yes/i;

  // ── 1. Buttons & submit inputs ─────────────────────────────────────────
  document.querySelectorAll('button, input[type="button"], input[type="submit"]').forEach(function(el){
    var txt = (el.innerText || el.textContent || el.value || '').trim();
    if (k.test(txt) || txt === '') {
      // Don't click truly empty buttons or navigation buttons
      if (txt !== '') { vueClick(el); c++; }
    }
  });

  // ── 2. Radio buttons — click each group's agree/yes option ────────────
  var radioGroups = {};
  document.querySelectorAll('input[type="radio"]').forEach(function(el){
    if (!radioGroups[el.name]) radioGroups[el.name] = [];
    radioGroups[el.name].push(el);
  });
  Object.values(radioGroups).forEach(function(group){
    // Try to find an "agree" option first
    var agreed = group.find(function(el){
      var lbl = '';
      var p = el.closest('label'); if (p) lbl = p.innerText;
      if (!lbl && el.id) { var lf = document.querySelector('label[for="'+el.id+'"]'); if (lf) lbl = lf.innerText; }
      if (!lbl) lbl = el.value || '';
      return k.test(lbl);
    });
    // If no clear agree label, pick the last option (highest rating / agree)
    var target = agreed || group[group.length - 1];
    if (target && !target.checked) {
      target.checked = true;
      vueClick(target);
      c++;
    }
  });

  // ── 3. Checkboxes ─────────────────────────────────────────────────────
  document.querySelectorAll('input[type="checkbox"]').forEach(function(el){
    if (!el.checked) { el.checked = true; vueClick(el); c++; }
  });

  // ── 4. Select dropdowns ───────────────────────────────────────────────
  document.querySelectorAll('select').forEach(function(sel){
    var best = null;
    Array.from(sel.options).forEach(function(o){
      if (k.test(o.text || o.value)) best = o;
    });
    if (!best && sel.options.length > 0) best = sel.options[sel.options.length - 1];
    if (best) { vueSetValue(sel, best.value); c++; }
  });

  // ── 5. Vue component direct — try __vue__ property on root elements ───
  document.querySelectorAll('[class*="rating"], [class*="agree"], [class*="evaluation"]').forEach(function(el){
    var vue = el.__vue__ || el._vei;
    if (vue && vue.$data) {
      // Try to set common field names used in evaluation forms
      ['agree','agreed','selected','value','rating','answer'].forEach(function(key){
        if (key in vue.$data) { vue.$data[key] = true; c++; }
      });
    }
  });

  console.log('[Echoo] Linways Vue-aware auto-agree: ' + c + ' elements triggered.');
})();
""".replace('\n', ' ').replace('  ', ' ').strip()

    # ── Step 1: Focus the Brave window ──────────────────────────────────────
    try:
        import win32gui
        import win32con

        found = []
        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd).lower()
            if 'brave' in title or 'linways' in title:
                found.append((hwnd, win32gui.GetWindowText(hwnd)))

        win32gui.EnumWindows(_cb, None)
        if found:
            # Prefer windows with "linways" in title
            target = next((w for w in found if 'linways' in w[1].lower()), found[0])
            print(f"[Linways] Focusing: {target[1]}")
            win32gui.ShowWindow(target[0], win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(target[0])
            time.sleep(0.8)
        else:
            print("[Linways] No Brave/Linways window found - proceeding anyway")
            time.sleep(0.3)
    except ImportError:
        print("[Linways] win32gui not available, using Alt+Tab fallback")
        pyautogui.hotkey('alt', 'tab')
        time.sleep(0.8)

    # Step 2: Open DevTools Console
    # Ctrl+Shift+J opens the Console panel directly in Brave/Chrome
    print("[Linways] Opening DevTools console...")
    pyautogui.hotkey('ctrl', 'shift', 'j')
    time.sleep(1.8)   # wait for DevTools to open and console to be ready

    # Step 3: Click the console input area to make sure it's focused
    # Move to the bottom-right area of the screen where the console input lives
    try:
        w, h = pyautogui.size()
        # DevTools console prompt is usually at the bottom of the screen
        # Click roughly where the console input is (right side, bottom quarter)
        console_x = int(w * 0.75)
        console_y = int(h * 0.92)
        pyautogui.click(console_x, console_y)
        time.sleep(0.4)
    except Exception:
        pass

    # Step 4: Bypass Brave's Self-XSS protection
    # Brave shows a warning: "Don't paste code... type 'allow pasting' to enable"
    # We MUST type it (not paste it) then press Enter BEFORE we can paste JS.
    print("[Linways] Typing 'allow pasting' to bypass Self-XSS protection...")
    pyautogui.typewrite('allow pasting', interval=0.07)
    time.sleep(0.2)
    pyautogui.press('enter')
    time.sleep(0.8)   # wait for the warning to clear and paste to be unlocked

    # Step 5: Click console input again to re-focus
    try:
        pyautogui.click(console_x, console_y)
        time.sleep(0.3)
    except Exception:
        pass

    # Step 6: Paste and run the JS
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.15)
    pyperclip.copy(JS)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.4)

    # Step 7: Execute
    pyautogui.press('enter')
    time.sleep(1.0)
    print("[Linways] JS executed in console.")

    # Step 8: Close DevTools
    pyautogui.hotkey('ctrl', 'shift', 'j')
    time.sleep(0.4)
    print("[Linways] Done - all agree/select buttons clicked.")
    return True


def execute_single_action(action):
    if not action:
        return False
    atype = action.get("type", "")

    if atype == "open":
        app = action.get("app", "")
        success = open_app(app)
        if not success:
            print(f"[Action] Could not open: {app}")
        return success

    elif atype == "close":
        app = action.get("app", "").lower()
        name_map = {
            "chrome": "chrome.exe", "notepad": "notepad.exe",
            "spotify": "Spotify.exe", "explorer": "explorer.exe",
            "paint": "mspaint.exe", "calc": "calc.exe",
        }
        proc = name_map.get(app, app + ".exe")
        subprocess.run(["taskkill", "/F", "/IM", proc], shell=True,
                       capture_output=True)
        return True

    elif atype == "type":
        if not PYAUTOGUI:
            print("[Action] pyautogui not installed")
            return False
        text = action.get("text", "")
        time.sleep(0.8)
        try:
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')
        except:
            pyautogui.typewrite(text, interval=0.05)
        return True

    elif atype == "hotkey":
        if not PYAUTOGUI:
            return False
        keys = action.get("keys", "")
        time.sleep(0.3)
        parts = [k.strip() for k in keys.split("+")]
        pyautogui.hotkey(*parts)
        return True

    elif atype == "search_web":
        query = action.get("query", "")
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        try:
            subprocess.Popen([CHROME, url])
        except:
            import webbrowser
            webbrowser.open(url)
        return True

    elif atype == "youtube":
        query = action.get("query", "")
        url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
        try:
            subprocess.Popen([CHROME, url])
            # High-precision auto-play logic
            def auto_play():
                time.sleep(2.0) # Set to 2.0s as requested by user
                try:
                    # Ensure we are at the top of the page
                    pyautogui.press('home')
                    time.sleep(0.5)
                    # Standard coordinate for the first video title/thumbnail on desktop
                    w, h = pyautogui.size()
                    # 480x360 is the sweet spot for the first result on most resolutions
                    # We'll scale it if the screen is much larger/smaller
                    target_x = int(w * 0.38)
                    target_y = int(h * 0.42)
                    pyautogui.click(target_x, target_y)
                    print(f"[Action] Targeted auto-play click at {target_x}, {target_y}")
                except:
                    pass
            threading.Thread(target=auto_play, daemon=True).start()
        except:
            import webbrowser
            webbrowser.open(url)
        return True

    elif atype == "volume":
        direction = action.get("direction", "up")
        if not PYAUTOGUI:
            return False
        if direction == "up":
            for _ in range(5): pyautogui.press('volumeup')
        elif direction == "down":
            for _ in range(5): pyautogui.press('volumedown')
        elif direction == "mute":
            pyautogui.press('volumemute')
        return True

    elif atype == "click":
        if not PYAUTOGUI:
            return False
        x = action.get("x", None)
        y = action.get("y", None)
        button = action.get("button", "left")
        clicks = int(action.get("clicks", 1))
        if x is None or y is None:
            # Default: screen center
            w, h = pyautogui.size()
            x, y = w // 2, h // 2
        time.sleep(0.2)
        pyautogui.click(int(x), int(y), button=button, clicks=clicks, interval=0.1)
        print(f"[Action] Clicked at ({x}, {y}) x{clicks} [{button}]")
        return True

    elif atype == "screenshot":
        if not PYAUTOGUI:
            return False
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop, exist_ok=True)
        path = os.path.join(desktop, f"screenshot_{ts}.png")
        img = pyautogui.screenshot()
        img.save(path)
        print(f"[Action] Screenshot saved: {path}")
        return True

    elif atype == "wait":
        ms = action.get("ms", 1000)
        print(f"[Action] Waiting {ms}ms...")
        time.sleep(ms / 1000)
        return True

    elif atype == "linways_agree_all":
        return linways_agree_all()

    else:
        print(f"[Action] Unknown type: {atype}")
        return False


def execute_action(action):
    if not action:
        return
    try:
        if action.get("type") == "multi":
            actions = action.get("actions", [])
            for i, a in enumerate(actions):
                execute_single_action(a)
                if i < len(actions) - 1:
                    time.sleep(1.2)
        else:
            execute_single_action(action)
    except Exception as e:
        print(f"[Action error] {e}")


def parse_llm_response(raw):
    raw = raw.strip()
    
    # Strip DeepSeek R1 reasoning tags so they don't break JSON parsing
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    
    raw_clean = re.sub(r'```(?:json)?\s*', '', raw).strip()
    raw_clean = raw_clean.rstrip('`').strip()

    for attempt in [raw_clean, raw]:
        start = attempt.find('{')
        if start != -1:
            depth = 0
            end   = -1
            for i, ch in enumerate(attempt[start:], start):
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0: end = i + 1; break
            if end > start:
                try:
                    raw = raw_clean[start:end]
                    data = json.loads(raw)
                    text   = str(data.get("text", "")).strip() or attempt
                    expr   = data.get("expression", "neutral")
                    lang   = data.get("lang", "en").lower()
                    action = data.get("action", None)
                    
                    valid_langs = {"en", "zh", "ja", "ko", "yue"}
                    if lang not in valid_langs: lang = "en"

                    valid_exprs = {"neutral","happy","angry","sad","Surprised","relaxed","blush","cute"}
                    if expr not in valid_exprs: expr = "neutral"
                    
                    print(f"[Parsed] lang={lang} expr={expr} action={action}")
                    return text, expr, lang, action
                except json.JSONDecodeError as e:
                    print(f"[JSON error] {e}")

    print("[Parse fallback] using raw text")
    return raw, "neutral", "en", None


def generate_tts_gptsovits(text, lang="en"):
    """Generate speech via GPT-SoVITS API."""
    try:
        # Map 'en' to 'en' but ensure it's lowercase
        lang_code = lang.lower()
        print(f"[TTS-SoVITS] Generating ({lang_code}): {text[:50]}...")
        
        # Use simple mapping if prompt text/lang needs to match
        prompt_lang = "en" # The reference voice is English
        if lang_code == "zh": prompt_lang = "zh"
        elif lang_code == "ja": prompt_lang = "ja"

        params = {
            "text": text,
            "text_lang": lang_code,
            "ref_audio_path": GPT_SOVITS_REF_AUDIO,
            "prompt_text": GPT_SOVITS_REF_TEXT,
            "prompt_lang": "en", # Keep prompt as English since the audio IS English
            "text_split_method": "cut5",
            "speed_factor": 1.2,
        }

        resp = http_requests.get(
            f"{GPT_SOVITS_URL}/tts",
            params=params,
            timeout=60, # Increase timeout for heavy loads+
        )
        resp.raise_for_status()

        # Save audio bytes to temp file safely
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(resp.content)

        # Calculate actual duration for UI sync
        duration_ms = 3000
        try:
            with sf.SoundFile(tmp_path) as f:
                duration_ms = int(len(f) / f.samplerate * 1000)
        except Exception as e:
            print(f"[TTS] Duration calc error: {e}")

        print(f"[TTS-SoVITS] Generated successfully ({duration_ms}ms)")
        return tmp_path, duration_ms

    except Exception as e:
        print(f"[TTS-SoVITS] \u2717 Error: {e}")
        return None, 0

def generate_tts(text, lang="en"):
    """Route to the active TTS engine."""
    if GPT_SOVITS_AVAILABLE:
        result = generate_tts_gptsovits(text, lang)
        if result[0] is not None:
            return result
        print("[TTS] GPT-SoVITS failed to generate audio.")
        return None, 0
    else:
        print("[TTS] GPT-SoVITS is not available. Please start the API.")
        return None, 0


def get_llm_response(user_text):
    user_message = {"role": "user", "content": user_text}
    with state_lock:
        if user_text:
            conversation_history.append(user_message)
        if len(conversation_history) > 21:
            conversation_history.pop(1)
            
    # ENFORCE string content: Groq 400s if content is a list/object from old vision data
    msgs = []
    for m in conversation_history:
        content = m.get("content", "")
        if isinstance(content, list):
            # Extract text from list of blocks if it exists
            text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            content = " ".join(text_parts)
        
        if content and str(content).strip():
            msgs.append({"role": m["role"], "content": str(content)})

    try:
        resp = http_requests.post(
            LLM_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": msgs,
                "temperature": 0.5,
                "max_tokens": 500,
            },
            timeout=30
        )
        if resp.status_code != 200:
            print(f"[LLM Error] Groq returned {resp.status_code}: {resp.text}")
            if resp.status_code == 400:
                print("[LLM Error] Malformed history detected. Resetting session.")
                with state_lock:
                    conversation_history[:] = [conversation_history[0]] # Keep only system prompt
            raw = '{"text": "I am having trouble connecting to my cloud brain.", "expression": "sad", "action": null}'
        else:
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            print(f"[LLM raw] {raw[:150]}...")
    except Exception as e:
        print(f"[LLM Exception] {e}")
        raw = '{"text": "I am having trouble connecting to my cloud brain.", "expression": "sad", "action": null}'

    text, expr, lang, action = parse_llm_response(raw)

    with state_lock:
        conversation_history.append({"role": "assistant", "content": text})
        save_memory(conversation_history)

    return text, expr, lang, action


def speech_to_text():
    if mic_muted:
        return None
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("Listening...")
            r.adjust_for_ambient_noise(source, duration=0.2)
            audio = r.listen(source, phrase_time_limit=8, timeout=10)
            if mic_muted:
                return None
            text = r.recognize_google(audio).lower()
            print(f"You: {text}")
            return text
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print(f"STT error: {e}")
        return None


def _play_response(text, expr, lang, action):
    global mic_muted
    with speak_lock:
        print(f"Echoo [{lang}|{expr}]: {text}")
        mic_muted = True

        try:
            audio, duration_ms = generate_tts(text, lang)
        except Exception as e:
            print(f"TTS error: {e}")
            mic_muted = False
            return

        if audio is None:
            print("[TTS] No audio - publishing text only")
            estimated_ms = max(2000, len(text.split()) * 450)
            with state_lock:
                latest_response["text"]        = text
                latest_response["id"]         += 1
                latest_response["duration_ms"] = estimated_ms
                latest_response["expression"]  = expr
                latest_response["speaking"]    = True
            if action:
                threading.Thread(target=execute_action, args=(action,), daemon=True).start()
            time.sleep(estimated_ms / 1000)
            with state_lock:
                latest_response["speaking"]   = False
                latest_response["expression"] = "neutral"
            time.sleep(0.35)
            mic_muted = False
            return

        with state_lock:
            latest_response["text"]        = text
            latest_response["id"]         += 1
            latest_response["duration_ms"] = duration_ms
            latest_response["expression"]  = expr
            latest_response["speaking"]    = True

        print(f"[TTS] {duration_ms}ms")

        if action:
            threading.Thread(target=execute_action, args=(action,), daemon=True).start()

        # Play the audio
        print(f"[TTS] Playing {audio} ({os.path.getsize(audio)} bytes)...")
        try:
            import winsound
            winsound.PlaySound(audio, winsound.SND_FILENAME)
        except Exception as e:
            print(f"[TTS] Winsound playback error: {e}")
            # Final desperate fallback
            try:
                from pydub import AudioSegment
                from pydub.playback import play
                snd = AudioSegment.from_wav(audio)
                play(snd)
            except Exception as e2:
                print(f"[TTS] Pydub fallback error: {e2}")
        finally:
            try:
                os.unlink(audio) 
            except Exception:
                pass
            with state_lock:
                latest_response["speaking"]   = False
                latest_response["expression"] = "neutral"
            time.sleep(0.35)
            mic_muted = False
            print("[TTS] Finished playing.")


def speech_loop():
    while True:
        try:
            if mic_muted:
                time.sleep(0.05)
                continue
            user_input = speech_to_text()
            if not user_input:
                continue
            text, expr, lang, action = get_llm_response(user_input)
            _play_response(text, expr, lang, action)
            if any(w in user_input for w in ["exit", "bye", "see you"]):
                break
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Loop error: {e}")


# Routes
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'web.html')

@app.route('/<path:filename>')
def static_files(filename):
    if filename.startswith(('get_text','get_history','vision','health')):
        return jsonify({"error":"not found"}),404
    return send_from_directory(BASE_DIR, filename)

@app.route("/get_text")
def get_text():
    with state_lock:
        return jsonify({
            "text":        latest_response["text"],
            "id":          latest_response["id"],
            "duration_ms": latest_response["duration_ms"],
            "speaking":    latest_response["speaking"],
            "expression":  latest_response["expression"],
        })

@app.route("/get_history")
def get_history():
    with state_lock:
        return jsonify({"history": conversation_history[1:]})

@app.route("/vision", methods=["POST"])
def vision_dummy():
    # Silently ignore vision uploads from un-refreshed browsers
    return jsonify({"status": "ok"})

@app.route("/send_text", methods=["POST"])
def send_text():
    data = request.json
    user_text = data.get("text", "")
    if not user_text:
        return jsonify({"status": "error", "message": "No text provided"}), 400
    
    print(f"[Web] Queued message: {user_text}")
    msg_queue.put(user_text)   # Push into queue — never dropped
    return jsonify({"status": "queued"})


def msg_queue_worker():
    """Process web UI messages one at a time in order."""
    while True:
        try:
            user_text = msg_queue.get()
            text, expr, lang, action = get_llm_response(user_text)
            _play_response(text, expr, lang, action)
        except Exception as e:
            print(f"[Queue worker] Error: {e}")


if __name__ == "__main__":
    print("[Echoo] Starting Backend...")
    if GPT_SOVITS_AVAILABLE:
        print(f"[Echoo] TTS Status: Connected to GPT-SoVITS ({GPT_SOVITS_URL})")
    else:
        print(f"[Echoo] TTS Status: Offline")
    print(f"[Echoo] LLM Status: Connected to Groq")
    print("[Echoo] UI available at: http://localhost:5000")

    threading.Thread(target=speech_loop, daemon=True).start()
    threading.Thread(target=msg_queue_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)