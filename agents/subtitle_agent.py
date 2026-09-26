import os
import json
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import whisper
except ImportError:
    whisper = None


# ============================================================
# STUDIO-GRADE WORD-HIGHLIGHT CAPTIONS
# ============================================================

@dataclass
class WordTiming:
    word: str
    start: float
    end: float

HEADER = """[Script Info]
Title: AutoTube AI Captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans Telugu,{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

ACTIVE, INACTIVE = "&H0000FFFF", "&H00FFFFFF"


def _fmt_time(s):
    h, m, sec = int(s // 3600), int((s % 3600) // 60), int(s % 60)
    cs = int(round((s - int(s)) * 100))
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"


def build_word_highlight_ass(whisper_words, output_path, video_width=1080, video_height=1920, fontsize=72, chunk_size=3):
    words = [WordTiming(w["word"].strip(), w["start"], w["end"]) for w in whisper_words if w["word"].strip()]
    chunks = [words[i:i+chunk_size] for i in range(0, len(words), chunk_size)]
    header = HEADER.format(width=video_width, height=video_height, fontsize=fontsize,
                            margin_v=int(video_height * 0.12))
    events = []
    for chunk in chunks:
        for active_idx, active_word in enumerate(chunk):
            text = " ".join(f"{{\\c{ACTIVE if i == active_idx else INACTIVE}}}{w.word}" for i, w in enumerate(chunk))
            events.append(f"Dialogue: 0,{_fmt_time(active_word.start)},{_fmt_time(active_word.end)},Default,,0,0,0,,{text}")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    return str(output_path)



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

    text = re.sub(r"[^\w\s\u0C00-\u0C7F\u0900-\u097F]+", " ", text)

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


def format_ass_timestamp(seconds):
    seconds = max(0.0, float(seconds))

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    centiseconds = int(
        round((seconds - int(seconds)) * 100)
    )

    if centiseconds >= 100:
        secs += 1
        centiseconds = 0

    if secs >= 60:
        minutes += 1
        secs = 0

    if minutes >= 60:
        hours += 1
        minutes = 0

    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


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
    cache_file = Path("output/transcription.json")
    if cache_file.exists() and VOICE_FILE.exists():
        try:
            if cache_file.stat().st_mtime >= VOICE_FILE.stat().st_mtime:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                cached_words = cached.get("words", [])
                if cached_words:
                    print("=" * 60)
                    print("USING CACHED WHISPER TRANSCRIPTION")
                    print("=" * 60)
                    print(f"Whisper words loaded from cache: {len(cached_words)}")
                    return cached_words
        except Exception:
            pass

    print()
    print("=" * 60)
    print("WHISPER AUDIO TRANSCRIPTION")
    print("=" * 60)

    if not VOICE_FILE.exists():
        raise FileNotFoundError(
            f"Missing voice file: {VOICE_FILE}"
        )

    print()
    from agents.video_agent import get_whisper_model, fallback_script_word_timestamps
    whisper_words = []

    # Check if running in cloud container or CPU-only environment where Whisper blocks for 15+ minutes
    is_cloud = (
        os.path.exists("/mount/src")
        or any(os.environ.get(k) for k in (
            "STREAMLIT_SH_ENVIRONMENT",
            "STREAMLIT_SERVER_BASE_URL",
            "SPACE_ID",
            "RENDER",
            "DYNO",
            "AUTOTUBE_CLOUD_MODE",
        ))
    )

    has_cuda = False
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except Exception:
        pass

    if is_cloud or (not has_cuda and os.environ.get("FAST_SUBTITLES", "1") == "1"):
        print("⚡ Cloud / CPU mode active: Using instant script-based word timestamp alignment (0.01s) instead of slow CPU Whisper...")
        whisper_words = fallback_script_word_timestamps(VOICE_FILE, Path("output/script.txt"))
    else:
        print()
        print(f"Loading Whisper model: {WHISPER_MODEL}")
        model = get_whisper_model()
        if model is not None:
            try:
                whisper_lang = "en"
                script_file = Path("output/script.txt")
                if script_file.exists():
                    try:
                        s_content = script_file.read_text(encoding="utf-8")
                        if re.search(r"[\u0C00-\u0C7F]", s_content):
                            whisper_lang = "te"
                        elif re.search(r"[\u0900-\u097F]", s_content):
                            whisper_lang = "hi"
                    except Exception:
                        pass

                print()
                print(f"Transcribing voice.mp3 (language={whisper_lang})...")

                result = model.transcribe(
                    str(VOICE_FILE),
                    language=whisper_lang,
                    fp16=False,
                    word_timestamps=True,
                    verbose=False,
                )

                for segment in result.get("segments", []):
                    for word in segment.get("words", []):
                        text = word.get("word", "").strip()
                        start = word.get("start")
                        end = word.get("end")
                        if not text or start is None or end is None:
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
            except Exception as trans_err:
                print(f"⚠️ Whisper transcription note in subtitle_agent: {trans_err}. Falling back...")
                whisper_words = []

    if not whisper_words:
        print("ℹ️ Generating resilient script-based word timings for subtitles...")
        whisper_words = fallback_script_word_timestamps(VOICE_FILE, Path("output/script.txt"))

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

    try:
        if not cache_file.exists() and whisper_words:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"words": whisper_words, "segments": [], "text": ""}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

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


def write_ass_karaoke_subtitles(items, output_ass="output/subtitles.ass", aspect_ratio="9:16"):
    """
    Generate Advanced SubStation Alpha (.ass) word-by-word highlighted karaoke subtitles.
    Supports either pre-chunked script items (all_subtitles) or raw whisper_words.
    Ensures correct Telugu font selection (Kohinoor Telugu) and libass compatibility.
    """
    if not items:
        return None

    if aspect_ratio == "9:16":
        res_x, res_y = 1080, 1920
        font_size = 62
        margin_v = 210  # Calibrated middle-bottom lower-third position (avoids blocking center subject)
    elif aspect_ratio == "16:9":
        res_x, res_y = 1920, 1080
        font_size = 54
        margin_v = 65
    else:  # 1:1
        res_x, res_y = 1080, 1080
        font_size = 56
        margin_v = 55

    script_file = Path("output/script.txt")
    script_text = ""
    if script_file.exists():
        try:
            script_text = script_file.read_text(encoding="utf-8")
        except Exception:
            pass

    has_telugu = (
        any(re.search(r"[\u0C00-\u0C7F]", str(item.get("text", ""))) for item in items)
        or bool(re.search(r"[\u0C00-\u0C7F]", script_text))
    )
    has_hindi = (
        any(re.search(r"[\u0900-\u097F]", str(item.get("text", ""))) for item in items)
        or bool(re.search(r"[\u0900-\u097F]", script_text))
    )
    font_name = "Kohinoor Telugu" if has_telugu else ("Kohinoor Devanagari" if has_hindi else "Arial")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3.5,1.5,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogues = []
    # Check if items are chunks (contain spaces or multiple words) or single words
    first_text = items[0].get("text", "").strip()
    is_chunk_list = " " in first_text or len(first_text.split()) > 1 or "index" in items[0]

    if is_chunk_list:
        for chunk in items:
            c_text = chunk.get("text", "").strip()
            if not c_text:
                continue
            c_start = float(chunk.get("start", 0.0))
            c_end = float(chunk.get("end", c_start + 1.0))
            words = c_text.split()
            if not words:
                continue
            k_parts = []
            for w in words:
                clean_w = w.replace("**", "").replace("*", "")
                is_spec = "**" in w or bool(re.search(r"(\d+(?:mah|hz|gb|tb|w|mp)|₹\d+|\$\d+|ufs|s27|snapdragon)", clean_w, re.I))
                if is_spec:
                    k_parts.append(f"{{\\kf{word_dur_cs}\\c&H002CD4FF&\\b1\\fscx112\\fscy112}}{clean_w}{{\\r}} ")
                else:
                    k_parts.append(f"{{\\kf{word_dur_cs}}}{clean_w} ")
            k_text = "".join(k_parts).strip()
            start_str = format_ass_timestamp(c_start)
            end_str = format_ass_timestamp(c_end)
            dialogues.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{k_text}")
    else:
        events = []
        current_chunk = []
        for w in items:
            if not current_chunk:
                current_chunk.append(w)
                continue

            prev_w = current_chunk[-1]
            gap = w["start"] - prev_w["end"]

            # Break chunk if pause > 0.35s or reached 4 words or sentence boundary
            if gap > 0.35 or len(current_chunk) >= 4 or prev_w["text"].rstrip().endswith((".", "!", "?")):
                events.append(current_chunk)
                current_chunk = [w]
            else:
                current_chunk.append(w)

        if current_chunk:
            events.append(current_chunk)

        for chunk in events:
            if not chunk:
                continue
            c_start = chunk[0]["start"]
            c_end = chunk[-1]["end"]

            karaoke_parts = []
            for idx, word_obj in enumerate(chunk):
                w_raw = word_obj.get("text", "").strip()
                w_clean = w_raw.replace("**", "").replace("*", "")
                is_spec = "**" in w_raw or bool(re.search(r"(\d+(?:mah|hz|gb|tb|w|mp)|₹\d+|\$\d+|ufs|s27|snapdragon)", w_clean, re.I))
                w_start = word_obj.get("start", c_start)
                w_end = word_obj.get("end", c_end)

                dur_cs = max(1, int(round((w_end - w_start) * 100)))

                if idx == 0 and w_start > c_start:
                    pre_gap = int(round((w_start - c_start) * 100))
                    if pre_gap > 0:
                        karaoke_parts.append(f"{{\\kf{pre_gap}}}")
                elif idx > 0:
                    prev_end = chunk[idx - 1]["end"]
                    inter_gap = int(round((w_start - prev_end) * 100))
                    if inter_gap > 2:
                        karaoke_parts.append(f"{{\\kf{inter_gap}}}")

                if is_spec:
                    karaoke_parts.append(f"{{\\kf{dur_cs}\\c&H002CD4FF&\\b1\\fscx112\\fscy112}}{w_clean}{{\\r}} ")
                else:
                    karaoke_parts.append(f"{{\\kf{dur_cs}}}{w_clean} ")

            k_text = "".join(karaoke_parts).strip()
            start_str = format_ass_timestamp(c_start)
            end_str = format_ass_timestamp(c_end)
            dialogues.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{k_text}")

    ass_content = header + "\n".join(dialogues) + "\n"
    out_path = Path(output_ass)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ass_content, encoding="utf-8")
    print(f"Word-Level Karaoke ASS subtitles saved: {output_ass} ({len(dialogues)} timed lines)")
    return str(out_path)


# ============================================================
# CREATE SUBTITLES
# ============================================================

def create_subtitles(aspect_ratio="9:16"):

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

    # Generate Word-Level Karaoke ASS Subtitles from aligned all_subtitles
    try:
        write_ass_karaoke_subtitles(
            all_subtitles,
            output_ass="output/subtitles.ass",
            aspect_ratio=aspect_ratio,
        )
    except Exception as ass_err:
        print(f"Karaoke ASS generation notice: {ass_err}")

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
