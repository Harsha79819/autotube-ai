"""
AutoTube AI - Multi-Mode Input Agent (agents/multimode_agent.py)

Supports 4 Generation Modes:
1. AI Stock Search (stock): Topic -> Script -> Stock Visuals & FLUX fallback
2. My Own Images/Videos (user_media): Script mapped to user-uploaded assets directly
3. Explainer Style (explainer): Conceptual breakdown with infographic/diagram prompt transformations
4. Upload Flyer/Poster (flyer): Gemini Multimodal Vision analysis -> Promo Script -> Flyer Climax
"""

import json
import mimetypes
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union

from providers.llm import generate_multimodal_cascade, generate_text_cascade

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"


def get_image_filename(image_input):
    """
    Safely extract filename from UploadedFile, Path, or str.
    Completely eliminates "'str' object has no attribute 'name'".
    """
    if hasattr(image_input, "name"):
        return image_input.name
    elif isinstance(image_input, str):
        return os.path.basename(image_input)
    elif isinstance(image_input, Path):
        return image_input.name
    raise TypeError(f"Unexpected image input type: {type(image_input)}")


# ============================================================
# MODE 2: USER MEDIA SCRIPT MAPPING
# ============================================================

def map_script_to_user_assets(
    script_chunks: Union[List[str], Dict[int, str]],
    user_assets: List[Union[str, Path]],
    gemini_call_fn=None,
) -> Dict[int, Path]:
    """
    Map each script chunk / scene index (1..N) to the most contextually relevant
    user-uploaded asset. Falls back gracefully to round-robin mapping if LLM fails.
    """
    if not user_assets:
        return {}

    # Resolve each asset safely regardless of whether it's UploadedFile, Path, or str
    clean_assets: List[Path] = []
    for a in user_assets:
        if hasattr(a, "getbuffer") or hasattr(a, "read"):
            upload_dir = ROOT / "input" / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            fname = get_image_filename(a)
            dest = upload_dir / fname
            if hasattr(a, "getbuffer"):
                dest.write_bytes(a.getbuffer())
            elif hasattr(a, "read"):
                dest.write_bytes(a.read())
            clean_assets.append(dest)
        elif isinstance(a, (str, Path)):
            p = Path(a)
            if p.exists():
                clean_assets.append(p.resolve())
            else:
                found = False
                for search_dir in [ROOT / "input" / "uploads", ROOT / "output" / "uploads", ROOT / "assets", ROOT]:
                    cand = search_dir / get_image_filename(p)
                    if cand.exists():
                        clean_assets.append(cand.resolve())
                        found = True
                        break
                if not found:
                    clean_assets.append(p)
        else:
            clean_assets.append(Path(get_image_filename(a)))

    if not clean_assets:
        return {}

    # Format script chunks into indexed dictionary
    if isinstance(script_chunks, list):
        chunk_dict = {i + 1: chunk for i, chunk in enumerate(script_chunks)}
    elif isinstance(script_chunks, dict):
        chunk_dict = {int(k): str(v) for k, v in script_chunks.items()}
    else:
        chunk_dict = {1: str(script_chunks)}

    asset_map: Dict[int, Path] = {}

    # Prepare prompt for Gemini LLM matching
    asset_catalog = []
    for idx, asset in enumerate(clean_assets, start=1):
        asset_catalog.append(f"File {idx}: {get_image_filename(asset)}")

    scenes_text = []
    for idx, chunk_text in sorted(chunk_dict.items()):
        scenes_text.append(f"Scene {idx}: {chunk_text[:180]}")

    sample_first = get_image_filename(clean_assets[0])
    sample_last = get_image_filename(clean_assets[-1])

    prompt = f"""
You are an expert video editor. We have {len(chunk_dict)} script scenes and {len(clean_assets)} user-uploaded media files.
Assign the most contextually relevant user media file to each scene index.

User Uploaded Media:
{chr(10).join(asset_catalog)}

Script Scenes:
{chr(10).join(scenes_text)}

Rules:
1. Every scene from 1 to {len(chunk_dict)} MUST be assigned one filename from the User Media list.
2. You may reuse files if there are more scenes than files.
3. Return ONLY a valid JSON object where keys are string scene numbers ("1", "2", ...) and values are the exact filenames.
Example:
{{
  "1": "{sample_first}",
  "2": "{sample_last}"
}}
"""

    try:
        if gemini_call_fn:
            response_text = gemini_call_fn(prompt)
        else:
            response_text = generate_text_cascade(prompt)

        # Extract JSON block
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            raw_map = json.loads(json_match.group(0))
            filename_to_path = {get_image_filename(a): a for a in clean_assets}

            for scn_key, fname in raw_map.items():
                try:
                    s_idx = int(scn_key)
                    if fname in filename_to_path:
                        asset_map[s_idx] = filename_to_path[fname]
                    else:
                        # Fuzzy match filename
                        matched = next((a for a in clean_assets if fname.lower() in get_image_filename(a).lower()), None)
                        if matched:
                            asset_map[s_idx] = matched
                except (ValueError, TypeError):
                    continue

    except Exception as err:
        print(f"[multimode_agent] Gemini media mapping notice: {err}. Using round-robin fallback.")

    # Fill any missing scene indices using round-robin distribution
    for s_idx in chunk_dict.keys():
        if s_idx not in asset_map or not asset_map[s_idx]:
            fallback_asset = clean_assets[(s_idx - 1) % len(clean_assets)]
            asset_map[s_idx] = fallback_asset

    return asset_map


