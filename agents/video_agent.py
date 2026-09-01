import re
from pathlib import Path

import whisper
from moviepy import AudioFileClip, ImageClip, VideoFileClip, concatenate_videoclips


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "output"

SCRIPT_FILE = OUTPUT_DIR / "script.txt"
VISUAL_PLAN_FILE = OUTPUT_DIR / "visual_plan.txt"
SECTION_MAP_FILE = OUTPUT_DIR / "section_map.txt"
VOICE_FILE = OUTPUT_DIR / "voice.mp3"
VIDEO_FILE = OUTPUT_DIR / "video.mp4"


# ============================================================
# VIDEO CONFIG
# ============================================================

IMAGE_WIDTH = 640
FPS = 10

# Whisper model.
# "base" is a good balance for this Mac/project.
WHISPER_MODEL = "base"


# ============================================================
# HELPERS
# ============================================================

def get_images():
    """
    Return numbered visuals in exact numeric order.

    Visual 1 -> assets/1.jpg
    Visual 2 -> assets/2.jpg
    ...
    Visual 8 -> assets/8.jpg

    flyer_original.jpg is intentionally ignored.
    """

    if not ASSETS_DIR.exists():
        return []

    numbered = []

    for path in ASSETS_DIR.iterdir():

        if not path.is_file():
            continue

        match = re.fullmatch(
            r"(\d+)\.(jpg|jpeg|png|webp)",
            path.name,
            re.IGNORECASE,
        )

        if not match:
            continue

        numbered.append(
            (
                int(match.group(1)),
                path,
            )
        )

    numbered.sort(
        key=lambda item: item[0]
    )

    return [
        path
        for _, path in numbered
    ]


