import asyncio
import os
import re

import edge_tts


# ============================================================
# ENGLISH VOICE CONFIG
# ============================================================

ENGLISH_VOICE = "en-US-AndrewNeural"


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

async def create_voice(
    voice=None,
    rate="-5%",
    pitch="+0Hz"
):
    """
    Create English-only narration audio.
    """

    script_path = "output/script.txt"

    if not os.path.exists(script_path):
        print("Script not found!")
        return None

    with open(
        script_path,
        "r",
        encoding="utf-8"
    ) as file:
        text = file.read().strip()

    if not text:
        print("Script is empty!")
        return None

    # --------------------------------------------------------
    # HARD ENGLISH CHECK
    # --------------------------------------------------------

    telugu_chars = re.findall(
        r"[\u0C00-\u0C7F]",
        text
    )

    if telugu_chars:
        raise ValueError(
            "Telugu characters detected in script. "
            "English-only voice generation stopped."
        )

    # --------------------------------------------------------
    # Always use English voice
    # --------------------------------------------------------

    selected_voice = voice or ENGLISH_VOICE

    speech_text = make_tts_text(text)

    os.makedirs(
        "output",
        exist_ok=True
    )

    with open(
        "output/tts_script.txt",
        "w",
        encoding="utf-8"
    ) as file:
        file.write(speech_text)

    print()
    print("=" * 60)
    print("ENGLISH TTS GENERATION")
    print("=" * 60)
    print()
    print("Voice:", selected_voice)
    print("Rate:", rate)
    print("Pitch:", pitch)
    print()
    print("TTS text:")
    print(speech_text[:500])
    print()

    communicate = edge_tts.Communicate(
        speech_text,
        selected_voice,
        rate=rate,
        pitch=pitch,
    )

    await communicate.save(
        "output/voice.mp3"
    )

    print()
    print("Voice created successfully!")
    print("Saved to: output/voice.mp3")
    print("TTS text saved to: output/tts_script.txt")
    print()

    return "output/voice.mp3"


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":
    asyncio.run(create_voice())