def apply_user_assets_to_visuals(
    user_assets_map: Dict[int, Union[str, Path]],
    target_dir: Optional[Path] = None,
) -> List[Path]:
    """
    Copies/converts mapped user assets directly to assets/{i}.jpg and/or assets/{i}.mp4,
    ensuring video_agent renders the user's footage without external stock downloads.
    """
    dest_dir = target_dir or ASSETS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    applied_files = []

    for visual_num, asset_src in sorted(user_assets_map.items()):
        src_path = Path(asset_src)
        if not src_path.exists():
            print(f"Warning: User asset path does not exist: {src_path}")
            continue

        ext = src_path.suffix.lower()
        is_video = ext in {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}

        if is_video:
            target_mp4 = dest_dir / f"{visual_num}.mp4"
            target_jpg = dest_dir / f"{visual_num}.jpg"
            shutil.copy2(src_path, target_mp4)
            # Extract keyframe for video thumbnail/visual plan verification
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-ss", "00:00:00.500",
                        "-i", str(target_mp4),
                        "-vframes", "1",
                        "-q:v", "2",
                        str(target_jpg),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=10,
                )
            except Exception:
                pass
            applied_files.append(target_mp4)
        else:
            target_jpg = dest_dir / f"{visual_num}.jpg"
            if ext in {".jpg", ".jpeg"}:
                shutil.copy2(src_path, target_jpg)
            else:
                # Convert PNG / WEBP to clean JPEG
                try:
                    from PIL import Image
                    with Image.open(src_path) as img:
                        rgb = img.convert("RGB")
                        rgb.save(target_jpg, "JPEG", quality=95)
                except Exception:
                    shutil.copy2(src_path, target_jpg)
            applied_files.append(target_jpg)

    return applied_files


# ============================================================
# MODE 4: FLYER MULTIMODAL VISION EXTRACTION
# ============================================================

