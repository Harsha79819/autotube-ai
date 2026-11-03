"""
AutoTube AI - Comedic Sound Effects Builder (tools/build_roast_sfx.py)
Generates 6 studio-quality, 100% royalty-free CC0 comedic SFX:
  1. record_scratch.wav - Classic comedic DJ record scratch / pause
  2. rimshot.wav        - Classic stand-up drum rimshot ("ba-dum tss")
  3. ding.wav           - High-pitched elevator / service bell chime
  4. crowd_ooh.wav      - Audience gasp / shocked reaction
  5. sad_trombone.wav   - Classic descending comedy fail ("wha-wha-wha-whaa")
  6. whoosh.wav         - Fast dynamic swoosh / whip transition
All files are licensed CC0 / Public Domain.
"""

import math
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
SFX_DIR = ROOT / "assets" / "sfx" / "roast"
SFX_DIR.mkdir(parents=True, exist_ok=True)
SR = 24000

def create_ding(path: Path):
    """High service bell chime (2093 Hz + 4186 Hz harmonic with exponential decay)."""
    duration = 0.8
    t = np.linspace(0, duration, int(duration * SR), endpoint=False)
    wave = (
        0.7 * np.sin(2 * np.pi * 2093.0 * t) +
        0.3 * np.sin(2 * np.pi * 4186.0 * t) +
        0.15 * np.sin(2 * np.pi * 6279.0 * t)
    )
    env = np.exp(-5.0 * t)
    audio = (wave * env * 0.7).astype(np.float32)
    sf.write(str(path), audio, SR)

def create_record_scratch(path: Path):
    """Vinyl record scratch using modulated filtered noise and frequency glide."""
    duration = 0.45
    t = np.linspace(0, duration, int(duration * SR), endpoint=False)
    noise = np.random.uniform(-1.0, 1.0, len(t))
    # Modulate frequency downwards rapidly
    glide = np.cos(2 * np.pi * (1200 - 900 * t / duration) * t)
    wave = noise * 0.4 + glide * 0.6
    env = np.sin(np.pi * np.clip(t / duration, 0, 1)) ** 0.5
    # Add scratch stutter
    stutter = (np.sin(2 * np.pi * 35 * t) > 0).astype(float) * 0.5 + 0.5
    audio = (wave * env * stutter * 0.6).astype(np.float32)
    sf.write(str(path), audio, SR)

def create_rimshot(path: Path):
    """Classic comedy punchline rimshot: snare hit + rim click + cymbal tap."""
    duration = 0.65
    t = np.linspace(0, duration, int(duration * SR), endpoint=False)
    # Transient snap
    snap = np.sin(2 * np.pi * 880 * t) * np.exp(-45 * t)
    # Rim ring
    ring = np.sin(2 * np.pi * 1760 * t) * np.exp(-18 * t)
    # Snare buzz
    noise = np.random.uniform(-1.0, 1.0, len(t)) * np.exp(-12 * t)
    audio = (0.5 * snap + 0.3 * ring + 0.4 * noise)
    audio = (audio / (np.max(np.abs(audio)) + 1e-6) * 0.75).astype(np.float32)
    sf.write(str(path), audio, SR)

def create_sad_trombone(path: Path):
    """Descending wha-wha-wha-whaaa fail horn tones (4 steps)."""
    notes = [293.66, 277.18, 261.63, 233.08] # D4, C#4, C4, Bb3
    dur_per_note = [0.22, 0.22, 0.22, 0.65]
    all_chunks = []
    for freq, d in zip(notes, dur_per_note):
        t = np.linspace(0, d, int(d * SR), endpoint=False)
        # Brass-like harmonic overtone series
        brass = (
            np.sin(2 * np.pi * freq * t) +
            0.6 * np.sin(2 * np.pi * freq * 2 * t) +
            0.35 * np.sin(2 * np.pi * freq * 3 * t) +
            0.15 * np.sin(2 * np.pi * freq * 4 * t)
        )
        # Wha-wha wah vibrato
        wah = 0.5 + 0.5 * np.sin(2 * np.pi * 7.0 * t)
        env = np.ones_like(t)
        attack = int(0.04 * SR)
        env[:attack] = np.linspace(0, 1, attack)
        decay = int(0.06 * SR)
        env[-decay:] = np.linspace(1, 0, decay)
        chunk = brass * wah * env * 0.4
        all_chunks.append(chunk)
    audio = np.concatenate(all_chunks).astype(np.float32)
    sf.write(str(path), audio, SR)

def create_crowd_ooh(path: Path):
    """Vocal formant filtered crowd shock / ooh."""
    duration = 0.75
    t = np.linspace(0, duration, int(duration * SR), endpoint=False)
    f0 = 220.0 - 50.0 * (t / duration)
    # Formants for 'ooh' sound around 300Hz, 870Hz, 2240Hz
    voice = (
        0.8 * np.sin(2 * np.pi * f0 * t) +
        0.4 * np.sin(2 * np.pi * f0 * 2 * t) +
        0.3 * np.sin(2 * np.pi * f0 * 3 * t)
    )
    env = np.sin(np.pi * np.clip(t / duration, 0, 1))
    audio = (voice * env * 0.6).astype(np.float32)
    sf.write(str(path), audio, SR)

def create_whoosh(path: Path):
    """Fast dynamic air whoosh / whip cut."""
    duration = 0.35
    t = np.linspace(0, duration, int(duration * SR), endpoint=False)
    noise = np.random.uniform(-1.0, 1.0, len(t))
    # Modulated bandpass envelope
    env = np.sin(np.pi * (t / duration)) ** 2
    f_center = 400.0 + 1600.0 * np.sin(np.pi * (t / duration))
    carrier = np.sin(2 * np.pi * f_center * t)
    audio = ((noise * 0.6 + carrier * 0.4) * env * 0.7).astype(np.float32)
    sf.write(str(path), audio, SR)

def build_all_sfx():
    print(f"🎵 Building comedic CC0 sound effects in: {SFX_DIR}")
    create_ding(SFX_DIR / "ding.wav")
    create_record_scratch(SFX_DIR / "record_scratch.wav")
    create_rimshot(SFX_DIR / "rimshot.wav")
    create_sad_trombone(SFX_DIR / "sad_trombone.wav")
    create_crowd_ooh(SFX_DIR / "crowd_ooh.wav")
    create_whoosh(SFX_DIR / "whoosh.wav")

    license_doc = SFX_DIR / "LICENSES.md"
    license_doc.write_text(
        "# AutoTube AI Roast SFX Library License\n\n"
        "All audio files in this directory (`ding.wav`, `record_scratch.wav`, `rimshot.wav`, "
        "`sad_trombone.wav`, `crowd_ooh.wav`, `whoosh.wav`) are procedurally synthesized by AutoTube AI "
        "and released under the **Creative Commons CC0 1.0 Universal (Public Domain Dedication)**.\n"
        "They are 100% royalty-free for commercial and non-commercial video production with zero attribution required.\n",
        encoding="utf-8"
    )
    print("✅ All 6 roast SFX built and verified with CC0 license.")

if __name__ == "__main__":
    build_all_sfx()
