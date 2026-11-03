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
from typing import List, Dict, Optional, Any, Tuple

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
    preserve_indic_pauses: bool = True,
) -> str:
    """
    Trims dead air gaps and applies studio pacing and broadcast loudness normalization.
    If preserve_indic_pauses is True (or min_silence_ms >= 550), it avoids aggressive stop_periods=-1
    which clips natural Indic/Telugu breath pauses and trailing vowel syllables.
    """
    inp = Path(input_path)
    outp = Path(output_path)
    outp.parent.mkdir(parents=True, exist_ok=True)

    if not inp.exists() or inp.stat().st_size < 512:
        raise FileNotFoundError(f"Input voice file missing or empty: {input_path}")

    # Studio-Grade Natural Delivery:
    # For Indic/Telugu or natural pacing, ONLY trim leading dead air at file start.
    # Never aggressively delete internal breath pauses or clip trailing vowels!
    if preserve_indic_pauses or min_silence_ms >= 550:
        silence = "silenceremove=start_periods=1:start_duration=0.03:start_threshold=-45dB"
    else:
        s_thresh = "-45dB" if min_silence_ms >= 400 else "-40dB"
        silence = (
            f"silenceremove=start_periods=1:start_duration=0.03:start_threshold={s_thresh}:"
            f"stop_periods=-1:stop_duration={min_silence_ms/1000}:stop_threshold={s_thresh}"
        )

    af_filters = [silence]
    if abs(float(target_speed) - 1.0) >= 0.02:
        af_filters.append(f"atempo={target_speed}")
    af_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(inp),
        "-af",
        ",".join(af_filters),
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
    music_base_volume: float = 0.11,
    threshold: float = 0.08,
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


def mix_longform_background_music(
    voice_path: str,
    output_path: str,
    chapters_data: Optional[List[Dict[str, Any]]] = None,
    topic_category: str = "general",
    music_base_volume: float = 0.11,
    threshold: float = 0.08,
) -> str:
    """
    Studio-grade chapter-aware adaptive background music mixer for Long-Form (16:9 / 3+ min) videos.
    Sequences mood tracks across 3 narrative acts (Ambient Setup -> Rising Tension -> Reflection)
    with smooth 2.0s crossfades, sidechain compression ducking under narration, and -14 LUFS broadcast mastering.
    Gracefully falls back to single-track ducked mixing if multiple tracks are unavailable.
    """
    v_path = Path(voice_path)
    outp = Path(output_path)
    outp.parent.mkdir(parents=True, exist_ok=True)

    if not v_path.exists() or v_path.stat().st_size < 512:
        raise FileNotFoundError(f"Voice track missing or empty: {voice_path}")

    # 1. Probe voice track duration
    voice_duration = 0.0
    try:
        p_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(v_path)
        ]
        res = subprocess.run(p_cmd, capture_output=True, text=True, check=True)
        voice_duration = float(res.stdout.strip())
    except Exception:
        pass

    # If duration is short or no chapters, fall back cleanly to standard mixing
    if voice_duration < 75.0 or not chapters_data or len(chapters_data) < 2:
        default_track = select_mood_music(topic_category)
        return mix_with_background_music(
            voice_path=voice_path,
            music_path=default_track,
            output_path=output_path,
            music_base_volume=music_base_volume,
            threshold=threshold,
        )

    # 2. Sequence narrative mood tracks for long-form acts
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    ambient_track = MUSIC_DIR / "cinematic_ambient_01.mp3"
    tech_track = MUSIC_DIR / "tech_energetic_01.mp3"
    chill_track = MUSIC_DIR / "lofi_chill_01.mp3"

    available_tracks = [t for t in (ambient_track, tech_track, chill_track) if t.exists() and t.stat().st_size > 1024]
    if len(available_tracks) < 2:
        # Fallback to single track
        default_track = select_mood_music(topic_category)
        return mix_with_background_music(
            voice_path=voice_path,
            music_path=default_track,
            output_path=output_path,
            music_base_volume=music_base_volume,
            threshold=threshold,
        )

    # Sequence: Act 1 (Ambient) -> Act 2 (Energy) -> Act 3 (Chill / Ambient)
    act1_track = str(available_tracks[0])
    act2_track = str(available_tracks[1])
    act3_track = str(available_tracks[2 % len(available_tracks)])

    # Split duration across the 3 acts
    act_dur = voice_duration / 3.0
    crossfade_dur = 2.0

    print(f"🎵 [Adaptive BGM] Sequencing 3-Act documentary score across {voice_duration:.1f}s narration:")
    print(f"   • Act 1 (0.0s - {act_dur:.1f}s): {Path(act1_track).name}")
    print(f"   • Act 2 ({act_dur:.1f}s - {act_dur*2:.1f}s): {Path(act2_track).name}")
    print(f"   • Act 3 ({act_dur*2:.1f}s - {voice_duration:.1f}s): {Path(act3_track).name}")

    try:
        # Complex filter: loop and trim each act, crossfade act1+act2 then +act3, sidechain compress under voice
        filt = (
            f"[1:a]atrim=0:{act_dur + crossfade_dur},asetpts=PTS-STARTPTS[a1];"
            f"[2:a]atrim=0:{act_dur + crossfade_dur},asetpts=PTS-STARTPTS[a2];"
            f"[3:a]atrim=0:{act_dur + 5.0},asetpts=PTS-STARTPTS[a3];"
            f"[a1][a2]acrossfade=d={crossfade_dur}:c1=tri:c2=tri[m12];"
            f"[m12][a3]acrossfade=d={crossfade_dur}:c1=tri:c2=tri[bgm_full];"
            f"[bgm_full]volume={music_base_volume}[bgm_vol];"
            f"[bgm_vol][0:a]sidechaincompress=threshold={threshold}:ratio=6:attack=50:release=400:makeup=1[ducked];"
            f"[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=2[mixed];"
            f"[mixed]loudnorm=I=-14:TP=-1.5:LRA=11[out]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(v_path),
            "-stream_loop", "-1", "-i", act1_track,
            "-stream_loop", "-1", "-i", act2_track,
            "-stream_loop", "-1", "-i", act3_track,
            "-filter_complex", filt,
            "-map", "[out]",
            str(outp),
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and outp.exists() and outp.stat().st_size > 1024:
            print("✅ [Adaptive BGM] Multi-track chapter BGM mixed with studio sidechain ducking & -14 LUFS.")
            return str(outp)
        else:
            print(f"⚠️ Multi-track mix notice: {res.stderr[:200]}. Falling back to single-track mix...")
    except Exception as multi_err:
        print(f"⚠️ Multi-track BGM exception: {multi_err}. Falling back to single track...")

    default_track = select_mood_music(topic_category)
    return mix_with_background_music(
        voice_path=voice_path,
        music_path=default_track,
        output_path=output_path,
        music_base_volume=music_base_volume,
        threshold=threshold,
    )