def extract_flyer_content(
    flyer_image_path: Union[str, Path],
    gemini_vision_call_fn=None,
) -> Dict:
    """
    Extract structured promotional data from an uploaded flyer or poster image
    using Gemini multimodal vision cascade.
    """
    fpath = Path(flyer_image_path)
    if not fpath.exists():
        raise FileNotFoundError(f"Flyer file not found: {fpath}")

    mime_type, _ = mimetypes.guess_type(str(fpath))
    mime_type = mime_type or "image/jpeg"

    image_bytes = fpath.read_bytes()

    prompt = """
You are an expert marketing visual analyst. Inspect this poster/flyer image thoroughly.
Extract the structured information and return strictly a valid JSON object with these exact keys:

{
  "headline": "<Main event, business, or product headline>",
  "brand_or_organizer": "<Company, organizer, or creator name>",
  "key_offer": "<Discount, special offer, price, prize, or primary message>",
  "key_details": "<Dates, timings, venue/location, registration, or contact numbers>",
  "selling_points": ["<Key highlight 1>", "<Key highlight 2>", "<Key highlight 3>"],
  "call_to_action": "<Clear instructions on what the viewer should do>",
  "tone": "<Energetic / Professional / Urgent / Celebratory / Informative>",
  "primary_language": "<Detected text language: Telugu, English, Hindi, etc.>"
}

Do not include markdown or explanations outside the JSON object.
"""

    try:
        if gemini_vision_call_fn:
            resp_text = gemini_vision_call_fn(prompt, image_bytes, mime_type)
        else:
            resp_text = generate_multimodal_cascade(prompt, image_bytes, mime_type=mime_type)

        json_match = re.search(r"\{[\s\S]*\}", resp_text)
        if json_match:
            data = json.loads(json_match.group(0))
            data["flyer_path"] = str(fpath.resolve())
            return data
    except Exception as err:
        print(f"[multimode_agent] Flyer vision analysis notice: {err}. Using fallback metadata.")

    # Fallback structure
    stem_name = fpath.stem.replace("_", " ").title()
    return {
        "headline": stem_name,
        "brand_or_organizer": "Official Announcement",
        "key_offer": "Special Event & Offer",
        "key_details": "Check flyer for dates and full details.",
        "selling_points": [stem_name, "Limited time opportunity", "Full details on screen"],
        "call_to_action": "Contact or visit today!",
        "tone": "Energetic",
        "primary_language": "Telugu",
        "flyer_path": str(fpath.resolve()),
    }


