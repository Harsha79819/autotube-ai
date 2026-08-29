import re
from pathlib import Path

import whisper


# ============================================================
# CONFIG
# ============================================================

VOICE_FILE = Path("output/voice.mp3")
SECTION_MAP_FILE = Path("output/section_map.txt")
OUTPUT_FILE = Path("output/subtitles.srt")

WHISPER_MODEL = "base"
MAX_WORDS_PER_SUBTITLE = 10


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(text):
    text = text.lower()

    text = text.replace("’", "'")
    text = text.replace("–", "-")
    text = text.replace("—", "-")

    text = re.sub(r"[^a-z0-9]+", " ", text)

    return " ".join(text.split())


def normalize_words(text):
    normalized = normalize_text(text)

    if not normalized:
        return []

    return normalized.split()


# ============================================================
# TIMESTAMP
# ============================================================

def format_timestamp(seconds):
    seconds = max(0.0, float(seconds))

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    milliseconds = int(
        round((seconds - int(seconds)) * 1000)
    )

    if milliseconds >= 1000:
        secs += 1
        milliseconds = 0

    if secs >= 60:
        minutes += 1
        secs = 0

    if minutes >= 60:
        hours += 1
        minutes = 0

    return (
        f"{hours:02}:{minutes:02}:{secs:02},"
        f"{milliseconds:03}"
    )


# ============================================================
# SECTION MAP
# ============================================================

def load_section_map():
    print()
    print("=" * 60)
    print("LOADING SECTION MAP")
    print("=" * 60)

    if not SECTION_MAP_FILE.exists():
        raise FileNotFoundError(
            f"Missing section map: {SECTION_MAP_FILE}"
        )

    sections = []

    current_section = None

    with open(
        SECTION_MAP_FILE,
        "r",
        encoding="utf-8",
    ) as f:

        for raw_line in f:

            line = raw_line.strip()

            if not line:
                continue

            match = re.match(
                r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)",
                line,
                re.IGNORECASE,
            )

            if match:

                if current_section is not None:
                    if not current_section["narration"]:
                        raise RuntimeError(
                            f"Section "
                            f"{current_section['section']} "
                            "has no narration."
                        )

                    sections.append(
                        current_section
                    )

                current_section = {
                    "section": int(match.group(1)),
                    "visual": int(match.group(2)),
                    "narration": "",
                }

                continue

            if current_section is not None:

                if current_section["narration"]:
                    current_section["narration"] += " "

                current_section["narration"] += line

    if current_section is not None:

        if not current_section["narration"]:
            raise RuntimeError(
                f"Section "
                f"{current_section['section']} "
                "has no narration."
            )

        sections.append(current_section)

    if not sections:
        raise RuntimeError(
            "No sections found in section_map.txt"
        )

    print()
    print(
        f"Sections loaded: {len(sections)}"
    )

    return sections


# ============================================================
# WHISPER
# ============================================================

def transcribe_audio():
    print()
    print("=" * 60)
    print("WHISPER AUDIO TRANSCRIPTION")
    print("=" * 60)

    if not VOICE_FILE.exists():
        raise FileNotFoundError(
            f"Missing voice file: {VOICE_FILE}"
        )

    print()
    print(
        f"Loading Whisper model: "
        f"{WHISPER_MODEL}"
    )

    model = whisper.load_model(
        WHISPER_MODEL
    )

    print()
    print("Transcribing voice.mp3...")

    result = model.transcribe(
        str(VOICE_FILE),
        language="en",
        fp16=False,
        word_timestamps=True,
        verbose=False,
    )

    whisper_words = []

    for segment in result.get(
        "segments",
        [],
    ):

        for word in segment.get(
            "words",
            [],
        ):

            text = word.get(
                "word",
                "",
            ).strip()

            start = word.get("start")
            end = word.get("end")

            if not text:
                continue

            if start is None or end is None:
                continue

            normalized = normalize_text(text)

            if not normalized:
                continue

            whisper_words.append(
                {
                    "text": text,
                    "normalized": normalized,
                    "start": float(start),
                    "end": float(end),
                }
            )

    if not whisper_words:
        raise RuntimeError(
            "Whisper returned no word timestamps."
        )

    recognized_duration = max(
        word["end"]
        for word in whisper_words
    )

    print()
    print(
        f"Whisper words: "
        f"{len(whisper_words)}"
    )

    print(
        f"Whisper recognized duration: "
        f"{recognized_duration:.2f}s"
    )

    return whisper_words


# ============================================================
# SECTION ALIGNMENT
# ============================================================

