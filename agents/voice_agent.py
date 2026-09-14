import asyncio
import os
import re

os.environ["HF_HUB_OFFLINE"] = "1"

from dotenv import load_dotenv
from kokoro import KPipeline
import soundfile as sf
import subprocess
from supervisor import autonomous_recover

load_dotenv()



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
    into natural English speech.
    """

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


def generate_cloned_voice_xtts(
    text: str,
    speaker_wav: str,
    output_wav: str,
    language: str = "en",
):
    """
    Clone user's voice using Coqui XTTS-v2 with a high-fidelity reference audio sample.
    """
    global _XTTS_MODEL
    try:
        tts = get_xtts_model()
        print(f"Synthesizing cloned voice with speaker sample: {speaker_wav}")
        tts.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            language=language,
            file_path=output_wav,
            split_sentences=True,
        )
    except Exception as e:
        print(f"XTTS synthesis error: {e}. Retrying on CPU...")
        os.environ["COQUI_TOS_AGREED"] = "1"
        from TTS.api import TTS
        _XTTS_MODEL = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
        _XTTS_MODEL.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            language=language,
            file_path=output_wav,
            split_sentences=True,
        )


_KOKORO_PIPELINE = None


def get_kokoro_pipeline():
    """
    Cache KPipeline globally for ultra-fast, sub-second synthesis.
    Loads strictly from local HuggingFace cache to prevent network/hub errors.
    """
    global _KOKORO_PIPELINE
    if _KOKORO_PIPELINE is None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        from kokoro import KPipeline, KModel
        from huggingface_hub import hf_hub_download
        import torch

        # Load weights directly from local cache with local_files_only=True
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
        except Exception as load_err:
            print(f"Kokoro local weights notice: {load_err}, attempting standard init...")
            try:
                model = KModel().eval()
            except Exception:
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


@autonomous_recover("voice_agent")
async def create_voice(
    voice=None,
    rate="-5%",
    pitch="+0Hz",
    voice_sample=None,
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

    telugu_chars = re.findall(
        r"[\u0C00-\u0C7F]",
        text,
    )

    if telugu_chars:
        raise ValueError(
            "Telugu characters detected in script. "
            "English-only voice generation stopped."
        )

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

    used_mode = None
    if is_clone and speaker_sample_path:
        print()
        print("=" * 60)
        print("COQUI XTTS-V2 LOCAL VOICE CLONING GENERATION")
        print("=" * 60)
        print("Speaker Sample:", speaker_sample_path)
        print("TTS text preview:")
        print(speech_text[:400])
        print()

        # Extract pristine 12-second reference WAV snippet at 24000Hz for XTTS
        # with silence trimming, rumble filter, hiss reduction, and loudness normalization
        clean_sample_wav = "voice_samples/xtts_clean_ref.wav"
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
                    clean_sample_wav,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            xtts_speaker = clean_sample_wav
        except Exception:
            xtts_speaker = speaker_sample_path

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

    # Convert generated wav to output/voice.mp3
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

    print()
    print("Voice created successfully!")
    print(f"Mode: {used_mode}")
    print("Saved to:", output_mp3)
    print("TTS text saved to: output/tts_script.txt")
    print()

    return output_mp3