def generate_script_from_flyer(
    flyer_data: Dict,
    language_style: str = "Telugu",
    gemini_call_fn=None,
) -> Dict:
    """
    Generate an engaging short-form video script package from structured flyer data.
    Ensures Visual N is dedicated to the original flyer.
    """
    lang_str = str(language_style).lower()
    is_telugu = "telugu" in lang_str or "తెలుగు" in str(language_style)
    is_hindi = "hindi" in lang_str or "हिंदी" in str(language_style)

    if is_telugu:
        lang_instruction = """
- Language: Natural, fluent spoken Telugu (తెలుగు లిపి) with high-energy creator hook.
- Title and SCRIPT narration MUST be in Telugu script.
- VISUAL_PLAN descriptions MUST be in concise ENGLISH keywords for visual search.
"""
    elif is_hindi:
        lang_instruction = """
- Language: Natural, engaging spoken Hindi (देवनागरी लिपि).
- Title and SCRIPT narration in Hindi.
- VISUAL_PLAN in English keywords.
"""
    else:
        lang_instruction = """
- Language: Natural, punchy, persuasive English.
- SCRIPT narration in English.
- VISUAL_PLAN in English keywords.
"""

    prompt = f"""
You are a top-tier viral short-form video copywriter.
Create a high-converting 45-60 second YouTube Short / Instagram Reel script based on this flyer information:

Headline: {flyer_data.get('headline')}
Brand/Organizer: {flyer_data.get('brand_or_organizer')}
Key Offer/Hook: {flyer_data.get('key_offer')}
Details & Dates: {flyer_data.get('key_details')}
Highlights: {', '.join(flyer_data.get('selling_points', []))}
Call to Action: {flyer_data.get('call_to_action')}
Tone: {flyer_data.get('tone', 'Energetic')}

Instructions:
{lang_instruction}

Structure Requirements:
1. Hook (first 3 seconds): grab viewer attention immediately with the main benefit or exciting news.
2. Value/Details (middle 30 seconds): explain key benefits, dates, offers clearly.
3. Call to Action (final 10 seconds): direct the viewer to the flyer details.
4. Total visuals: EXACTLY 6 visual concepts.
   - Visuals 1 to 5: B-roll footage/imagery representing the concept.
   - Visual 6 (FINAL): MUST BE "The original uploaded flyer."
5. Section mapping: EXACTLY 6 sections matching the 6 visuals (SECTION 1 | VISUAL 1 through SECTION 6 | VISUAL 6).

Output Format (strict):

TITLE:
<Catchy short title under 60 characters>

SCRIPT:
<Complete spoken narration without stage directions or brackets>

VISUAL_PLAN:
1. <concise English search keywords>
2. <concise English search keywords>
3. <concise English search keywords>
4. <concise English search keywords>
5. <concise English search keywords>
6. The original uploaded flyer.

SECTIONS:
SECTION 1 | VISUAL 1
<narration for section 1>

SECTION 2 | VISUAL 2
<narration for section 2>

SECTION 3 | VISUAL 3
<narration for section 3>

SECTION 4 | VISUAL 4
<narration for section 4>

SECTION 5 | VISUAL 5
<narration for section 5>

SECTION 6 | VISUAL 6
<closing call-to-action narration while showing flyer>
"""

    response_text = ""
    try:
        if gemini_call_fn:
            response_text = gemini_call_fn(prompt)
        else:
            response_text = generate_text_cascade(prompt)
    except Exception as llm_err:
        print(f"[multimode_agent] Flyer script generation notice: {llm_err}. Using smart flyer template...")
        headline = flyer_data.get("headline", "Special Announcement")
        offer = flyer_data.get("key_offer", "Limited time special offer")
        details = flyer_data.get("key_details", "Check details on screen")
        cta = flyer_data.get("call_to_action", "Contact today")
        brand = flyer_data.get("brand_or_organizer", "Official")

        if is_telugu:
            response_text = f"""TITLE:
{headline} - భారీ ఆఫర్స్ & వివరాలు!

SCRIPT:
ఈరోజే చూడండి {headline}! {brand} నుండి వచ్చిన ఈ అద్భుతమైన అవకాశం మీ కోసమే. ఇందులో ప్రత్యేకంగా {offer} లభిస్తోంది. ముఖ్యమైన తేదీలు మరియు వివరాలు చూస్తే {details}. ఇలాంటి సూపర్ డీల్స్ అస్సలు మిస్ కావద్దు! పూర్తి సమాచారం కోసం స్క్రీన్ పై కనిపిస్తున్న వివరాలను చూడండి మరియు {cta}!

VISUAL_PLAN:
1. exciting promotion announcement neon banner
2. special discount offer savings celebration
3. event schedule calendar dates countdown
4. customers happy shopping experience crowd
5. smartphone scanning register booking online
6. The original uploaded flyer.

SECTIONS:
SECTION 1 | VISUAL 1
ఈరోజే చూడండి {headline}!

SECTION 2 | VISUAL 2
{brand} నుండి వచ్చిన ఈ అద్భుతమైన అవకాశం మీ కోసమే.

SECTION 3 | VISUAL 3
ఇందులో ప్రత్యేకంగా {offer} లభిస్తోంది.

SECTION 4 | VISUAL 4
ముఖ్యమైన తేదీలు మరియు వివరాలు చూస్తే {details}.

SECTION 5 | VISUAL 5
ఇలాంటి సూపర్ డీల్స్ అస్సలు మిస్ కావద్దు!

SECTION 6 | VISUAL 6
పూర్తి సమాచారం కోసం స్క్రీన్ పై కనిపిస్తున్న వివరాలను చూడండి మరియు {cta}!
"""
        else:
            response_text = f"""TITLE:
{headline} - Massive Special Offer!

SCRIPT:
Check this out: {headline}! {brand} just announced an incredible update featuring {offer}. Important details: {details}. Don't miss out on this limited-time opportunity. Check out the flyer on screen right now and {cta}!

VISUAL_PLAN:
1. exciting modern event announcement banner
2. special discount promo shopping celebration
3. event schedule calendar dates highlight
4. customers excited celebration retail crowd
5. online registration ticket mobile screen
6. The original uploaded flyer.

SECTIONS:
SECTION 1 | VISUAL 1
Check this out: {headline}!

SECTION 2 | VISUAL 2
{brand} just announced an incredible update.

SECTION 3 | VISUAL 3
Featuring {offer}.

SECTION 4 | VISUAL 4
Important details: {details}.

SECTION 5 | VISUAL 5
Don't miss out on this limited-time opportunity.

SECTION 6 | VISUAL 6
Check out the flyer on screen right now and {cta}!
"""

    # Parse package
    package = _parse_script_package(response_text)

    # Write files to output/
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if package.get("script"):
        (OUTPUT_DIR / "script.txt").write_text(package["script"], encoding="utf-8")
        (OUTPUT_DIR / "tts_script.txt").write_text(package["script"], encoding="utf-8")
    if package.get("visual_plan"):
        (OUTPUT_DIR / "visual_plan.txt").write_text("\n".join(package["visual_plan"]), encoding="utf-8")
    if package.get("sections_raw"):
        (OUTPUT_DIR / "section_map.txt").write_text(package["sections_raw"], encoding="utf-8")

    return package