def align_section_words(
    section_words,
    whisper_words,
    start_index,
):
    """
    Align one section against Whisper words.

    Uses sequential fuzzy matching.

    Important:
    Whisper may misrecognize names and numbers.
    Therefore we do NOT require exact text equality.
    """

    target_count = len(section_words)

    if target_count == 0:
        return None

    remaining = len(whisper_words) - start_index

    if remaining <= 0:
        return None

    # --------------------------------------------------------
    # For normal TTS narration the word count should be very
    # close to Whisper's word count.
    #
    # Search windows around the expected size.
    # --------------------------------------------------------

    min_window = max(
        1,
        int(target_count * 0.70),
    )

    max_window = min(
        remaining,
        max(
            min_window,
            int(target_count * 1.35) + 8,
        ),
    )

    best = None

    target_set = set(section_words)

    for candidate_start in range(
        start_index,
        min(
            len(whisper_words),
            start_index + 12,
        ),
    ):

        for window_size in range(
            min_window,
            max_window + 1,
        ):

            candidate_end = (
                candidate_start
                + window_size
            )

            if candidate_end > len(
                whisper_words
            ):
                break

            candidate = whisper_words[
                candidate_start:candidate_end
            ]

            candidate_words = [
                item["normalized"]
                for item in candidate
            ]

            candidate_set = set(
                candidate_words
            )

            if not candidate_set:
                continue

            intersection = (
                target_set
                & candidate_set
            )

            overlap = (
                len(intersection)
                / max(
                    1,
                    len(target_set),
                )
            )

            # Ordered positional similarity.
            positional_hits = 0

            compare_count = min(
                target_count,
                window_size,
            )

            for i in range(
                compare_count
            ):

                if (
                    section_words[i]
                    == candidate_words[i]
                ):
                    positional_hits += 1

            positional_score = (
                positional_hits
                / max(
                    1,
                    compare_count,
                )
            )

            score = (
                overlap * 0.65
                + positional_score * 0.35
            )

            # Strong bonus for matching boundaries.
            if (
                candidate_words[0]
                == section_words[0]
            ):
                score += 0.08

            if (
                candidate_words[-1]
                == section_words[-1]
            ):
                score += 0.08

            if best is None or score > best["score"]:

                best = {
                    "score": score,
                    "start_index": candidate_start,
                    "end_index": candidate_end,
                    "start": candidate[0]["start"],
                    "end": candidate[-1]["end"],
                }

    return best


def find_section_timestamps(
    sections,
    whisper_words,
    audio_duration,
):
    print()
    print("=" * 60)
    print("MATCHING SECTIONS TO WHISPER")
    print("=" * 60)

    results = []

    search_index = 0

    for section in sections:

        section_words = normalize_words(
            section["narration"]
        )

        match = align_section_words(
            section_words,
            whisper_words,
            search_index,
        )

        if match is None:

            print()
            print(
                f"WARNING: Whisper could not "
                f"match Section "
                f"{section['section']}"
            )

            match_score = 0.0

        else:

            match_score = match["score"]

        # ----------------------------------------------------
        # If Whisper alignment is weak, do NOT trust the weak
        # boundary.
        #
        # Instead we use the remaining narration proportion.
        # This prevents the old 5.78-second Section 1 problem.
        # ----------------------------------------------------

        if (
            match is None
            or match_score < 0.55
        ):

            remaining_sections = (
                len(sections)
                - len(results)
            )

            previous_end = (
                results[-1]["end"]
                if results
                else 0.0
            )

            remaining_duration = max(
                0.0,
                audio_duration
                - previous_end,
            )

            remaining_word_count = sum(
                len(
                    normalize_words(
                        item["narration"]
                    )
                )
                for item in sections[
                    len(results):
                ]
            )

            if remaining_word_count <= 0:

                duration = (
                    remaining_duration
                    / max(
                        1,
                        remaining_sections,
                    )
                )

            else:

                duration = (
                    remaining_duration
                    * len(section_words)
                    / remaining_word_count
                )

            start = previous_end

            end = min(
                audio_duration,
                start + duration,
            )

            next_search_index = search_index

        else:

            start = match["start"]
            end = match["end"]

            next_search_index = (
                match["end_index"]
            )

        # ----------------------------------------------------
        # Never allow a section to start before the previous
        # section.
        # ----------------------------------------------------

        if results:

            start = max(
                start,
                results[-1]["end"],
            )

        start = max(
            0.0,
            min(
                start,
                audio_duration,
            ),
        )

        end = max(
            start,
            min(
                end,
                audio_duration,
            ),
        )

        results.append(
            {
                "section": section["section"],
                "visual": section["visual"],
                "narration": section["narration"],
                "start": start,
                "end": end,
                "match_score": match_score,
            }
        )

        print()
        print(
            f"SECTION {section['section']}"
        )

        print(
            f"START   {start:.2f}s"
        )

        print(
            f"END     {end:.2f}s"
        )

        print(
            f"DURATION "
            f"{end - start:.2f}s"
        )

        print(
            f"MATCH SCORE "
            f"{match_score:.2f}"
        )

        search_index = max(
            search_index,
            next_search_index,
        )

    # --------------------------------------------------------
    # FORCE continuous timeline.
    # --------------------------------------------------------

    if not results:
        raise RuntimeError(
            "No section timestamps created."
        )

    results[0]["start"] = 0.0

    for i in range(
        1,
        len(results),
    ):

        results[i]["start"] = (
            results[i - 1]["end"]
        )

    results[-1]["end"] = audio_duration

    # --------------------------------------------------------
    # If a section somehow became zero length, distribute
    # the audio safely by narration word count.
    # --------------------------------------------------------

    total_narration_words = sum(
        len(
            normalize_words(
                item["narration"]
            )
        )
        for item in sections
    )

    for item in results:

        if item["end"] <= item["start"]:

            raise RuntimeError(
                f"Invalid section timing: "
                f"Section {item['section']}"
            )

    print()
    print("=" * 60)
    print("FINAL SECTION TIMELINE")
    print("=" * 60)

    for item in results:

        print(
            f"SECTION {item['section']} "
            f"| VISUAL {item['visual']} "
            f"| "
            f"{item['start']:.2f}s → "
            f"{item['end']:.2f}s "
            f"| "
            f"{item['end'] - item['start']:.2f}s"
        )

    return results


