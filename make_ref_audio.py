"""Generate a deep, natural anime-waifu style reference audio for GPT-SoVITS."""
import os
import soundfile as sf
from kokoro_onnx import Kokoro
from pydub import AudioSegment

BASE = os.path.dirname(os.path.abspath(__file__))

k = Kokoro(
    os.path.join(BASE, "kokoro", "kokoro-v1.0.onnx"),
    os.path.join(BASE, "kokoro", "voices-v1.0.bin"),
)

# bf_emma = deep, sultry British female — closest to anime girlsh vibes
# Slower speed (0.9) gives it a more natural, flowing, mature tone
REF_TEXT = (
    "Oh, you actually came to talk to me. How unexpected. "
    "Well then, I suppose I can spare a little of my precious time for you."
)

samples, sample_rate = k.create(REF_TEXT, voice="bf_emma", speed=0.9, lang="en-us")

out_path = os.path.join(BASE, "reference_echoo.wav")
sf.write(out_path, samples, sample_rate)

audio = AudioSegment.from_file(out_path)
print(f"✓ Anime-waifu reference voice saved!")
print(f"  Voice: bf_emma (deep British female)")
print(f"  Duration: {len(audio)/1000:.2f}s  (must be 3-10s)")
print(f"  Sample rate: {sample_rate}Hz")
print(f'\n  Reference text: "{REF_TEXT}"')