def _parse_script_package(text: str) -> Dict:
    """Parse TITLE, SCRIPT, VISUAL_PLAN, and SECTIONS from model response."""
    result = {
        "title": "",
        "script": "",
        "visual_plan": [],
        "sections": [],
        "sections_raw": "",
    }

    # Title
    t_match = re.search(r"TITLE:\s*(.*?)(?=\n\s*(?:SCRIPT|VISUAL_PLAN|SECTIONS)|\Z)", text, re.DOTALL | re.IGNORECASE)
    if t_match:
        result["title"] = t_match.group(1).strip()

    # Script
    s_match = re.search(r"SCRIPT:\s*(.*?)(?=\n\s*(?:VISUAL_PLAN|SECTIONS)|\Z)", text, re.DOTALL | re.IGNORECASE)
    if s_match:
        result["script"] = s_match.group(1).strip()

    # Visual Plan
    v_match = re.search(r"VISUAL_PLAN:\s*(.*?)(?=\n\s*SECTIONS|\Z)", text, re.DOTALL | re.IGNORECASE)
    if v_match:
        v_lines = []
        for line in v_match.group(1).strip().splitlines():
            line_clean = line.strip()
            if line_clean and not line_clean.startswith("#"):
                v_lines.append(line_clean)
        result["visual_plan"] = v_lines

    # Sections
    sec_match = re.search(r"SECTIONS:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    if sec_match:
        sec_raw = sec_match.group(1).strip()
        result["sections_raw"] = sec_raw
        pattern = re.compile(
            r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
            re.DOTALL | re.IGNORECASE,
        )
        for m in pattern.finditer(sec_raw):
            result["sections"].append({
                "section": int(m.group(1)),
                "visual": int(m.group(2)),
                "narration": m.group(3).strip(),
            })

    return result


# ============================================================
# MODE 3: EXPLAINER STYLE QUERY TRANSFORMATION
# ============================================================

EXPLAINER_MODIFIERS = [
    "clean technical infographic vector diagram, minimalist educational schematic, high visual clarity",
    "conceptual 3D isometric illustration, modern clean visual explanation, educational design",
    "technical flow chart breakdown, clean motion graphic style, sleek scientific illustration",
    "detailed conceptual diagram, clear labels and visual hierarchy, clean studio lighting",
]

def transform_queries_for_explainer(
    queries: Union[str, List[str]],
) -> Union[str, List[str]]:
    """
    Transforms visual queries for Explainer Style by enriching them with
    infographic, schematic, and conceptual diagram cues suited for FLUX AI & stock.
    """
    is_single = isinstance(queries, str)
    query_list = [queries] if is_single else list(queries)

    transformed = []
    for idx, q in enumerate(query_list):
        cleaned_q = re.sub(r"^\d+[\.\)\:\-]\s*", "", str(q).strip())
        # Remove generic stock photo noise
        cleaned_q = re.sub(r"\b(person|people|happy|smiling|looking at camera|office)\b", "", cleaned_q, flags=re.IGNORECASE).strip()

        modifier = EXPLAINER_MODIFIERS[idx % len(EXPLAINER_MODIFIERS)]
        enhanced = f"{cleaned_q}, {modifier}"
        transformed.append(enhanced)

    return transformed[0] if is_single else transformed
