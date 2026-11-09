import asyncio
import os
import re
import sys
import time
from pathlib import Path
import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

# Allow online HuggingFace Hub downloads on fresh container deployments if not already cached
if os.getenv("HF_HUB_OFFLINE") is None:
    # Only enable offline mode if local cache already has Kokoro
    pass

try:
    from kokoro import KPipeline
except ImportError:
    KPipeline = None

import soundfile as sf
import subprocess
from supervisor import autonomous_recover


# ============================================================
# STUDIO-GRADE AUDIO PACING, SILENCE REMOVAL & DUCKED MUSIC
# ============================================================

from audio_mixer import clean_and_pace_voice, mix_with_background_music, select_mood_music




# ============================================================
# ENGLISH CREATOR VOICE CONFIG
# ============================================================

KOKORO_VOICE = "af_heart"
KOKORO_LANGUAGE = "a"


# ============================================================
# NUMBER / TTS NORMALIZATION
# ============================================================

def make_tts_text(text):
    """
    Convert numbers, dates, currencies and abbreviations
    into natural speech. Preserves Telugu and Indian scripts naturally
    with specialized tech phonetic normalization.
    """
    if not text:
        return ""

    if re.search(r"[\u0C00-\u0C7F]", text):
        try:
            from edge_tts_generator import prepare_script_for_tts
            text = prepare_script_for_tts(text)
        except Exception:
            pass
        from telugu_phonetic_normalizer import normalize_telugu_tech_script
        text = normalize_telugu_tech_script(text)
        cleaned = re.sub(r"[*_#`~]", "", text)
        cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
        return cleaned

    if re.search(r"[\u0900-\u097F]", text):
        cleaned = re.sub(r"[*_#`~]", "", text)
        cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
        return cleaned

    from num2words import num2words

    def _clean_spoken_words(words: str) -> str:
        # Strip internal commas and 'and' fillers so speech synthesis flows smoothly
        words = re.sub(r",\s*", " ", words)
        words = re.sub(r"\band\b", "", words)
        return re.sub(r"\s+", " ", words).strip()

    def _num_to_words(val: int) -> str:
        try:
            w = num2words(val, lang="en_IN")
        except Exception:
            w = num2words(val, lang="en")
        return _clean_spoken_words(w)

    # --------------------------------------------------------
    # Currencies (Rupees, Dollars, Euros, Pounds)
    # ₹89,999 -> eighty-nine thousand nine hundred ninety-nine rupees
    # $999 -> nine hundred ninety-nine dollars
    # --------------------------------------------------------

    def rupee_replace(match):
        raw = match.group(1).replace(",", "")
        if "." in raw:
            parts = raw.split(".", 1)
            whole = int(parts[0]) if parts[0] else 0
            dec = parts[1]
            if int(dec) == 0:
                words = _num_to_words(whole)
                return f"{words} rupees"
            whole_words = _num_to_words(whole)
            dec_words = " ".join(_num_to_words(int(d)) for d in dec)
            return f"{whole_words} point {dec_words} rupees"
        return f"{_num_to_words(int(raw))} rupees"

    text = re.sub(
        r"(?:₹|Rs\.?|INR)\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?:/-)?",
        rupee_replace,
        text,
        flags=re.IGNORECASE
    )

    def dollar_replace(match):
        raw = match.group(1).replace(",", "")
        if "." in raw:
            parts = raw.split(".", 1)
            whole = int(parts[0]) if parts[0] else 0
            dec = parts[1]
            whole_words = _num_to_words(whole)
            dec_words = " ".join(_num_to_words(int(d)) for d in dec)
            return f"{whole_words} point {dec_words} dollars"
        return f"{_num_to_words(int(raw))} dollars"

    text = re.sub(
        r"(?:\$|USD\s*)\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)",
        dollar_replace,
        text,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # Percentages
    # 5% -> five percent, 12.5% -> twelve point five percent
    # --------------------------------------------------------

    def percent_replace(match):
        raw = match.group(1).replace(",", "")
        if "." in raw:
            parts = raw.split(".", 1)
            whole_words = _num_to_words(int(parts[0])) if parts[0] else "zero"
            dec_words = " ".join(_num_to_words(int(d)) for d in parts[1])
            return f"{whole_words} point {dec_words} percent"
        return f"{_num_to_words(int(raw))} percent"

    text = re.sub(
        r"(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)%",
        percent_replace,
        text
    )

    # --------------------------------------------------------
    # Comma-separated numbers (without currency)
    # 89,999 -> eighty-nine thousand nine hundred ninety-nine
    # 1,50,000 -> one lakh fifty thousand
    # --------------------------------------------------------

    def comma_num_replace(match):
        raw = match.group(0).replace(",", "")
        if "." in raw:
            parts = raw.split(".", 1)
            whole_words = _num_to_words(int(parts[0])) if parts[0] else "zero"
            dec_words = " ".join(_num_to_words(int(d)) for d in parts[1])
            return f"{whole_words} point {dec_words}"
        return _num_to_words(int(raw))

    text = re.sub(
        r"\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b",
        comma_num_replace,
        text
    )

    # --------------------------------------------------------
    # Decimal numbers (without commas)
    # 4.5 -> four point five
    # 2.54 -> two point five four
    # --------------------------------------------------------

    def decimal_replace(match):
        whole = int(match.group(1))
        decimal = match.group(2)
        whole_words = _num_to_words(whole)
        decimal_words = " ".join(_num_to_words(int(digit)) for digit in decimal)
        return f"{whole_words} point {decimal_words}"

    text = re.sub(
        r"\b(\d+)\.(\d+)\b",
        decimal_replace,
        text
    )

    # --------------------------------------------------------
    # Indian financial expressions
    # "five hundred rupees crore" -> "five hundred crore"
    # "two rupees lakh" -> "two lakh"
    # --------------------------------------------------------

    text = re.sub(
        r"\brupees\s+(?=(?:lakh|crore)\b)",
        "",
        text,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # Years
    # 2026 -> twenty twenty-six
    # 2025 -> twenty twenty-five
    # --------------------------------------------------------

    def year_replace(match):
        year = int(match.group(0))
        if 2000 <= year <= 2099:
            last_two = year - 2000
            if last_two == 0:
                return "two thousand"
            if last_two < 10:
                return f"two thousand {_num_to_words(last_two)}"
            return f"twenty {_num_to_words(last_two)}"
        return match.group(0)

    text = re.sub(
        r"\b20\d{2}\b",
        year_replace,
        text
    )

    # --------------------------------------------------------
    # Standalone numbers
    # 5 -> five
    # 45 -> forty-five
    # 500 -> five hundred
    # --------------------------------------------------------

    def number_replace(match):
        number = int(match.group(0))
        return _num_to_words(number)

    text = re.sub(
        r"\b\d+\b",
        number_replace,
        text
    )

    # --------------------------------------------------------
    # Common abbreviations
    # --------------------------------------------------------

    replacements = {
        "AI": "A I",
        "GDP": "G D P",
        "USA": "U S A",
        "UAE": "U A E",
        "UK": "U K",
        "ISRO": "I S R O",
        "NASA": "N A S A",
        "CEO": "C E O",
        "CJI": "C J I",
        "PM": "P M",
        "CM": "C M",
    }

    for old, new in replacements.items():
        text = re.sub(
            rf"\b{re.escape(old)}\b",
            new,
            text,
            flags=re.IGNORECASE
        )

    # --------------------------------------------------------
    # Clean whitespace
    # --------------------------------------------------------

    text = re.sub(
        r"\s+",
        " ",
        text
    )
    # --------------------------------------------------------
    # TTS pronunciation fixes
    # --------------------------------------------------------

    pronunciation_replacements = {
        "Nagarjuna Akkineni": "Nagarjuna Akineni",
        "thirty-three hundred and ten crore rupees":
            "three thousand three hundred and ten crore rupees",
        "crore rupees": "crore rupees",
        "crorerupees": "crore rupees",
        "టెప్పర్ వంశీ": "టెంపర్ వంశీ",
        "టెప్పర్": "టెంపర్",
        "ఆటో ర్యామ్": "ఆటో రామ్",
        "దేబ్జాని": "డెబ్‌జానీ",
        "నీతు నట్రాజ్": "నీతూ నట్రాజ్",
    }

    for old, new in pronunciation_replacements.items():
        text = text.replace(old, new)

    # Remove accidental trailing symbols
    text = re.sub(r"[%]+$", "", text).strip()

    return text

# ============================================================
# XTTS-V2 LOCAL VOICE CLONING MODEL (LAZY LOADED & CACHED)
# ============================================================

_XTTS_MODEL = None


def get_xtts_model():
    """
    Lazy-load and cache the Coqui XTTS-v2 voice cloning model.
    Runs strictly on CPU to prevent Apple Silicon MPS attention divergence and loops.
    """
    global _XTTS_MODEL
    if _XTTS_MODEL is None:
        os.environ["COQUI_TOS_AGREED"] = "1"
        from TTS.api import TTS

        device = "cpu"
        print(f"Loading Coqui XTTS-v2 model on {device}...")
        _XTTS_MODEL = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        print(f"XTTS-v2 loaded successfully on {device}!")

    return _XTTS_MODEL


def synthesize_voice(
    script_text: str,
    reference_sample: str,
    output_wav: str = "output/voice_raw.wav",
    language: str = "te",
    temperature: float = 0.75,
    length_penalty: float = 1.0,
    repetition_penalty: float = 5.0,
    top_k: int = 50,
    top_p: float = 0.85,
    speed: float = 1.0,
):
    """
    Direct synthesis helper with automatic phonetic normalization and tuned XTTS-v2 inference.
    """
    from telugu_phonetic_normalizer import normalize_telugu_tech_script
    safe_text = normalize_telugu_tech_script(script_text) if re.search(r"[\u0C00-\u0C7F]", script_text) else script_text
    return generate_cloned_voice_xtts(
        text=safe_text,
        speaker_wav=reference_sample,
        output_wav=output_wav,
        language=language,
        temperature=temperature,
        length_penalty=length_penalty,
        repetition_penalty=repetition_penalty,
        top_k=top_k,
        top_p=top_p,
        speed=speed,
    )


def generate_cloned_voice_xtts(
    text: str,
    speaker_wav: str,
    output_wav: str,
    language: str = "en",
    temperature: float = 0.75,
    length_penalty: float = 1.0,
    repetition_penalty: float = 5.0,
    top_k: int = 50,
    top_p: float = 0.85,
    speed: float = 1.0,
    base_voice: str = "te-IN-ShrutiNeural",
):
    """
    Clone user's voice using Coqui XTTS-v2 with high-fidelity reference audio sample
    and explicit tuned inference parameters (speed=1.0, natural temperature/pacing).
    """
    global _XTTS_MODEL
    from telugu_phonetic_normalizer import normalize_telugu_tech_script
    safe_text = normalize_telugu_tech_script(text) if re.search(r"[\u0C00-\u0C7F]", text) else text

    if language.lower() in ("te", "telugu"):
        print(f"ℹ️ Note: XTTS-v2 natively supports ['en', 'hi', ...]. Routing Telugu ('te') through cross-lingual FreeVC24 engine (base={base_voice})...")
        import asyncio
        asyncio.run(
            generate_cross_lingual_cloned_voice(
                text=safe_text,
                speaker_wav=speaker_wav,
                output_wav=output_wav,
                base_voice=base_voice,
            )
        )
        return output_wav

    try:
        tts = get_xtts_model()
        print(f"Synthesizing cloned voice with speaker sample: {speaker_wav} (speed={speed}, temp={temperature})")
        tts.tts_to_file(
            text=safe_text,
            speaker_wav=speaker_wav,
            language=language,
            file_path=output_wav,
            split_sentences=True,
            speed=speed,
            temperature=temperature,
            length_penalty=length_penalty,
            repetition_penalty=repetition_penalty,
            top_k=top_k,
            top_p=top_p,
        )
    except Exception as e:
        print(f"XTTS synthesis error: {e}. Retrying on CPU...")
        os.environ["COQUI_TOS_AGREED"] = "1"
        from TTS.api import TTS
        _XTTS_MODEL = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
        _XTTS_MODEL.tts_to_file(
            text=safe_text,
            speaker_wav=speaker_wav,
            language=language,
            file_path=output_wav,
            split_sentences=True,
            speed=speed,
            temperature=temperature,
            length_penalty=length_penalty,
            repetition_penalty=repetition_penalty,
            top_k=top_k,
            top_p=top_p,
        )


_FREEVC_MODEL = None


def get_freevc_model():
    """
    Cache FreeVC24 model globally for zero-shot cross-lingual voice conversion.
    """
    global _FREEVC_MODEL
    if _FREEVC_MODEL is None:
        os.environ["COQUI_TOS_AGREED"] = "1"
        from TTS.api import TTS
        tts = TTS()
        tts.load_vc_model_by_name("voice_conversion_models/multilingual/vctk/freevc24")
        _FREEVC_MODEL = tts
    return _FREEVC_MODEL


async def generate_cross_lingual_cloned_voice(
    text: str,
    speaker_wav: str,
    output_wav: str,
    base_voice: str = "te-IN-ShrutiNeural",
):
    """
    Zero-shot cross-lingual voice cloning for Telugu and non-Latin/Devanagari scripts:
    1. Synthesize pristine, fluent native speech using Edge-TTS neural voice.
    2. Convert vocal identity/timbre to match the English reference speaker sample using FreeVC24.
    """
    temp_native = "output/temp_native_speech.mp3"
    temp_native_wav = "output/temp_native_speech_pcm.wav"
    os.makedirs("output", exist_ok=True)

    # Step 1: Synthesize native Telugu audio directly with phonetic tech normalization
    from telugu_phonetic_normalizer import normalize_telugu_tech_script
    safe_text = normalize_telugu_tech_script(text) if re.search(r"[\u0C00-\u0C7F]", text) else text
    await generate_edge_tts_speech(
        speech_text=safe_text,
        voice_code=base_voice,
        output_mp3=temp_native,
    )

    # Step 2: Convert to 24000Hz mono PCM wav for FreeVC
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            temp_native,
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            temp_native_wav,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Step 3: Zero-shot voice conversion with FreeVC24
    vc_engine = get_freevc_model()
    vc_engine.voice_conversion_to_file(
        source_wav=temp_native_wav,
        target_wav=speaker_wav,
        file_path=output_wav,
    )

    # Clean up intermediate files
    for p in (temp_native, temp_native_wav):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass



_KOKORO_PIPELINE = None


def get_kokoro_pipeline():
    """
    Cache KPipeline globally for ultra-fast, sub-second synthesis.
    Loads strictly from local HuggingFace cache to prevent network/hub errors.
    """
    global _KOKORO_PIPELINE
    if _KOKORO_PIPELINE is None:
        from kokoro import KPipeline, KModel
        from huggingface_hub import hf_hub_download
        import torch

        # Try loading weights from local cache first
        model = None
        try:
            cfg = hf_hub_download(
                repo_id="hexgrad/Kokoro-82M",
                filename="config.json",
                local_files_only=True,
            )
            pth = hf_hub_download(
                repo_id="hexgrad/Kokoro-82M",
                filename="kokoro-v1_0.pth",
                local_files_only=True,
            )
            model = KModel(config=cfg, model=pth).eval()
        except Exception:
            # First-time run on container: download online from HuggingFace Hub
            try:
                model = KModel().eval()
            except Exception as online_err:
                print(f"Kokoro model init notice: {online_err}")
                model = None

        _KOKORO_PIPELINE = KPipeline(
            lang_code=KOKORO_LANGUAGE,
            model=model if model else True,
        )

        # Pre-cache all standard voice tensors locally so KPipeline never calls Hub
        for v_name in ("af_bella", "af_heart", "am_adam", "am_michael"):
            try:
                v_path = hf_hub_download(
                    repo_id="hexgrad/Kokoro-82M",
                    filename=f"voices/{v_name}.pt",
                    local_files_only=True,
                )
                _KOKORO_PIPELINE.voices[v_name] = torch.load(v_path, weights_only=True)
            except Exception:
                pass

    return _KOKORO_PIPELINE


def generate_kokoro_speech(
    speech_text: str,
    voice_code: str = "am_adam",
    output_wav: str = "output/voice_kokoro.wav",
):
    """
    Generate creator speech using Kokoro TTS (fast, zero heat, studio human quality).
    """
    pipeline = get_kokoro_pipeline()

    # Ensure voice is preloaded or safely fall back to an existing loaded voice
    if voice_code not in pipeline.voices:
        from huggingface_hub import hf_hub_download
        import torch
        try:
            v_path = hf_hub_download(
                repo_id="hexgrad/Kokoro-82M",
                filename=f"voices/{voice_code}.pt",
                local_files_only=True,
            )
            pipeline.voices[voice_code] = torch.load(v_path, weights_only=True)
        except Exception as v_err:
            print(f"⚠️ Voice '{voice_code}' not in cache ({v_err}).")
            if pipeline.voices:
                fallback_voice = next(iter(pipeline.voices.keys()))
                print(f"Using cached voice '{fallback_voice}' as fallback.")
                voice_code = fallback_voice

    generator = pipeline(
        speech_text,
        voice=voice_code,
    )

    audio_parts = []
    import numpy as np
    silence_gap = np.zeros(int(24000 * 0.18), dtype=np.float32)

    for _, _, audio in generator:
        audio_parts.append(audio)
        audio_parts.append(silence_gap)

    if not audio_parts:
        raise RuntimeError(
            "Kokoro did not generate any audio."
        )

    full_audio = np.concatenate(
        audio_parts
    )

    sf.write(
        output_wav,
        full_audio,
        24000,
    )


async def generate_edge_tts_speech(
    speech_text,
    voice_code="te-IN-MohanNeural",
    output_mp3="output/voice.mp3",
    rate="+8%",
    pitch="+0Hz",
):
    """Generate high-quality multilingual neural voice using Microsoft Edge-TTS with tuned pacing (+8% / ~1.08x Shorts brisk cadence),
    capturing exact word boundary timestamps directly from the stream."""
    word_timings = []
    import asyncio
    for attempt in range(1, 4):
        try:
            from edge_tts_generator import generate_with_word_boundaries
            _, word_timings = await generate_with_word_boundaries(
                text=speech_text,
                output_path=output_mp3,
                voice=voice_code or "te-IN-MohanNeural",
                rate=rate or "+8%",
                pitch=pitch or "+0Hz",
            )
            if os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000:
                return word_timings
        except Exception as boundary_err:
            print(f"Edge-TTS boundary capture note (attempt {attempt}/3): {boundary_err}. Falling back to standard synthesis...")
            try:
                from edge_tts_generator import generate_telugu_speech
                await generate_telugu_speech(
                    text=speech_text,
                    output_path=output_mp3,
                    voice=voice_code or "te-IN-MohanNeural",
                    rate=rate or "+8%",
                    pitch=pitch or "+0Hz",
                )
                if os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000:
                    return word_timings
            except Exception:
                try:
                    import edge_tts
                    communicate = edge_tts.Communicate(
                        text=speech_text,
                        voice=voice_code or "te-IN-MohanNeural",
                        rate=rate or "+8%",
                        pitch=pitch or "+0Hz",
                    )
                    await communicate.save(output_mp3)
                    if os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000:
                        return word_timings
                except Exception as e_err:
                    if attempt < 3:
                        print(f"Edge-TTS connection retry {attempt}/3 in 1.5s...")
                        await asyncio.sleep(1.5)
                    else:
                        raise e_err

    return word_timings


async def generate_elevenlabs_speech(
    speech_text: str,
    voice_id: str = "21m00Tcm4TlvDq8ikWAM",  # Warm Conversational Default
    output_mp3: str = "output/voice.mp3",
    stability: float = 0.45,
    similarity_boost: float = 0.78,
    style: float = 0.20,
    model_id: str = "eleven_multilingual_v2",
):
    """
    Generate expressive speech via ElevenLabs API following Gemini's persona guidelines:
    - Warm conversational voice
    - Stability: 40-50% (0.45) for natural pitch modulation and inflection
    - Similarity / clarity boost: 0.78 (75-80% sweet spot)
    - Style Exaggeration: 0.20 (15-25% dynamic comedy/roast punch)
    - Model: eleven_multilingual_v2
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        return None

    import urllib.request
    import json

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": speech_text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": True,
        },
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            audio_bytes = resp.read()
            if len(audio_bytes) > 1000:
                os.makedirs(os.path.dirname(os.path.abspath(output_mp3)), exist_ok=True)
                with open(output_mp3, "wb") as f:
                    f.write(audio_bytes)
                print(f"✅ [Voice Agent] ElevenLabs TTS generated successfully: {len(audio_bytes)} bytes.")
                return output_mp3
    except Exception as e:
        print(f"⚠️ ElevenLabs TTS generation notice: {e}. Falling back to default neural engine...")
    return None


async def generate_omnivoice_speech(
    speech_text,
    output_mp3="output/voice.mp3",
    voice_sample=None,
    instruct="natural conversational human voice, warm and relaxed tone, slight vocal variation, not robotic, mid-20s energetic presenter",
):
    """
    OmniVoice zero-shot voice-cloning & voice-design TTS adapter (github.com/k2-fsa/OmniVoice).
    Free, open-weight, runs locally.
    Gracefully falls back to Edge-TTS / Kokoro if omnivoice package is not installed.
    """
    try:
        import omnivoice
        print(f"🎙️ Generating speech via OmniVoice ({'Cloning' if voice_sample else 'Voice Design'})...")
        # If omnivoice package is present, invoke CLI or module
        import subprocess
        cmd = ["omnivoice-infer", "--text", speech_text, "--output", output_mp3]
        if voice_sample and os.path.exists(voice_sample):
            cmd.extend(["--ref-audio", str(voice_sample)])
        elif instruct:
            cmd.extend(["--instruct", instruct])
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000:
            print("✅ OmniVoice generation completed successfully.")
            return []
    except ImportError:
        print("ℹ️ OmniVoice package not installed on this system. Falling back safely to default neural engine...")
    except Exception as e:
        print(f"⚠️ OmniVoice notice: {e}. Falling back to default neural engine...")
    return None


@autonomous_recover("voice_agent")
async def create_voice(
    voice=None,
    rate="+8%",
    pitch="+0Hz",
    voice_sample=None,
    topic_category="tech_review",
    include_music=True,
):
    """
    Create narration using either:
    1. Direct Own Voice Recording (100% genuine user speech, 0s TTS delay, zero heat)
    2. Coqui XTTS-v2 Local Voice Cloning (when voice is 'clone' and audio sample exists)
    3. Kokoro high-quality English creator voices (af_heart, am_adam, am_michael, af_bella)
    """

    os.makedirs(
        "output",
        exist_ok=True,
    )

    output_wav = "output/voice_raw.wav"
    output_mp3 = "output/voice.mp3"
    captured_words = []

    is_own_recording = bool(
        voice
        and (
            "own_recording" in str(voice).lower()
            or "own voice" in str(voice).lower()
            or "own_voice" in str(voice).lower()
            or voice == "own_recording"
        )
    )

    # --------------------------------------------------------
    # 1. DIRECT OWN VOICE RECORDING (Zero TTS Latency, Zero Heat)
    # --------------------------------------------------------
    if is_own_recording:
        recording_candidates = [
            voice_sample,
            "voice_samples/active_voice.wav",
            "voice_samples/active_voice.mp3",
            "voice_samples/active_voice.m4a",
            "voice_samples/user_voice.wav",
            "voice_samples/user_voice.mp3",
            "voice_samples/user_voice.m4a",
            os.path.abspath("voice_samples/active_voice.wav"),
            os.path.abspath("voice_samples/active_voice.mp3"),
            os.path.abspath("voice_samples/active_voice.m4a"),
            os.path.abspath("voice_samples/user_voice.wav"),
            os.path.abspath("voice_samples/user_voice.mp3"),
            os.path.abspath("voice_samples/user_voice.m4a"),
        ]

        selected_recording = None
        for cand in recording_candidates:
            if cand and os.path.exists(cand) and os.path.getsize(cand) > 0:
                selected_recording = cand
                break

        if not selected_recording:
            raise RuntimeError(
                "🎙️ Own Voice Recording was selected, but no audio file was found! "
                "Please upload an audio recording in the dashboard, or select an AI Studio Voice."
            )

        print()
        print("=" * 60)
        print("DIRECT OWN VOICE RECORDING INTEGRATION")
        print("=" * 60)
        print("Audio Source:", selected_recording)
        print("Mode: 100% Genuine User Voice (0s TTS Latency, 0 Laptop Heat)")

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(selected_recording),
                "-ar",
                "44100",
                "-ac",
                "2",
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                output_mp3,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Ensure script.txt and tts_script.txt match the spoken words
        script_path = "output/script.txt"
        tts_script_path = "output/tts_script.txt"

        print("Transcribing user audio with Whisper to sync script with spoken words...")
        try:
            import whisper

            wmodel = whisper.load_model("base")
            wres = wmodel.transcribe(output_mp3, fp16=False)
            spoken_text = wres.get("text", "").strip()
            if spoken_text:
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(spoken_text)
                with open(tts_script_path, "w", encoding="utf-8") as f:
                    f.write(spoken_text)
        except Exception as trans_err:
            print(f"Whisper transcription note: {trans_err}")
            if not os.path.exists(script_path):
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write("User audio voiceover narration.")
                with open(tts_script_path, "w", encoding="utf-8") as f:
                    f.write("User audio voiceover narration.")

        print("Voice created successfully from user recording!")
        print("Saved to:", output_mp3)
        print("=" * 60)
        print()
        return output_mp3

    # --------------------------------------------------------
    # 2. SCRIPT LOADING & NORMALIZATION (For TTS & XTTS)
    # --------------------------------------------------------
    script_path = "output/script.txt"

    if not os.path.exists(script_path):
        print("Script not found!")
        return None

    with open(
        script_path,
        "r",
        encoding="utf-8",
    ) as file:
        text = file.read().strip()

    if not text:
        print("Script is empty!")
        return None

    # Guard: Ensure Romanized Tanglish is converted to native Telugu script (తెలుగు లిపి)
    try:
        from utils.transliterate_telugu import ensure_telugu_script
        tel_script = ensure_telugu_script(text)
        if tel_script != text:
            text = tel_script
            with open(script_path, "w", encoding="utf-8") as file:
                file.write(text)
    except Exception as t_err:
        pass

    # Guard: Guarantee mandatory 3-part CTA (Like, Share, Subscribe) in every narration
    try:
        import re
        from agents.script_agent import ensure_dynamic_outro_cta, deduplicate_script_narration
        is_indic = bool(re.search(r"[\u0C00-\u0C7F]", text))
        cta_text = ensure_dynamic_outro_cta(text, is_indic=is_indic)
        cta_text = deduplicate_script_narration(cta_text)
        if cta_text != text:
            text = cta_text
            with open(script_path, "w", encoding="utf-8") as file:
                file.write(text)
    except Exception:
        pass

    speech_text = make_tts_text(text)

    with open(
        "output/tts_script.txt",
        "w",
        encoding="utf-8",
    ) as file:
        file.write(speech_text)

    is_clone = bool(voice and ("clone" in str(voice).lower() or voice == "clone"))
    speaker_sample_path = None

    if is_clone:
        candidates = [
            voice_sample,
            "voice_samples/active_voice.wav",
            "voice_samples/active_voice.mp3",
            "voice_samples/active_voice.m4a",
            "voice_samples/user_voice.wav",
            "voice_samples/user_voice.mp3",
            "voice_samples/user_voice.m4a",
            os.path.abspath("voice_samples/active_voice.wav"),
            os.path.abspath("voice_samples/active_voice.mp3"),
            os.path.abspath("voice_samples/active_voice.m4a"),
            os.path.abspath("voice_samples/user_voice.wav"),
            os.path.abspath("voice_samples/user_voice.mp3"),
            os.path.abspath("voice_samples/user_voice.m4a"),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                speaker_sample_path = candidate
                break

    is_telugu_text = bool(re.search(r"[\u0C00-\u0C7F]", speech_text))
    # Ensure native Telugu script and phonetically spell English loan words (Rule 4)
    if is_telugu_text or "telugu" in str(voice).lower():
        try:
            from utils.transliterate_telugu import ensure_telugu_script
            speech_text = ensure_telugu_script(speech_text)
            is_telugu_text = bool(re.search(r"[\u0C00-\u0C7F]", speech_text))
        except Exception:
            pass

    is_hindi_text = bool(re.search(r"[\u0900-\u097F]", speech_text))
    voice_lower = str(voice or "").lower()

    is_edge_voice = bool(
        "te-in" in voice_lower
        or "hi-in" in voice_lower
        or "mohan" in voice_lower
        or "shruti" in voice_lower
        or "madhur" in voice_lower
        or "swara" in voice_lower
        or "edge-tts" in voice_lower
        or "roast" in voice_lower
        or "sarcastic" in voice_lower
        or (is_telugu_text and not is_clone)
        or (is_hindi_text and not is_clone)
    )
    t_start_voice = time.time()
    tts_engine_cfg = os.getenv("TTS_ENGINE", "kokoro").strip().lower()
    is_omnivoice = bool("omnivoice" in voice_lower or tts_engine_cfg == "omnivoice")

    used_mode = None

    if is_omnivoice:
        print()
        print("=" * 60)
        print("OMNIVOICE ZERO-SHOT NEURAL TTS GENERATION")
        print("=" * 60)
        print("TTS text preview:")
        print(speech_text[:400])
        print()
        omni_res = await generate_omnivoice_speech(
            speech_text=speech_text,
            output_mp3=output_mp3,
            voice_sample=speaker_sample_path,
        )
        if omni_res is not None and os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000:
            used_mode = "OmniVoice (Voice Design: Natural Presenter)"
            subprocess.run(
                ["ffmpeg", "-y", "-i", output_mp3, "-ar", "24000", "-ac", "1", output_wav],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

    eleven_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    is_elevenlabs = bool("eleven" in voice_lower or (eleven_key and tts_engine_cfg == "elevenlabs"))

    if not used_mode and is_elevenlabs and eleven_key:
        print()
        print("=" * 60)
        print("ELEVENLABS NEURAL TTS GENERATION (WARM CONVERSATIONAL)")
        print("=" * 60)
        print("Voice: ElevenLabs (stability=0.45, similarity_boost=0.78, style=0.20)")
        print("TTS text preview:")
        print(speech_text[:400])
        print()
        el_res = await generate_elevenlabs_speech(
            speech_text=speech_text,
            output_mp3=output_mp3,
            stability=0.45,
            similarity_boost=0.78,
            style=0.20,
        )
        if el_res and os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000:
            used_mode = "ElevenLabs (Warm Conversational, Stability 0.45, Similarity 0.78, Style 0.20)"
            subprocess.run(
                ["ffmpeg", "-y", "-i", output_mp3, "-ar", "24000", "-ac", "1", output_wav],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

    if not used_mode and is_clone and speaker_sample_path and is_telugu_text:
        print()
        print("=" * 60)
        print("FREEVC24 CROSS-LINGUAL TELUGU VOICE CLONING")
        print("=" * 60)
        print("Speaker Sample:", speaker_sample_path)
        print("TTS text preview:")
        print(speech_text[:400])
        print()

        # Extract clean reference WAV snippet for FreeVC
        clean_sample_wav = "voice_samples/freevc_clean_ref.wav"
        freevc_speaker = speaker_sample_path
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(speaker_sample_path),
                    "-af",
                    "silenceremove=start_periods=1:start_duration=0.08:start_threshold=-40dB,highpass=f=80,lowpass=f=12000,loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-ss",
                    "0",
                    "-t",
                    "12",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    clean_sample_wav,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if os.path.exists(clean_sample_wav) and os.path.getsize(clean_sample_wav) > 10000:
                freevc_speaker = clean_sample_wav
        except Exception as prep_err:
            print(f"Reference audio prep note: {prep_err}")
            freevc_speaker = speaker_sample_path

        base_telugu_voice = "te-IN-ShrutiNeural" if "shruti" in voice_lower else "te-IN-MohanNeural"
        try:
            await generate_cross_lingual_cloned_voice(
                text=speech_text,
                speaker_wav=freevc_speaker,
                output_wav=output_wav,
                base_voice=base_telugu_voice,
            )

            # Apply studio loudness normalization
            norm_wav = "output/voice_norm.wav"
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        output_wav,
                        "-af",
                        "loudnorm=I=-14:TP=-1.5:LRA=11",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        norm_wav,
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if os.path.exists(norm_wav) and os.path.getsize(norm_wav) > 1000:
                    os.replace(norm_wav, output_wav)
            except Exception as norm_err:
                print(f"Post-normalization note: {norm_err}")

            used_mode = f"Cross-Lingual Cloned Voice (FreeVC24: {os.path.basename(speaker_sample_path)} -> Telugu)"
        except Exception as vc_err:
            print(f"⚠️ FreeVC24 cross-lingual cloning failed: {vc_err}. Falling back to Edge-TTS...")
            fb_done = False
            try:
                captured_words = await generate_edge_tts_speech(
                    speech_text=speech_text,
                    voice_code=base_telugu_voice,
                    output_mp3=output_mp3,
                )
                if os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", output_mp3, "-ar", "24000", "-ac", "1", output_wav],
                        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    used_mode = f"Edge-TTS Fallback ({base_telugu_voice})"
                    fb_done = True
            except Exception as edge_fb_err:
                print(f"⚠️ Edge-TTS fallback error: {edge_fb_err}. Attempting local system/Kokoro fallback...")

            if not fb_done:
                if sys.platform == "darwin":
                    temp_aiff = "output/temp_geeta.aiff"
                    try:
                        print("🎙️ Using macOS native Telugu neural voice (Geeta) as zero-network fallback...")
                        subprocess.run(["say", "-v", "Geeta", "-o", temp_aiff, speech_text], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if os.path.exists(temp_aiff) and os.path.getsize(temp_aiff) > 2000:
                            subprocess.run(["ffmpeg", "-y", "-i", temp_aiff, "-ar", "24000", "-ac", "1", output_wav], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            subprocess.run(["ffmpeg", "-y", "-i", temp_aiff, "-codec:a", "libmp3lame", "-q:a", "2", output_mp3], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            os.unlink(temp_aiff)
                            used_mode = "macOS System Voice (Geeta)"
                            fb_done = True
                    except Exception as s_err:
                        print(f"macOS voice fallback note: {s_err}")

                if not fb_done:
                    print("Falling back to local Kokoro creator voice...")
                    words = re.findall(r"[A-Za-z0-9]+", speech_text)
                    safe_k_text = " ".join(words) if len(words) >= 15 else "Here are the latest news updates and essential insights for today."
                    generate_kokoro_speech(speech_text=safe_k_text, voice_code="am_adam", output_wav=output_wav)
                    if os.path.exists(output_wav) and os.path.getsize(output_wav) > 1000:
                        subprocess.run(["ffmpeg", "-y", "-i", output_wav, "-codec:a", "libmp3lame", "-q:a", "2", output_mp3], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    used_mode = "Kokoro Fallback (am_adam)"
    elif not used_mode and is_clone and speaker_sample_path and not is_telugu_text:
        print()
        print("=" * 60)
        print("COQUI XTTS-V2 LOCAL VOICE CLONING GENERATION")
        print("=" * 60)
        print("Speaker Sample:", speaker_sample_path)
        print("TTS text preview:")
        print(speech_text[:400])
        print()

        # Extract pristine 12-second reference WAV snippet at 24000Hz 16-bit PCM for XTTS
        # with silence trimming, rumble filter, hiss reduction, and loudness normalization
        clean_sample_wav = "voice_samples/xtts_clean_ref.wav"
        xtts_speaker = speaker_sample_path
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(speaker_sample_path),
                    "-af",
                    "silenceremove=start_periods=1:start_duration=0.08:start_threshold=-40dB,highpass=f=80,lowpass=f=12000,loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-ss",
                    "0",
                    "-t",
                    "12",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    clean_sample_wav,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if os.path.exists(clean_sample_wav) and os.path.getsize(clean_sample_wav) > 10000:
                xtts_speaker = clean_sample_wav
        except Exception as prep_err:
            print(f"XTTS reference audio prep note: {prep_err}")
            xtts_speaker = speaker_sample_path

        print(f"XTTS Reference Speaker Audio: {xtts_speaker} (Size: {os.path.getsize(xtts_speaker)} bytes)")

        try:
            generate_cloned_voice_xtts(
                text=speech_text,
                speaker_wav=xtts_speaker,
                output_wav=output_wav,
            )

            # Apply studio loudness normalization to output
            norm_wav = "output/voice_norm.wav"
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        output_wav,
                        "-af",
                        "loudnorm=I=-14:TP=-1.5:LRA=11",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        norm_wav,
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if os.path.exists(norm_wav) and os.path.getsize(norm_wav) > 1000:
                    os.replace(norm_wav, output_wav)
            except Exception as norm_err:
                print(f"Post-normalization note: {norm_err}")

            # Verify audio duration sanity
            probe_cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                output_wav,
            ]
            p_res = subprocess.run(
                probe_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            actual_dur = float(p_res.stdout.strip() or 0)
            expected_dur = len(speech_text.split()) / 2.5
            if actual_dur > expected_dur * 2.2 or actual_dur < expected_dur * 0.4:
                raise RuntimeError(
                    f"Cloned audio duration anomaly: got {actual_dur:.1f}s, expected ~{expected_dur:.1f}s"
                )

            used_mode = f"XTTS-v2 Cloned Voice (sample: {os.path.basename(speaker_sample_path)})"
        except Exception as clone_err:
            print(f"⚠️ XTTS-v2 voice cloning failed or duration anomaly: {clone_err}")
            print("Falling back gracefully to Kokoro creator voice...")
            generate_kokoro_speech(
                speech_text=speech_text,
                voice_code="am_adam",
                output_wav=output_wav,
            )
            used_mode = "Kokoro Fallback (am_adam)"
    elif not used_mode and is_edge_voice:
        if "shruti" in voice_lower or "roast" in voice_lower or "sarcastic" in voice_lower or "te-in-shrutineural-roast" in voice_lower:
            edge_voice_id = "te-IN-ShrutiNeural"
        elif "swara" in voice_lower:
            edge_voice_id = "hi-IN-SwaraNeural"
        elif "madhur" in voice_lower:
            edge_voice_id = "hi-IN-MadhurNeural"
        elif is_hindi_text and not is_telugu_text:
            edge_voice_id = "hi-IN-MadhurNeural"
        elif "te-in-shrutineural" in voice_lower:
            edge_voice_id = "te-IN-ShrutiNeural"
        elif voice in ("te-IN-MohanNeural", "te-IN-ShrutiNeural", "hi-IN-MadhurNeural", "hi-IN-SwaraNeural"):
            edge_voice_id = voice
        else:
            edge_voice_id = "te-IN-MohanNeural"

        print()
        print("=" * 60)
        print("MICROSOFT EDGE-TTS MULTILINGUAL GENERATION")
        print("=" * 60)
        print("Voice:", edge_voice_id)
        print("TTS text preview:")
        print(speech_text[:400])
        print()

        try:
            if "te-" in str(edge_voice_id).lower() or re.search(r"[\u0C00-\u0C7F]", speech_text):
                try:
                    from telugu_phonetic_normalizer import normalize_telugu_tech_script
                    speech_text = normalize_telugu_tech_script(speech_text)
                except Exception as norm_err:
                    print(f"Voice agent Telugu normalization note: {norm_err}")

            # Check if delivery_plan.json exists for roast / multi-emotion synthesis
            delivery_file = Path("output/delivery_plan.json")
            roast_beats = None
            if delivery_file.exists():
                try:
                    roast_beats = json.loads(delivery_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # Check topic context to determine if this is really a roast/entertainment topic
            topic_str = ""
            for t_file in [Path("output/topic.txt"), Path("output/topic.json")]:
                if t_file.exists():
                    try:
                        topic_str = t_file.read_text(encoding="utf-8")
                        break
                    except Exception:
                        pass

            is_explicit_roast = bool(
                "roast" in voice_lower
                or "sarcastic" in voice_lower
                or "te-in-shrutineural-roast" in voice_lower
            )
            is_factual_news = (
                not is_explicit_roast
                and any(k in topic_str.lower() for k in ("cyclone", "devastation", "dead", "damaged", "government", "policy", "minister", "weather", "tragedy", "disaster"))
            )
            is_roast_delivery = bool(
                is_explicit_roast
                or any(k in topic_str.lower() for k in ("bigg boss", "roast", "comedy", "troll", "overaction", "clown", "nomination", "eviction"))
            )

            if is_roast_delivery and not is_factual_news:
                if not roast_beats or len(roast_beats) < 1:
                    # Auto-split speech_text sentences into the 6 emotion beats
                    sentences = [s.strip() for s in re.split(r"[।!?.\n]+", speech_text) if len(s.strip()) > 2]
                    if len(sentences) < 2:
                        sentences = [s.strip() for s in re.split(r"[,;]+", speech_text) if len(s.strip()) > 2]
                    if not sentences:
                        sentences = [speech_text.strip()]

                    emotion_cycle = [
                        ("neutral setup", 0, None),
                        ("fake_shock", 350, "record_scratch"),
                        ("smug", 350, None),
                        ("mock", 400, "rimshot"),
                        ("dramatic_question", 450, "crowd_ooh"),
                        ("hype", 350, None),
                    ]
                    roast_beats = []
                    for s_idx, sentence in enumerate(sentences):
                        em, pause, sfx = emotion_cycle[s_idx % len(emotion_cycle)]
                        if s_idx == 0:
                            pause = 0
                            sfx = None
                        elif s_idx == len(sentences) - 1 and len(sentences) > 2:
                            em = "hype"
                            sfx = None
                        b_dict = {
                            "spoken_text": sentence,
                            "emotion": em,
                            "pause_before_ms": pause,
                        }
                        if sfx:
                            b_dict["sfx"] = sfx
                        roast_beats.append(b_dict)

            if roast_beats and is_roast_delivery and not is_factual_news:
                print(f"🔥 [Voice Agent] Running chunked multi-emotion roast synthesis with {edge_voice_id} ({len(roast_beats)} beats)...")
                from edge_tts_generator import generate_roast_speech_with_emotions
                output_mp3, captured_words = await generate_roast_speech_with_emotions(
                    beats=roast_beats,
                    output_path=output_mp3,
                    voice=edge_voice_id,
                    sfx_enabled=True,
                )
            elif is_telugu_text or "te-in" in edge_voice_id.lower() or "mohan" in edge_voice_id.lower() or "shruti" in edge_voice_id.lower():
                print(f"🎙️ [Voice Agent] Running clean news/fact anchor Telugu speech synthesis with {edge_voice_id} (rate={rate or '+4%'}, pitch={pitch or '+0Hz'})...")
                from edge_tts_generator import generate_modulated_telugu_speech
                output_mp3, captured_words = await generate_modulated_telugu_speech(
                    script_text=speech_text,
                    output_path=output_mp3,
                    voice=edge_voice_id,
                    max_workers=4,
                    rate=rate or "+4%",
                    pitch=pitch or "+0Hz",
                )
            else:
                captured_words = await generate_edge_tts_speech(
                    speech_text=speech_text,
                    voice_code=edge_voice_id,
                    output_mp3=output_mp3,
                    rate=rate if rate else "+8%",
                    pitch=pitch if pitch else "+0Hz",
                )
            # Create output_wav from output_mp3 for downstream processing
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    output_mp3,
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-avoid_negative_ts",
                    "make_zero",
                    output_wav,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            used_mode = f"Edge-TTS ({edge_voice_id})"
        except Exception as edge_err:
            print(f"⚠️ Edge-TTS notice: {edge_err}. Attempting fast local fallback...")
            fb_done = False
            if sys.platform == "darwin":
                chosen_voice = "Geeta" if is_telugu_text else ("Lekha" if is_hindi_text else "Rishi")
                temp_aiff = "output/temp_system_fallback.aiff"
                try:
                    subprocess.run(["say", "-v", chosen_voice, "-o", temp_aiff, speech_text[:200]], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                    if os.path.exists(temp_aiff) and os.path.getsize(temp_aiff) > 2000:
                        subprocess.run(["ffmpeg", "-y", "-i", temp_aiff, "-ar", "24000", "-ac", "1", output_wav], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        subprocess.run(["ffmpeg", "-y", "-i", temp_aiff, "-codec:a", "libmp3lame", "-q:a", "2", output_mp3], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        os.unlink(temp_aiff)
                        used_mode = f"macOS System Voice ({chosen_voice})"
                        fb_done = True
                except Exception:
                    pass

            if not fb_done:
                print("Falling back to local Kokoro creator voice...")
                safe_kokoro_text = speech_text
                if is_telugu_text or is_hindi_text:
                    words = re.findall(r"[A-Za-z0-9]+", speech_text)
                    safe_kokoro_text = " ".join(words) if len(words) >= 15 else "Here are the latest news updates and essential insights for today."
                generate_kokoro_speech(
                    speech_text=safe_kokoro_text,
                    voice_code="am_adam",
                    output_wav=output_wav,
                )
                if os.path.exists(output_wav) and os.path.getsize(output_wav) > 1000:
                    subprocess.run(["ffmpeg", "-y", "-i", output_wav, "-codec:a", "libmp3lame", "-q:a", "2", output_mp3], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                used_mode = "Kokoro Fallback (am_adam)"
    elif not used_mode:
        kokoro_voice = (
            voice
            if voice
            and voice
            in (
                "af_heart",
                "am_adam",
                "am_michael",
                "af_bella",
                "bm_george",
                "bf_emma",
            )
            else KOKORO_VOICE
        )

        if is_clone and not speaker_sample_path:
            print("⚠️ Voice set to 'Clone My Voice' but no audio sample was found.")
            print(f"Using creator voice ({kokoro_voice}) instead.")

        print()
        print("=" * 60)
        print("KOKORO LOCAL TTS GENERATION")
        print("=" * 60)
        print("Voice:", kokoro_voice)
        print("Language:", KOKORO_LANGUAGE)
        print("TTS text preview:")
        print(speech_text[:400])
        print()

        generate_kokoro_speech(
            speech_text=speech_text,
            voice_code=kokoro_voice,
            output_wav=output_wav,
        )
        used_mode = f"Kokoro ({kokoro_voice})"

    # Studio-grade Pacing, Silence Removal & Ducked Background Music
    raw_audio = output_wav if (os.path.exists(output_wav) and os.path.getsize(output_wav) > 1000) else output_mp3
    voice_paced = "output/voice_paced.wav"

    try:
        is_indic_audio = bool(re.search(r"[\u0C00-\u0C7F]", speech_text)) or any(k in str(voice or "").lower() for k in ("te-", "hi-", "mohan", "shruti", "swara", "madhur"))
        # For Telugu / Indic speech, apply 1.06x energetic pacing while preserving natural breath pauses (preserve_indic_pauses=True)
        effective_speed = 1.06 if is_indic_audio else 1.07
        effective_silence = 750 if is_indic_audio else 350
        print(f"🎙️ Cleaning and pacing voice narration ({effective_speed}x pacing, preserve natural breathing={is_indic_audio})...")
        clean_and_pace_voice(
            raw_audio,
            voice_paced,
            target_speed=effective_speed,
            min_silence_ms=effective_silence,
            preserve_indic_pauses=is_indic_audio,
        )

        if include_music:
            music_track = select_mood_music(topic_category)
            music_vol = 0.10 if is_indic_audio else 0.14
            print(f"🎵 Ducking and mixing background music: {os.path.basename(music_track)} (volume={music_vol}, threshold=0.08, -24dB)...")
            mix_with_background_music(
                voice_path=voice_paced,
                music_path=music_track,
                output_path=output_mp3,
                music_base_volume=music_vol,
                threshold=0.08,
            )
            print("✅ Studio Audio Pipeline Complete: Paced voice + ducked background music saved to output/voice.mp3")
        else:
            subprocess.run(
                ["ffmpeg", "-y", "-i", voice_paced, "-codec:a", "libmp3lame", "-q:a", "2", output_mp3],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as mix_err:
        print(f"⚠️ Audio mixing notice: {mix_err}. Converting raw voice to voice.mp3...")
        if not os.path.exists(output_mp3) or (os.path.exists(output_wav) and os.path.getmtime(output_wav) > os.path.getmtime(output_mp3)):
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    output_wav,
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    output_mp3,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    # ----------------------------------------------------
    # Ensure leading silence is strictly < 0.15s for instant 0.0s speech hook
    # ----------------------------------------------------
    try:
        from agents.run_report import measure_leading_silence
        lead_sil = measure_leading_silence(output_mp3)
        if lead_sil >= 0.15:
            print(f"✂️ [Virality Trim] Leading silence was {lead_sil:.2f}s (>= 0.15s). Trimming leading silence to 0.0s...")
            tmp_trimmed = "output/voice_trimmed.mp3"
            subprocess.run([
                "ffmpeg", "-y", "-i", output_mp3,
                "-af", "silenceremove=start_periods=1:start_duration=0.01:start_threshold=-40dB",
                "-codec:a", "libmp3lame", "-q:a", "2",
                tmp_trimmed
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(tmp_trimmed) and os.path.getsize(tmp_trimmed) > 1000:
                os.replace(tmp_trimmed, output_mp3)
                new_lead = measure_leading_silence(output_mp3)
                print(f"✅ [Virality Trim] Leading silence reduced to {new_lead:.2f}s (< 0.15s target achieved).")
    except Exception as trim_lead_err:
        print(f"⚠️ Leading silence check notice: {trim_lead_err}")

    # ----------------------------------------------------
    # Synchronize Word-Level Timestamps to output/transcription.json
    # ----------------------------------------------------
    try:
        import json
        cache_file = Path("output/transcription.json")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        final_duration = 0.0
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(output_mp3),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            final_duration = float(probe.stdout.strip())
        except Exception:
            pass

        final_words = []
        if captured_words and len(captured_words) > 0:
            orig_duration = max(w["end"] for w in captured_words) if captured_words else 0.0
            scale = (final_duration / orig_duration) if (orig_duration > 0 and final_duration > 0) else 1.0
            for w in captured_words:
                final_words.append({
                    "text": w.get("text", w.get("word", "")),
                    "normalized": w.get("normalized", w.get("text", "")),
                    "start": round(w["start"] * scale, 3),
                    "end": round(w["end"] * scale, 3),
                })
        else:
            from agents.video_agent import fallback_script_word_timestamps
            final_words = fallback_script_word_timestamps(output_mp3, Path("output/script.txt"))

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "words": final_words,
                "segments": [],
                "text": speech_text,
            }, f, ensure_ascii=False, indent=2)

        # Touch cache file modification time so downstream agents recognize it as fresh
        v_mtime = os.path.getmtime(output_mp3) if os.path.exists(output_mp3) else time.time()
        os.utime(str(cache_file), (v_mtime + 2, v_mtime + 2))

        print(f"⚡ Synchronized {len(final_words)} word timestamps to output/transcription.json (0s Whisper wait!)")
    except Exception as cache_sync_err:
        print(f"⚠️ Transcription cache sync note: {cache_sync_err}")

    # Defensive guarantee: Ensure output_mp3 is valid and non-empty before returning
    if not os.path.exists(output_mp3) or os.path.getsize(output_mp3) < 1000:
        print("⚠️ Emergency audio recovery: output/voice.mp3 was missing or empty, synthesizing now...")
        if os.path.exists(output_wav) and os.path.getsize(output_wav) > 1000:
            subprocess.run(["ffmpeg", "-y", "-i", output_wav, "-codec:a", "libmp3lame", "-q:a", "2", output_mp3], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "darwin":
            c_voice = "Geeta" if is_telugu_text else ("Lekha" if is_hindi_text else "Rishi")
            t_aiff = "output/temp_emergency.aiff"
            try:
                subprocess.run(["say", "-v", c_voice, "-o", t_aiff, speech_text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(t_aiff) and os.path.getsize(t_aiff) > 1000:
                    subprocess.run(["ffmpeg", "-y", "-i", t_aiff, "-codec:a", "libmp3lame", "-q:a", "2", output_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    os.unlink(t_aiff)
            except Exception as em_err:
                print(f"Emergency audio synthesis notice: {em_err}")

    print()
    print("Voice created successfully!")
    print(f"Mode: {used_mode}")
    print("Saved to:", output_mp3)
    print("TTS text saved to: output/tts_script.txt")
    dur_ms = (time.time() - t_start_voice) * 1000
    try:
        from providers.tracker import record_step_provider
        is_fb = "fallback" in str(used_mode).lower() or "edge-tts" in str(used_mode).lower()
        record_step_provider("voice", used_mode or "Voice Engine", duration_ms=dur_ms, is_fallback=is_fb)
    except Exception:
        pass

    return output_mp3

