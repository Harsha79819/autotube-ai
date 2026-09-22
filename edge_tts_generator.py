"""
edge_tts_generator.py

Free, unlimited Telugu TTS using Microsoft Edge's neural voices via the
open-source `edge-tts` library (no API key, no quota).

Install:
    pip install edge-tts --break-system-packages

Available Telugu voices (verify current list anytime with `edge-tts --list-voices`):
    te-IN-ShrutiNeural  (female)
    te-IN-MohanNeural   (male)

Usage:
    import asyncio
    asyncio.run(generate_telugu_speech(
        text="మీ స్క్రిప్ట్ ఇక్కడ...",
        output_path="voice.mp3",
        voice="te-IN-MohanNeural",
        rate="+8%",     # slightly energetic pacing, avoids flat/robotic feel
        pitch="+2Hz",   # tiny lift for a livelier, less monotone delivery
    ))
"""

import asyncio
import re
import edge_tts


def prepare_script_for_tts(raw_text: str) -> str:
    """Punctuation cleanup and phonetic Telugu tech normalization so Edge-TTS
    pacing sounds natural and technical model codes (e.g. iPhone 18 -> ఐఫోన్ ఎయిటీన్)
    are pronounced in conversational English phonetics instead of literal Telugu digits.
    """
    text = str(raw_text or "").strip()

    # Apply Telugu phonetic normalization for brands, model numbers, chips & specs
    try:
        from telugu_phonetic_normalizer import normalize_telugu_tech_script
        text = normalize_telugu_tech_script(text)
    except Exception as norm_err:
        print(f"[edge_tts] Phonetic normalization note: {norm_err}")

    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([.!?])(?=\S)", r"\1 ", text)   # space after . ! ?
    text = re.sub(r"([,;])(?=\S)", r"\1 ", text)     # space after , ;
    return text


async def generate_telugu_speech(
    text: str,
    output_path: str,
    voice: str = "te-IN-MohanNeural",
    rate: str = "+8%",
    pitch: str = "+2Hz",
) -> str:
    """Generate natural-sounding Telugu speech via Edge-TTS.

    rate: percentage speed adjustment. "+0%" is default Edge pace, which
          many people find slightly flat for review/short-form content --
          "+5%" to "+10%" gives a livelier, more energetic delivery.
    pitch: small positive pitch shift reduces the "flat/robotic" perception
           reported with default settings, without sounding unnatural.
    """
    safe_text = prepare_script_for_tts(text)

    communicate = edge_tts.Communicate(
        text=safe_text,
        voice=voice,
        rate=rate,
        pitch=pitch,
    )
    await communicate.save(output_path)
    return output_path


async def generate_with_word_boundaries(
    text: str,
    output_path: str,
    voice: str = "te-IN-MohanNeural",
    rate: str = "+8%",
    pitch: str = "+2Hz",
):
    """Generates natural-sounding speech via Edge-TTS and captures word-level timing
    boundaries directly from Microsoft's neural stream. This completely replaces the need
    for heavy 15-minute CPU Whisper transcription on Cloud environments."""
    safe_text = prepare_script_for_tts(text)
    communicate = edge_tts.Communicate(
        text=safe_text,
        voice=voice,
        rate=rate or "+8%",
        pitch=pitch or "+2Hz",
    )

    word_timings = []
    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                w_text = str(chunk.get("text", "")).strip()
                if not w_text:
                    continue
                start_sec = round(float(chunk["offset"]) / 10_000_000.0, 3)
                duration_sec = round(float(chunk["duration"]) / 10_000_000.0, 3)
                end_sec = round(start_sec + duration_sec, 3)

                norm = re.sub(r"[^\w\s]", "", w_text).strip()
                word_timings.append({
                    "word": w_text,
                    "text": w_text,
                    "normalized": norm or w_text,
                    "start": start_sec,
                    "end": end_sec,
                })

    return output_path, word_timings



if __name__ == "__main__":
    sample_text = "Samsung Galaxy S26 FE లో కొత్త కెమెరా ఫీచర్లు ఉన్నాయి. ధర ఎంతో చూద్దాం."
    print("Prepared text:", prepare_script_for_tts(sample_text))
    print("(Run generate_telugu_speech(...) via asyncio.run() to actually synthesize -- needs network access to Microsoft's Edge TTS service.)")
