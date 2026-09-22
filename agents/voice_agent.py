import asyncio
import os
import re

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

    # --------------------------------------------------------
    # Decimal numbers
    # 2.54 -> two point five four
    # --------------------------------------------------------

    def decimal_replace(match):
        whole = int(match.group(1))
        decimal = match.group(2)

        whole_words = num2words(
            whole,
            lang="en"
        )

        decimal_words = " ".join(
            num2words(
                int(digit),
                lang="en"
            )
            for digit in decimal
        )

        return f"{whole_words} point {decimal_words}"

    text = re.sub(
        r"\b(\d+)\.(\d+)\b",
        decimal_replace,
        text
    )

    # --------------------------------------------------------
    # Percentages
    # 5% -> five percent
    # --------------------------------------------------------

    def percent_replace(match):
        number = match.group(1)

        if "." in number:
            value = float(number)
            words = num2words(
                value,
                lang="en"
            )
        else:
            words = num2words(
                int(number),
                lang="en"
            )

        return f"{words} percent"

    text = re.sub(
        r"(\d+(?:\.\d+)?)%",
        percent_replace,
        text
    )

    # --------------------------------------------------------
    # Indian currency
    # ₹500 -> five hundred rupees
    # Rs. 500 -> five hundred rupees
    # --------------------------------------------------------

    def rupee_replace(match):
        number = match.group(1)

        if "." in number:
            value = float(number)
            words = num2words(
                value,
                lang="en"
            )
        else:
            words = num2words(
                int(number),
                lang="en"
            )

        return f"{words} rupees"

    text = text.replace("₹", "₹")

    text = re.sub(
        r"₹\s*(\d+(?:\.\d+)?)",
        rupee_replace,
        text
    )

    text = re.sub(
        r"\bRs\.?\s*(\d+(?:\.\d+)?)",
        rupee_replace,
        text,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # Indian financial expressions
    # "five hundred rupees crore" -> "five hundred crore"
    # "two rupees lakh" -> "two lakh"
    # --------------------------------------------------------

    text = re.sub(
        r"\\brupees\\s+(?=(?:lakh|crore)\\b)",
        "",
        text,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # Years
    #
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
                return f"two thousand and {num2words(last_two, lang='en')}"

            last_two_words = num2words(
                last_two,
                lang="en"
            )

            return f"twenty {last_two_words}"

        return match.group(0)

    text = re.sub(
        r"\b20\d{2}\b",
        year_replace,
        text
    )

    # --------------------------------------------------------
    # Standalone numbers
    #
    # 5 -> five
    # 500 -> five hundred
    #
    # Avoid converting numbers that are part of words.
    # --------------------------------------------------------

    def number_replace(match):
        number = int(match.group(0))

        return num2words(
            number,
            lang="en"
        )

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
):
    """
    Clone user's voice using Coqui XTTS-v2 with high-fidelity reference audio sample
    and explicit tuned inference parameters (speed=1.0, natural temperature/pacing).
    """
    global _XTTS_MODEL
    from telugu_phonetic_normalizer import normalize_telugu_tech_script
    safe_text = normalize_telugu_tech_script(text) if re.search(r"[\u0C00-\u0C7F]", text) else text

    if language.lower() in ("te", "telugu"):
        print("ℹ️ Note: XTTS-v2 natively supports ['en', 'hi', ...]. Routing Telugu ('te') through cross-lingual FreeVC24 engine...")
        import asyncio
        asyncio.run(
            generate_cross_lingual_cloned_voice(
                text=safe_text,
                speaker_wav=speaker_wav,
                output_wav=output_wav,
                base_voice="te-IN-MohanNeural",
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
    base_voice: str = "te-IN-MohanNeural",
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
    for _, _, audio in generator:
        audio_parts.append(audio)

    if not audio_parts:
        raise RuntimeError(
            "Kokoro did not generate any audio."
        )

    import numpy as np

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
    pitch="+2Hz",
):
    """Generate high-quality multilingual neural voice using Microsoft Edge-TTS with tuned pacing,
    capturing exact word boundary timestamps directly from the stream."""
    word_timings = []
    try:
        from edge_tts_generator import generate_with_word_boundaries
        _, word_timings = await generate_with_word_boundaries(
            text=speech_text,
            output_path=output_mp3,
            voice=voice_code or "te-IN-MohanNeural",
            rate=rate or "+8%",
            pitch=pitch or "+2Hz",
        )
    except Exception as boundary_err:
        print(f"Edge-TTS boundary capture note: {boundary_err}. Falling back to standard synthesis...")
        try:
            from edge_tts_generator import generate_telugu_speech
            await generate_telugu_speech(
                text=speech_text,
                output_path=output_mp3,
                voice=voice_code or "te-IN-MohanNeural",
                rate=rate or "+8%",
                pitch=pitch or "+2Hz",
            )
        except Exception:
            import edge_tts
            communicate = edge_tts.Communicate(
                text=speech_text,
                voice=voice_code,
                rate=rate or "+8%",
                pitch=pitch or "+2Hz",
            )
            await communicate.save(output_mp3)

    return word_timings


@autonomous_recover("voice_agent")
async def create_voice(
    voice=None,
    rate="-5%",
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
        or (is_telugu_text and not is_clone)
        or (is_hindi_text and not is_clone)
    )

    used_mode = None
    if is_clone and speaker_sample_path and is_telugu_text:
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
                    "silenceremove=start_periods=1:start_duration=0.08:start_threshold=-40dB,highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11",
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
                        "loudnorm=I=-16:TP=-1.5:LRA=11",
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
            await generate_edge_tts_speech(
                speech_text=speech_text,
                voice_code=base_telugu_voice,
                output_mp3=output_wav,
            )
            used_mode = f"Edge-TTS Fallback ({base_telugu_voice})"
    elif is_clone and speaker_sample_path and not is_telugu_text:
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
                    "silenceremove=start_periods=1:start_duration=0.08:start_threshold=-40dB,highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11",
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
                        "loudnorm=I=-16:TP=-1.5:LRA=11",
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
    elif is_edge_voice:
        if "shruti" in voice_lower:
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

            captured_words = await generate_edge_tts_speech(
                speech_text=speech_text,
                voice_code=edge_voice_id,
                output_mp3=output_mp3,
                rate=rate if (rate and rate not in ("-5%", "+0%")) else "+8%",
                pitch=pitch if (pitch and pitch != "+0Hz") else "+2Hz",
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
                    output_wav,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            used_mode = f"Edge-TTS ({edge_voice_id})"
        except Exception as edge_err:
            print(f"⚠️ Edge-TTS error: {edge_err}. Attempting Kokoro fallback...")
            generate_kokoro_speech(
                speech_text=speech_text,
                voice_code="am_adam",
                output_wav=output_wav,
            )
            used_mode = "Kokoro Fallback (am_adam)"
    else:
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
        print("🎙️ Cleaning and pacing voice narration (1.07x pacing, -40dB silence trim)...")
        clean_and_pace_voice(raw_audio, voice_paced, target_speed=1.07, min_silence_ms=350)

        if include_music:
            music_track = select_mood_music(topic_category)
            print(f"🎵 Ducking and mixing background music: {os.path.basename(music_track)} (threshold=0.08, -20dB)...")
            mix_with_background_music(
                voice_path=voice_paced,
                music_path=music_track,
                output_path=output_mp3,
                music_base_volume=0.35,
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
    # Synchronize Word-Level Timestamps to output/transcription.json
    # ----------------------------------------------------
    try:
        import json
        import time
        from pathlib import Path
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

    print()
    print("Voice created successfully!")
    print(f"Mode: {used_mode}")
    print("Saved to:", output_mp3)
    print("TTS text saved to: output/tts_script.txt")
    print()

    return output_mp3