# ============================================================
# SUBTITLE CHUNKS
# ============================================================

def create_subtitle_chunks(
    section,
    section_start,
    section_end,
    max_words=MAX_WORDS_PER_SUBTITLE,
):
    """
    Exact narration text.
    Timing is derived from the Whisper-aligned section.
    """

    words = section["narration"].split()

    if not words:
        return []

    chunks = []

    for i in range(
        0,
        len(words),
        max_words,
    ):

        chunks.append(
            " ".join(
                words[
                    i:i + max_words
                ]
            )
        )

    total_words = len(words)

    duration = (
        section_end
        - section_start
    )

    current = section_start

    subtitles = []

    for chunk in chunks:

        count = len(
            chunk.split()
        )

        chunk_duration = (
            duration
            * count
            / max(
                1,
                total_words,
            )
        )

        start = current

        end = min(
            section_end,
            current + chunk_duration,
        )

        subtitles.append(
            {
                "start": start,
                "end": end,
                "text": chunk,
            }
        )

        current = end

    if subtitles:
        subtitles[-1]["end"] = section_end

    return subtitles


# ============================================================
# CREATE SUBTITLES
# ============================================================

def create_subtitles():

    print("=" * 60)
    print("SUBTITLE GENERATION")
    print("=" * 60)

    sections = load_section_map()

    whisper_words = transcribe_audio()

    # Actual audio duration from Whisper's final word.
    whisper_duration = max(
        word["end"]
        for word in whisper_words
    )

    # Add the small tail of the actual MP3.
    # ffprobe shows 93.55s while Whisper recognizes 93.04s.
    #
    # We use the actual audio duration when available.
    actual_duration = whisper_duration

    try:

        import subprocess

        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(VOICE_FILE),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        actual_duration = float(
            probe.stdout.strip()
        )

    except Exception:
        pass

    print()
    print(
        f"Actual audio duration: "
        f"{actual_duration:.2f}s"
    )

    timed_sections = find_section_timestamps(
        sections,
        whisper_words,
        actual_duration,
    )

    # ========================================================
    # CREATE SUBTITLE CHUNKS
    # ========================================================

    print()
    print("=" * 60)
    print("CREATING SUBTITLE CHUNKS")
    print("=" * 60)

    all_subtitles = []

    subtitle_index = 1

    for section in timed_sections:

        chunks = create_subtitle_chunks(
            section,
            section["start"],
            section["end"],
        )

        for chunk in chunks:

            chunk["index"] = subtitle_index

            all_subtitles.append(
                chunk
            )

            subtitle_index += 1

    if not all_subtitles:
        raise RuntimeError(
            "No subtitle chunks created."
        )

    # ========================================================
    # WRITE SRT
    # ========================================================

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        for subtitle in all_subtitles:

            f.write(
                f"{subtitle['index']}\n"
            )

            f.write(
                f"{format_timestamp(subtitle['start'])}"
                f" --> "
                f"{format_timestamp(subtitle['end'])}\n"
            )

            f.write(
                f"{subtitle['text']}\n\n"
            )

    print()
    print("=" * 60)
    print("SUBTITLES CREATED SUCCESSFULLY")
    print("=" * 60)

    print()
    print(
        f"Saved: {OUTPUT_FILE}"
    )

    print(
        f"Subtitle chunks: "
        f"{len(all_subtitles)}"
    )

    print(
        f"Audio duration: "
        f"{actual_duration:.2f}s"
    )

    print()
    print(
        "Timing source: "
        "Whisper section timestamps"
    )

    print()
    print("=" * 60)
    print("SUBTITLE TIMELINE")
    print("=" * 60)

    for subtitle in all_subtitles:

        print(
            f"{subtitle['index']:02d} | "
            f"{subtitle['start']:.2f}s → "
            f"{subtitle['end']:.2f}s | "
            f"{subtitle['text']}"
        )

    return str(OUTPUT_FILE)


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":
    create_subtitles()
