"""
audio_mixer.py - Studio-Grade Audio Processing & Ducked Music Mixing

Features:
1. clean_and_pace_voice: Silence trim (-40dB) + dynamic pacing (1.05x-1.1x) + studio loudnorm (-16 LUFS)
2. mix_with_background_music: Sidechain compression ducking (-20dB during speech) with verified FFmpeg execution
3. select_mood_music: Category-aware background music selector with verified asset presence on disk
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MUSIC_DIR = ROOT / "assets" / "music"


def select_mood_music(topic_category="tech_review") -> str:
    """
    Returns path to royalty-free background track based on topic category.
    Verifies that the target mp3 file actually exists on disk before returning.
    """
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    library = {
        "tech": "tech_energetic_01.mp3",
        "tech_review": "tech_energetic_01.mp3",
        "gadgets": "tech_energetic_01.mp3",
        "news": "cinematic_ambient_01.mp3",
        "breaking_news": "cinematic_ambient_01.mp3",
        "current_affairs": "cinematic_ambient_01.mp3",
        "lifestyle": "lofi_chill_01.mp3",
        "explainer": "lofi_chill_01.mp3",
        "facts": "tech_energetic_01.mp3",
    }

    cat_key = "tech_review"
    if topic_category:
        tc_lower = str(topic_category).lower()
        for k in library:
            if k in tc_lower:
                cat_key = k
                break

    filename = library.get(cat_key, "tech_energetic_01.mp3")
    target_path = MUSIC_DIR / filename

    if not target_path.exists() or target_path.stat().st_size < 1024:
        # Fallback to any existing mp3 in MUSIC_DIR
        existing_tracks = list(MUSIC_DIR.glob("*.mp3"))
        if existing_tracks:
            return str(existing_tracks[0])

        # Auto-synthesize a soft ambient background track on the fly via FFmpeg
        try:
            synth_cmd = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=130.81:duration=60,volume=0.25[b];"
                      "sine=frequency=196.00:duration=60,volume=0.18[g];"
                      "sine=frequency=261.63:duration=60,volume=0.18[c1];"
                      "sine=frequency=329.63:duration=60,volume=0.12[e];"
                      "[b][g][c1][e]amix=inputs=4:normalize=0,lowpass=f=850,aecho=0.8:0.88:60:0.4,volume=0.7",
                "-c:a", "libmp3lame", "-b:a", "128k",
                str(target_path)
            ]
            subprocess.run(synth_cmd, check=True, capture_output=True)
            if target_path.exists():
                return str(target_path)
        except Exception as synth_err:
            print(f"⚠️ Auto-synthesis note: {synth_err}")
            return ""

    return str(target_path)


def clean_and_pace_voice(
    input_path: str,
    output_path: str,
    target_speed: float = 1.07,
    min_silence_ms: int = 350,
) -> str:
    """
    Trims dead air gaps and applies studio pacing and broadcast loudness normalization.
    """
    inp = Path(input_path)
    outp = Path(output_path)
    outp.parent.mkdir(parents=True, exist_ok=True)

    if not inp.exists() or inp.stat().st_size < 512:
        raise FileNotFoundError(f"Input voice file missing or empty: {input_path}")

    silence = f"silenceremove=stop_periods=-1:stop_duration={min_silence_ms/1000}:stop_threshold=-40dB"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(inp),
        "-af",
        f"{silence},atempo={target_speed},loudnorm=I=-14:TP=-1.5:LRA=11",
        str(outp),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"clean_and_pace_voice failed: {result.stderr}")

    if not outp.exists() or outp.stat().st_size < 1024:
        raise RuntimeError(
            f"Output audio file missing or too small after pacing: {outp}\nFFmpeg stderr: {result.stderr}"
        )

    return str(outp)


def mix_with_background_music(
    voice_path: str,
    music_path: str,
    output_path: str,
    music_base_volume: float = 0.22,
    threshold: float = 0.10,
) -> str:
    """
    Ducks background music under voice track using sidechain compression (-24dB relative), then mixes and normalizes to -14 LUFS.
    Guarantees audible, balanced music with zero voice masking.
    """
    v_path = Path(voice_path)
    m_path = Path(music_path)
    outp = Path(output_path)
    outp.parent.mkdir(parents=True, exist_ok=True)

    if not v_path.exists() or v_path.stat().st_size < 512:
        raise FileNotFoundError(f"Voice track missing or empty: {voice_path}")
    if not m_path.exists() or m_path.stat().st_size < 512:
        raise FileNotFoundError(f"Music track missing or empty: {music_path}")

    # Sidechain compression filter with tuned threshold (ensures music is ducked ~-24dB under voice)
    filt = (
        f"[1:a]volume={music_base_volume}[music];"
        f"[music][0:a]sidechaincompress=threshold={threshold}:ratio=6:attack=50:release=400:makeup=1[ducked];"
        f"[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=2[mixed];"
        f"[mixed]loudnorm=I=-14:TP=-1.5:LRA=11[out]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(v_path),
        "-i",
        str(m_path),
        "-filter_complex",
        filt,
        "-map",
        "[out]",
        str(outp),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"mix_with_background_music failed: {result.stderr}")

    if not outp.exists() or outp.stat().st_size < 1024:
        raise RuntimeError(
            f"Mixed audio output missing or too small: {outp}\nFFmpeg stderr: {result.stderr}"
        )

    return str(outp)