def get_visual_plan():
    """
    Read visual_plan.txt.

    Expected:

        1. Visual concept
        2. Visual concept
        ...
    """

    if not VISUAL_PLAN_FILE.exists():
        return []

    visuals = []

    with open(
        VISUAL_PLAN_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        for raw_line in file:

            line = raw_line.strip()

            match = re.match(
                r"^\d+[\.\)]\s*(.+)$",
                line,
            )

            if not match:
                continue

            visual = match.group(1).strip()

            if visual:
                visuals.append(visual)

    return visuals


def get_section_map():
    """
    Read the exact SECTION -> VISUAL -> NARRATION mapping.

    Expected format:

        SECTION 1 | VISUAL 1
        narration...

        SECTION 2 | VISUAL 2
        narration...

    Returns a list of dictionaries.
    """

    if not SECTION_MAP_FILE.exists():
        return []

    with open(
        SECTION_MAP_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        text = file.read()

    pattern = re.compile(
        r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n"
        r"(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    sections = []

    for match in pattern.finditer(text):

        section_number = int(
            match.group(1)
        )

        visual_number = int(
            match.group(2)
        )

        narration = match.group(3).strip()

        if not narration:
            continue

        sections.append(
            {
                "section": section_number,
                "visual": visual_number,
                "narration": narration,
            }
        )

    sections.sort(
        key=lambda item: item["section"]
    )

    return sections


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    """
    Normalize text so section narration can be matched
    against Whisper transcription.

    Example:

        "twenty-five"
        ->
        "twenty five"

    Punctuation is removed and repeated spaces are collapsed.
    """

    text = text.lower()

    # Normalize common dash characters.
    text = text.replace(
        "–",
        " ",
    )
    text = text.replace(
        "—",
        " ",
    )
    text = text.replace(
        "-",
        " ",
    )

    # Remove punctuation.
    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    # Collapse whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_words(text):
    """
    Convert text into normalized individual words.
    """

    normalized = normalize_text(text)

    if not normalized:
        return []

    return normalized.split()


# ============================================================
# VALIDATION
# ============================================================

def validate_mapping(
    images,
    visual_plan,
    sections,
):
    """
    Make absolutely sure:

        Section 1 -> Visual 1 -> 1.jpg
        Section 2 -> Visual 2 -> 2.jpg
        ...
    """

    print()
    print("=" * 60)
    print("VALIDATING VISUAL / SECTION MAPPING")
    print("=" * 60)

    print()
    print(
        f"Images       : {len(images)}"
    )

    print(
        f"Visual plan  : {len(visual_plan)}"
    )

    print(
        f"Sections     : {len(sections)}"
    )

    if len(images) != len(visual_plan):
        raise RuntimeError(
            "Image count does not match visual-plan count."
        )

    if len(sections) != len(visual_plan):
        raise RuntimeError(
            "Section count does not match visual-plan count."
        )

    expected = list(
        range(
            1,
            len(visual_plan) + 1,
        )
    )

    actual_sections = [
        item["section"]
        for item in sections
    ]

    actual_visuals = [
        item["visual"]
        for item in sections
    ]

    if actual_sections != expected:
        raise RuntimeError(
            "Section numbering is invalid: "
            f"{actual_sections}"
        )

    if actual_visuals != expected:
        raise RuntimeError(
            "Section-to-visual mapping is invalid: "
            f"{actual_visuals}"
        )

    for index, image in enumerate(
        images,
        start=1,
    ):

        expected_name = f"{index}.jpg"

        if image.name.lower() != expected_name:
            raise RuntimeError(
                f"Expected Visual {index} to use "
                f"{expected_name}, but found "
                f"{image.name}"
            )

    print()
    print("MAPPING CHECK PASSED")

    for index in expected:

        image = images[index - 1]
        section = sections[index - 1]

        print()
        print(
            f"SECTION {section['section']}"
        )

        print(
            f"VISUAL  {section['visual']}"
        )

        print(
            f"IMAGE   {image.name}"
        )

        print(
            f"NARRATION: "
            f"{section['narration'][:160]}"
        )


# ============================================================
# WHISPER TRANSCRIPTION
# ============================================================

def transcribe_audio():
    """
    Transcribe voice.mp3 using Whisper with word timestamps.

    Returns:

        {
            "text": "...",
            "segments": [...],
            "words": [...]
        }
    """

    print()
    print("=" * 60)
    print("WHISPER AUDIO TRANSCRIPTION")
    print("=" * 60)

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
        fp16=False,
        word_timestamps=True,
        verbose=False,
    )

    words = []

    for segment in result.get(
        "segments",
        [],
    ):

        for word in segment.get(
            "words",
            [],
        ):

            word_text = word.get(
                "word",
                "",
            ).strip()

            start = word.get(
                "start"
            )

            end = word.get(
                "end"
            )

            if not word_text:
                continue

            if start is None or end is None:
                continue

            words.append(
                {
                    "text": word_text,
                    "normalized": normalize_text(
                        word_text
                    ),
                    "start": float(start),
                    "end": float(end),
                }
            )

    if not words:
        raise RuntimeError(
            "Whisper did not return word timestamps."
        )

    print()
    print(
        f"Whisper words: {len(words)}"
    )

    print(
        f"Whisper text: "
        f"{result.get('text', '').strip()[:300]}"
    )

    return {
        "text": result.get(
            "text",
            "",
        ),
        "segments": result.get(
            "segments",
            [],
        ),
        "words": words,
    }


# ============================================================
# SECTION TIMESTAMP MATCHING
# ============================================================

def find_section_timestamps(
    sections,
    whisper_words,
    audio_duration,
):
    """
    Match each section narration against Whisper's
    word-level timestamps.

    This uses sequential matching because the narration
    occurs in the same order as section_map.txt.

    Returns:

        [
            {
                "section": 1,
                "visual": 1,
                "narration": "...",
                "start": 0.0,
                "end": 17.9,
            },
            ...
        ]
    """

    print()
    print("=" * 60)
    print("MATCHING SECTIONS TO WHISPER TIMESTAMPS")
    print("=" * 60)

    # --------------------------------------------------------
    # Normalize Whisper words.
    # --------------------------------------------------------

    usable_words = []

    for word in whisper_words:

        normalized = word["normalized"]

        if not normalized:
            continue

        usable_words.append(
            word
        )

    if not usable_words:
        raise RuntimeError(
            "No usable Whisper words found."
        )

    # --------------------------------------------------------
    # Build normalized narration words.
    # --------------------------------------------------------

    section_word_lists = []

    for section in sections:

        words = normalize_words(
            section["narration"]
        )

        if not words:
            raise RuntimeError(
                f"Section {section['section']} "
                "contains no usable narration words."
            )

        section_word_lists.append(
            words
        )

    # --------------------------------------------------------
    # Sequential matching.
    # --------------------------------------------------------

    results = []

    search_index = 0

    for section, target_words in zip(
        sections,
        section_word_lists,
    ):

        target_count = len(
            target_words
        )

        best_start = None
        best_end = None
        best_score = 0

        # ----------------------------------------------------
        # Search for the best matching window.
        #
        # We use a slightly larger window than the exact
        # narration length because Whisper can occasionally
        # split or merge words.
        # ----------------------------------------------------

        max_window_extra = max(
            8,
            int(
                target_count * 0.20
            ),
        )

        max_window = (
            target_count
            + max_window_extra
        )

        remaining = (
            len(usable_words)
            - search_index
        )

        if remaining <= 0:
            raise RuntimeError(
                f"Could not find audio words for "
                f"Section {section['section']}."
            )

        # ----------------------------------------------------
        # First try exact-ish sequential matching.
        # ----------------------------------------------------

        for start_index in range(
            search_index,
            len(usable_words),
        ):

            if (
                start_index
                >= len(usable_words)
            ):
                break

            # Avoid searching infinitely far ahead.
            if (
                start_index
                - search_index
                > max_window_extra * 2
            ):
                break

            for window_size in range(
                max(
                    1,
                    target_count
                    - max_window_extra,
                ),
                min(
                    max_window,
                    len(usable_words)
                    - start_index,
                )
                + 1,
            ):

                candidate = usable_words[
                    start_index:
                    start_index + window_size
                ]

                candidate_text = [
                    item["normalized"]
                    for item in candidate
                ]

                # ------------------------------------------------
                # Compare using ordered word overlap.
                # ------------------------------------------------

                if not candidate_text:
                    continue

                # Fuzzy ordered word matching.
                # Handles Whisper variations such as:
                # StockGro -> stock grow
                # multi-crore -> multi core

                def words_similar(a, b):
                    a = normalize_text(a)
                    b = normalize_text(b)

                    if not a or not b:
                        return False

                    if a == b:
                        return True

                    compact_a = a.replace(" ", "")
                    compact_b = b.replace(" ", "")

                    if compact_a == compact_b:
                        return True

                    shorter = min(len(a), len(b))

                    if shorter >= 4:
                        common = sum(
                            char_a == char_b
                            for char_a, char_b in zip(a, b)
                        )

                        similarity = (
                            common / max(len(a), len(b))
                        )

                        if similarity >= 0.70:
                            return True

                    return False

                matched = 0
                candidate_position = 0

                for target_word in target_words:

                    for position in range(
                        candidate_position,
                        len(candidate_text),
                    ):

                        if words_similar(
                            target_word,
                            candidate_text[position],
                        ):
                            matched += 1
                            candidate_position = position + 1
                            break

                score = (
                    matched
                    / max(1, len(target_words))
                )

                # Bonus for matching section boundaries.
                if words_similar(
                    candidate_text[0],
                    target_words[0],
                ):
                    score += 0.10

                if words_similar(
                    candidate_text[-1],
                    target_words[-1],
                ):
                    score += 0.10

                if score > best_score:

                    best_score = score

                    best_start = (
                        candidate[0]["start"]
                    )

                    best_end = (
                        candidate[-1]["end"]
                    )

                    best_match_end_index = (
                        start_index
                        + window_size
                    )

        # ----------------------------------------------------
        # If matching failed, use a fallback based on the
        # remaining audio.
        # ----------------------------------------------------

        if (
            best_start is None
            or best_end is None
            or best_score < 0.35
        ):

            print()
            print(
                f"WARNING: Weak Whisper match "
                f"for Section {section['section']} "
                f"(score={best_score:.2f})"
            )

            # Fallback:
            # Take the next proportional portion of the
            # remaining Whisper timeline.

            remaining_sections = (
                len(sections)
                - len(results)
            )

            remaining_duration = (
                audio_duration
                - (
                    results[-1]["end"]
                    if results
                    else 0.0
                )
            )

            fallback_duration = (
                remaining_duration
                / max(
                    1,
                    remaining_sections,
                )
            )

            fallback_start = (
                results[-1]["end"]
                if results
                else 0.0
            )

            best_start = fallback_start

            best_end = min(
                audio_duration,
                fallback_start
                + fallback_duration,
            )

            best_match_end_index = (
                search_index
                + target_count
            )

        # ----------------------------------------------------
        # Ensure timestamps are valid.
        # ----------------------------------------------------

        best_start = max(
            0.0,
            float(best_start),
        )

        best_end = min(
            audio_duration,
            float(best_end),
        )

        if best_end <= best_start:

            raise RuntimeError(
                f"Invalid timestamp range for "
                f"Section {section['section']}: "
                f"{best_start} -> {best_end}"
            )

        results.append(
            {
                "section": section["section"],
                "visual": section["visual"],
                "narration": section["narration"],
                "start": best_start,
                "end": best_end,
            }
        )

        print()
        print(
            f"SECTION {section['section']}"
        )

        print(
            f"VISUAL  {section['visual']}"
        )

        print(
            f"START   {best_start:.2f}s"
        )

        print(
            f"END     {best_end:.2f}s"
        )

        print(
            f"DURATION "
            f"{best_end - best_start:.2f}s"
        )

        print(
            f"MATCH SCORE: "
            f"{best_score:.2f}"
        )

        # ----------------------------------------------------
        # Continue searching after this section.
        # ----------------------------------------------------

        if (
            "best_match_end_index"
            in locals()
        ):

            search_index = max(
                search_index + 1,
                best_match_end_index,
            )

    # ========================================================
    # FORCE CLEAN CONTINUOUS TIMELINE
    # ========================================================
    #
    # Whisper matching can produce tiny gaps/overlaps.
    # We convert the matched boundaries into a clean,
    # continuous visual timeline.
    #
    # The first visual always starts at 0.
    # The last visual always ends at audio_duration.
    #
    # Internal boundaries use Whisper-derived timestamps.
    # ========================================================

    if not results:
        raise RuntimeError(
            "No section timestamps generated."
        )

    results[0]["start"] = 0.0

    for index in range(
        1,
        len(results),
    ):

        previous_end = results[
            index - 1
        ]["end"]

        current_start = results[
            index
        ]["start"]

        # Use the midpoint when a tiny overlap occurs.
        if current_start < previous_end:

            midpoint = (
                current_start
                + previous_end
            ) / 2.0

            results[
                index - 1
            ]["end"] = midpoint

            results[
                index
            ]["start"] = midpoint

        else:

            # Remove small gaps.
            if (
                current_start
                - previous_end
                < 0.75
            ):

                results[
                    index
                ]["start"] = previous_end

    results[-1]["end"] = audio_duration

    # --------------------------------------------------------
    # Finalize continuous timeline.
    #
    # Whisper timestamps can contain natural pauses between
    # sections. Those pauses should remain on the previous
    # visual rather than causing gaps in the video.
    # --------------------------------------------------------

    for index, item in enumerate(results):

        start = item["start"]
        end = item["end"]

        if end <= start:

            raise RuntimeError(
                f"Section {item['section']} "
                "has invalid final timing."
            )

        if index > 0:

            previous = results[index - 1]

            # Make the current section start exactly where
            # the previous section ends.
            item["start"] = previous["end"]

    # The video must cover the complete audio duration.
    results[0]["start"] = 0.0
    results[-1]["end"] = audio_duration

    # Re-check that every section is valid.
    for item in results:

        if item["end"] <= item["start"]:

            raise RuntimeError(
                f"Invalid final timing for "
                f"Section {item['section']}: "
                f"{item['start']:.2f}s -> "
                f"{item['end']:.2f}s"
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
# VIDEO CREATION
# ============================================================

def create_video():

    print()
    print("=" * 60)
    print("AUTOTUBE AI - WHISPER TIMED VIDEO")
    print("=" * 60)

    # --------------------------------------------------------
    # Required files
    # --------------------------------------------------------

    if not VOICE_FILE.exists():

        raise FileNotFoundError(
            f"Voice file not found: {VOICE_FILE}"
        )

    if not SCRIPT_FILE.exists():

        raise FileNotFoundError(
            f"Script file not found: {SCRIPT_FILE}"
        )

    if not VISUAL_PLAN_FILE.exists():

        raise FileNotFoundError(
            f"Visual plan not found: "
            f"{VISUAL_PLAN_FILE}"
        )

    if not SECTION_MAP_FILE.exists():

        raise FileNotFoundError(
            f"Section map not found: "
            f"{SECTION_MAP_FILE}"
        )

    # --------------------------------------------------------
    # Load data
    # --------------------------------------------------------

    images = get_images()

    visual_plan = get_visual_plan()

    sections = get_section_map()

    if not images:
        raise RuntimeError(
            "No numbered images found in assets/"
        )

    if not visual_plan:
        raise RuntimeError(
            "No visual concepts found."
        )

    if not sections:
        raise RuntimeError(
            "No section mapping found."
        )

    # --------------------------------------------------------
    # Validate mapping.
    # --------------------------------------------------------

    validate_mapping(
        images,
        visual_plan,
        sections,
    )

    # --------------------------------------------------------
    # Validate script.
    # --------------------------------------------------------

    with open(
        SCRIPT_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        script = file.read().strip()

    if not script:

        raise RuntimeError(
            "Script is empty."
        )

    # --------------------------------------------------------
    # Load audio.
    # --------------------------------------------------------

    audio = AudioFileClip(
        str(VOICE_FILE)
    )

    audio_duration = audio.duration

    print()
    print(
        f"Voice duration: "
        f"{audio_duration:.2f} seconds"
    )

    # --------------------------------------------------------
    # Whisper.
    # --------------------------------------------------------

    transcription = transcribe_audio()

    whisper_words = transcription[
        "words"
    ]

    # --------------------------------------------------------
    # Match sections to actual speech timing.
    # --------------------------------------------------------

    timed_sections = find_section_timestamps(
        sections,
        whisper_words,
        audio_duration,
    )

    # --------------------------------------------------------
    # Build visual clips.
    # --------------------------------------------------------

    clips = []

    print()
    print("=" * 60)
    print("SECTION → IMAGE → WHISPER TIMELINE")
    print("=" * 60)

    for item in timed_sections:

        section_number = item[
            "section"
        ]

        visual_number = item[
            "visual"
        ]

        start = item[
            "start"
        ]

        end = item[
            "end"
        ]

        duration = (
            end
            - start
        )

        image_index = (
            visual_number
            - 1
        )

        if (
            image_index < 0
            or image_index >= len(images)
        ):

            audio.close()

            raise RuntimeError(
                f"Visual {visual_number} "
                "does not have a corresponding image."
            )

        image_path = images[
            image_index
        ]

        print()
        print(
            f"[{start:06.2f}s - "
            f"{end:06.2f}s]"
        )

        print(
            f"SECTION : "
            f"{section_number}"
        )

        print(
            f"VISUAL  : "
            f"{visual_number}"
        )

        print(
            f"IMAGE   : "
            f"{image_path.name}"
        )

        print(
            f"DURATION: "
            f"{duration:.2f}s"
        )

        print(
            f"NARRATION: "
            f"{item['narration']}"
        )

        # ----------------------------------------------------
        # Create visual clip.
        #
        # Prefer a local video clip when available.
        # Fall back to the existing numbered image.
        # ----------------------------------------------------

        video_path = None

        videos_dir = Path("assets/videos")

        for extension in (
            ".mp4",
            ".mov",
            ".m4v",
            ".webm",
        ):

            candidate = (
                videos_dir
                / f"{visual_number}{extension}"
            )

            if candidate.exists():

                video_path = candidate
                break

        if video_path:

            print(
                f"VIDEO   : "
                f"{video_path.name}"
            )

            source_video = VideoFileClip(
                str(video_path)
            )

            source_duration = (
                source_video.duration
            )

            if source_duration >= duration:

                clip = source_video.subclipped(
                    0,
                    duration,
                )

            else:

                # Loop short videos until they
                # cover the complete section.
                from moviepy import vfx

                clip = source_video.with_effects(
                    [
                        vfx.Loop(
                            duration=duration
                        )
                    ]
                )

            clip = (
                clip
                .resized(
                    width=IMAGE_WIDTH
                )
                .with_duration(
                    duration
                )
            )

        else:

            print(
                f"IMAGE   : "
                f"{image_path.name}"
            )

            clip = (
                ImageClip(
                    str(image_path)
                )
                .resized(
                    width=IMAGE_WIDTH
                )
                .with_duration(
                    duration
                )
            )

        clips.append(
            clip
        )

    # --------------------------------------------------------
    # Safety check.
    # --------------------------------------------------------

    if not clips:

        audio.close()

        raise RuntimeError(
            "No video clips were created."
        )

    # --------------------------------------------------------
    # Concatenate.
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("CREATING VIDEO")
    print("=" * 60)

    video = concatenate_videoclips(
        clips,
        method="compose",
    )

    # --------------------------------------------------------
    # Attach original narration.
    # --------------------------------------------------------

    video = video.with_audio(
        audio
    )

    # --------------------------------------------------------
    # Render.
    # --------------------------------------------------------

    video.write_videofile(
        str(VIDEO_FILE),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=1,
    )

    # --------------------------------------------------------
    # Cleanup.
    # --------------------------------------------------------

    video.close()

    audio.close()

    for clip in clips:

        try:
            clip.close()

        except Exception:
            pass

    # --------------------------------------------------------
    # Done.
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("VIDEO CREATED SUCCESSFULLY")
    print("=" * 60)

    print()
    print(
        f"Saved: {VIDEO_FILE}"
    )

    print(
        f"Duration: "
        f"{audio_duration:.2f}s"
    )

    print(
        f"Visuals used: "
        f"{len(clips)}"
    )

    print(
        "Timing source: Whisper word timestamps"
    )

    return str(VIDEO_FILE)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    create_video()
