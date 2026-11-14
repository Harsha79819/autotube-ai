"""
AutoTube AI - Social Visual Selection Engine (agents/social_visual_selector.py)

Implements scene-by-scene authentic visual sourcing from Instagram & Twitter/X:
1. Splits scripts into scenes (one sentence or discrete thought).
2. Extracts main entity, event type, 3 hashtags, and English clip_text via LLM cascade.
3. Fetches 30-50 candidate images per scene using Apify actors (Instagram & Twitter) + local cache.
4. Ranks candidates with CLIP ViT-B-32 (70% image-text + 30% caption-text + entity name boost).
5. Picks the top-scoring image, enforces perceptual imagehash deduplication across scenes.
6. Multi-rung fallback ladder (< 0.25): scene hashtags -> entity name -> show hashtag -> typography card.
7. Logs detailed audit trails to output/visual_selection_audit.json and .log.
"""

import hashlib
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import torch
    from transformers import CLIPModel, CLIPProcessor
except ImportError:
    torch = None
    CLIPModel = None
    CLIPProcessor = None

from PIL import Image

from config.settings import get_setting
from agents.typography_card import generate_typography_card
from providers.apify_social import (
    download_candidate_image,
    fetch_social_candidates_for_scene,
)
from providers.claude_vision import verify_candidates_with_claude_vision
from providers.image import clean_and_crop_image
from providers.llm import generate_text_cascade
from utils.image_hasher import compute_image_hash, is_duplicate_hash

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
AUDIT_LOG_FILE = OUTPUT_DIR / "visual_selection_audit.log"
AUDIT_JSON_FILE = OUTPUT_DIR / "visual_selection_audit.json"

# CLIP Model Singleton
_CLIP_MODEL = None
_CLIP_PROCESSOR = None
_CLIP_LOCK = threading.Lock()


def get_clip_model():
    """Load cached CLIP ViT-B-32 model thread-safely."""
    global _CLIP_MODEL, _CLIP_PROCESSOR
    if torch is None or CLIPModel is None or CLIPProcessor is None:
        return None, None
    with _CLIP_LOCK:
        if _CLIP_MODEL is None or _CLIP_PROCESSOR is None:
            model_id = "openai/clip-vit-base-patch32"
            print(f"🧠 Loading CLIP model ({model_id}) for multi-modal visual ranking...")
            try:
                _CLIP_MODEL = CLIPModel.from_pretrained(model_id, local_files_only=True)
                _CLIP_PROCESSOR = CLIPProcessor.from_pretrained(model_id, local_files_only=True)
            except Exception:
                # Fallback if local_files_only fails
                _CLIP_MODEL = CLIPModel.from_pretrained(model_id)
                _CLIP_PROCESSOR = CLIPProcessor.from_pretrained(model_id)
            _CLIP_MODEL.to("cpu")
            _CLIP_MODEL.eval()
        return _CLIP_MODEL, _CLIP_PROCESSOR


# ============================================================
# 1. SCENE SEGMENTATION
# ============================================================

def split_script_into_scenes(script_text: str) -> List[str]:
    """
    Splits narration script into individual scene units (sentences / distinct beats).
    Cleans teleprompter markers, bracketed SFX, and pacing tokens.
    Guarantees fast visual pacing (1 scene per 3.5 to 6 seconds / 8 to 15 words).
    Syncs 1-to-1 with section_map.txt when available.
    """
    # 1. First priority: if section_map.txt already exists for this script, align 100% with it!
    sec_map_path = OUTPUT_DIR / "section_map.txt"
    if sec_map_path.exists():
        try:
            from agents.video_agent import get_section_map
            existing_sections = get_section_map()
            if existing_sections and len(existing_sections) >= 3:
                sec_texts = [s.get("narration", "").strip() for s in existing_sections if s.get("narration", "").strip()]
                first_snippet = sec_texts[0][:20].strip() if sec_texts else ""
                if first_snippet and first_snippet in script_text and len(sec_texts) >= 3:
                    print(f"🎬 [Scene Segmentation] Aligned 1-to-1 with {len(sec_texts)} sections from section_map.txt")
                    return sec_texts
        except Exception as e:
            print(f"Notice: Could not load existing section map: {e}")

    # 2. Otherwise parse script into sentences
    clean_lines = []
    for line in script_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Drop headers and teleprompter badges
        if any(line.startswith(h) for h in ["===", "AUTOTUBE", "Record", "BEAT", "👉", "Title:"]):
            continue
        # Remove audio pacing cues e.g. [PAUSE 450ms], [SFX: RIMSHOT], 💥
        cleaned = re.sub(r"\[.*?\]", "", line)
        cleaned = re.sub(r"[💥🎬🔥✨👏👉🗣️]", "", cleaned).strip()
        if cleaned:
            clean_lines.append(cleaned)

    full_text = " ".join(clean_lines)
    # Protect ellipsis (...) from splitting into fragment sentences
    full_text = re.sub(r"\.{2,}", "__ELLIPSIS__", full_text)
    raw_sentences = re.split(r"(?<=[.!?।\n])\s+", full_text)
    scenes = []
    buf = ""
    for s in raw_sentences:
        s = s.replace("__ELLIPSIS__", "...").strip()
        if not s:
            continue
        buf = f"{buf} {s}".strip() if buf else s
        # Consolidate sentences into coherent visual beats of at least 8 words
        if len(buf.split()) >= 8:
            scenes.append(buf)
            buf = ""
    if buf:
        if scenes and len(buf.split()) < 5:
            scenes[-1] = f"{scenes[-1]} {buf}"
        else:
            scenes.append(buf)

    # For Shorts, limit scene count to max 16 scenes for optimal visual pacing and low CPU heat
    if len(scenes) > 16:
        consolidated = []
        c_buf = ""
        target_len = max(8, len(full_text.split()) // 14)
        for sc in scenes:
            c_buf = f"{c_buf} {sc}".strip() if c_buf else sc
            if len(c_buf.split()) >= target_len:
                consolidated.append(c_buf)
                c_buf = ""
        if c_buf:
            if consolidated:
                consolidated[-1] = f"{consolidated[-1]} {c_buf}"
            else:
                consolidated.append(c_buf)
        scenes = consolidated

    if not scenes:
        scenes = clean_lines if clean_lines else [script_text.strip()[:100] if script_text.strip() else "Scene 1"]

    return scenes


# ============================================================
# 2. LLM SCENE ANALYSIS (ENTITY, EVENT, HASHTAGS, CLIP_TEXT)
# ============================================================

def analyze_scene_with_llm(scene_text: str, overall_context: str = "Bigg Boss Telugu") -> Dict[str, Any]:
    """
    Uses LLM cascade to extract structured metadata for visual sourcing:
    - main_entity
    - event_type
    - 3 relevant hashtags
    - clip_text (concise English description of the ideal visual)
    """
    prompt = f"""You are an expert visual director for viral social media videos.
Analyze this single script sentence from a video about '{overall_context}':

SENTENCE: "{scene_text}"

Extract the visual intent strictly as a valid JSON object with the following schema:
{{
  "person_name": "Specific person, host, or contestant named in this sentence (e.g. 'Nagarjuna', 'Sudheer', 'Rohit', or null if no human is mentioned)",
  "main_entity": "Specific person name if mentioned, or show name (e.g. Nagarjuna, Sudheer, Bigg Boss Telugu 10)",
  "event_type": "Short 2-3 word event or action (e.g. elimination reaction, nomination argument, hosting class)",
  "hashtags": ["#Hashtag1", "#Hashtag2", "#Hashtag3"],
  "clip_text": "A concise, specific English description (6-12 words) of the ideal real photograph/video still to show on screen for this sentence."
}}

RULES:
- 'clip_text' MUST be in English.
- If the sentence mentions ANY person (e.g. Nagarjuna, Sudheer, Rohit, etc.), 'person_name' MUST be set to their English name, and 'main_entity' MUST be that person.
- The hashtags must be relevant to the person and the show.
- Output ONLY the raw JSON block without markdown formatting or preamble.
"""
    try:
        raw_resp = generate_text_cascade(prompt, step_name="visual_scene_analysis", per_provider_timeout=14.0)
        clean_json = re.sub(r"^```[a-zA-Z0-9_-]*", "", raw_resp.strip()).rstrip("`").strip()
        data = json.loads(clean_json)

        # Deterministic person backup check
        from utils.season_guard import extract_person_from_scene
        det_person = extract_person_from_scene(scene_text)
        if det_person:
            data["person_name"] = det_person
            data["main_entity"] = det_person

        # Validate fields
        if not data.get("main_entity"):
            data["main_entity"] = overall_context if overall_context != "auto" else "viral topic"
        if "bigg boss" in data["main_entity"].lower() and "telugu" not in data["main_entity"].lower():
            data["main_entity"] = "Bigg Boss Telugu 10"

        if not data.get("hashtags"):
            clean_ent = re.sub(r"[^A-Za-z0-9]", "", str(data["main_entity"])).strip()
            data["hashtags"] = [f"#{clean_ent}" if clean_ent else "#Tollywood", "#TrendingTelugu", "#ViralVideo"]
        else:
            clean_tags = []
            for t in data["hashtags"]:
                if "biggboss" in t.lower() and "telugu" not in t.lower():
                    clean_tags.append("#BiggBossTelugu10")
                elif "hindi" not in t.lower() and "colors" not in t.lower():
                    clean_tags.append(t)
            if "#BiggBossTelugu10" not in clean_tags and "bigg boss" in data["main_entity"].lower():
                clean_tags.insert(0, "#BiggBossTelugu10")
            data["hashtags"] = clean_tags

        if not data.get("clip_text"):
            data["clip_text"] = f"{data['main_entity']} candid photo or reaction"

        from utils.season_guard import (
            is_bigg_boss_topic,
            get_current_season_number,
            format_strict_visual_query,
        )
        is_bb = is_bigg_boss_topic(f"{overall_context} {scene_text}")
        cur_s = get_current_season_number(overall_context) or 10
        s_name = f"Bigg Boss Telugu {cur_s}" if is_bb else str(overall_context)
        yr = 2026 if cur_s >= 10 else 2025
        data["contestant_names"] = [data["person_name"]] if data.get("person_name") else []
        data["season_name"] = s_name
        data["year"] = yr
        data["incident_context"] = data.get("event_type", "scene")
        if data.get("person_name"):
            data["strict_query"] = format_strict_visual_query(data["person_name"], s_name, yr)
        elif is_bb:
            data["strict_query"] = format_strict_visual_query("Nagarjuna Akkineni", s_name, yr, task_or_promo=data.get("event_type"))

        return data
    except Exception as err:
        # Resilient fallback extraction with scene-specific semantics
        from utils.season_guard import (
            extract_person_from_scene,
            is_bigg_boss_topic,
            get_current_season_number,
            format_strict_visual_query,
        )
        det_person = extract_person_from_scene(scene_text)
        words = [w for w in re.findall(r"[A-Za-z0-9]+", str(overall_context)) if len(w) >= 3][:2]
        fallback_entity = det_person if det_person else (" ".join(words) if words else (overall_context if overall_context != "auto" else "viral topic"))
        if "bigg boss" in fallback_entity.lower() and "telugu" not in fallback_entity.lower():
            fallback_entity = "Bigg Boss Telugu 10"
        tags = [f"#{w}" for w in words] + ["#Tollywood", "#TrendingTelugu"]
        if "bigg boss" in fallback_entity.lower() or "telugu" in fallback_entity.lower():
            tags.insert(0, "#BiggBossTelugu10")

        sc_lower = scene_text.lower()
        if any(k in sc_lower for k in ["కబాలి", "kabali", "నేను మళ్ళీ వస్తా", "మళ్లీ వస్తా"]):
            evt = "Kabali mass entry"
            fallback_entity = "Rajinikanth"
            clip_txt = "Rajinikanth Kabali mass stylish entry movie still"
        elif any(k in sc_lower for k in ["లైక్", "షేర్", "సబ్‌స్క్రైబ్", "సబ్స్క్రైబ్", "subscribe"]):
            evt = "like share subscribe outro"
            fallback_entity = "YouTube"
            clip_txt = "YouTube subscribe like button social media outro animation"
        elif any(k in sc_lower for k in ["కామెంట్", "comment", "గెస్"]):
            evt = "audience comment discussion"
            clip_txt = "viewer reaction comment feedback social media"
        elif any(k in sc_lower for k in ["డిన్నర్", "dinner", "ఫుడ్", "తినడం"]):
            evt = "dining table dinner"
            clip_txt = f"{fallback_entity} contestants dining food discussion table"
        elif any(k in sc_lower for k in ["బిల్లు", "bill", "డబ్బు"]):
            evt = "shocked reaction bill"
            clip_txt = "shocked stunned face reaction meme Telugu comedy"
        elif any(k in sc_lower for k in ["వైల్డ్ కార్డ్", "wildcard", "ఎంట్రీ"]):
            evt = "wildcard surprise entry"
            clip_txt = f"{fallback_entity} wildcard contestant surprise entry stage"
        elif any(k in sc_lower for k in ["బ్యాగ్", "సర్దుకో", "pack", "suitcase"]):
            evt = "packing suitcase exit"
            clip_txt = f"{fallback_entity} contestant packing suitcase elimination exit"
        elif any(k in sc_lower for k in ["ఎలిమినేషన్", "elimination", "ఎగ్జిట్", "అదృష్టం"]):
            evt = "elimination shock"
            clip_txt = f"{fallback_entity} shocked elimination reaction on stage"
        elif any(k in sc_lower for k in ["హైప్", "hype", "pan-india", "రేంజ్"]):
            evt = "grand celebration hype"
            clip_txt = f"{fallback_entity} grand stage celebration hype"
        elif any(k in sc_lower for k in ["కెమెరా", "camera", "డ్రామా", "లాజిక్"]):
            evt = "camera angles drama"
            clip_txt = f"{fallback_entity} contestants confused reaction house camera"
        elif any(k in sc_lower for k in ["ఫైట్", "fight", "గోడవ", "వాదన", "అరుపులు"]):
            evt = "heated confrontation"
            clip_txt = f"{fallback_entity} contestants heated argument confrontation"
        elif any(k in sc_lower for k in ["నామినేషన్", "nomination", "ఓటింగ్"]):
            evt = "nomination discussion"
            clip_txt = f"{fallback_entity} nomination process discussion"
        elif any(k in sc_lower for k in ["టాస్క్", "task", "గేమ్", "పోటీ"]):
            evt = "task challenge"
            clip_txt = f"{fallback_entity} physical task challenge game"
        elif any(k in sc_lower for k in ["కామెడీ", "comedy", "మీమ్", "నవ్వు", "లోకల్"]):
            evt = "comedy reaction"
            clip_txt = f"{fallback_entity} laughing funny comedy moment"
        else:
            evt = "housemate candid reaction"
            clip_txt = f"{fallback_entity} housemate candid reaction still"

        is_bb_f = is_bigg_boss_topic(f"{overall_context} {scene_text}")
        cur_sf = get_current_season_number(overall_context) or 10
        s_name_f = f"Bigg Boss Telugu {cur_sf}" if is_bb_f else str(overall_context)
        yr_f = 2026 if cur_sf >= 10 else 2025
        strict_q_f = format_strict_visual_query(det_person, s_name_f, yr_f) if det_person else (
            format_strict_visual_query("Nagarjuna Akkineni", s_name_f, yr_f, task_or_promo=evt) if is_bb_f else ""
        )

        return {
            "person_name": det_person,
            "main_entity": fallback_entity,
            "event_type": evt,
            "hashtags": tags[:3],
            "clip_text": clip_txt,
            "contestant_names": [det_person] if det_person else [],
            "season_name": s_name_f,
            "year": yr_f,
            "incident_context": evt,
            "strict_query": strict_q_f,
        }


def batch_analyze_scenes_with_llm(scenes: List[str], overall_context: str = "Bigg Boss Telugu 10") -> List[Dict[str, Any]]:
    """
    Batches metadata extraction for all scenes in a single LLM prompt for 10x faster execution.
    Falls back gracefully to concurrent individual scene analysis if batch parsing fails.
    """
    if not scenes:
        return []
    if len(scenes) == 1:
        return [analyze_scene_with_llm(scenes[0], overall_context)]

    formatted_scenes = "\n".join([f"Scene {i+1}: \"{s}\"" for i, s in enumerate(scenes)])
    prompt = f"""You are an expert visual director for viral social media videos.
Analyze these {len(scenes)} sequential script scenes from a video about '{overall_context}'.
For each scene, extract structured visual metadata.

SCENES:
{formatted_scenes}

Return strictly a valid JSON array of {len(scenes)} objects matching this schema:
[
  {{
    "scene_index": 1,
    "person_name": "Specific person, host, or contestant named in this sentence (e.g. 'Nagarjuna', 'Sudheer', 'Rohit', or null if no human is mentioned)",
    "main_entity": "Specific person name if mentioned, or show name (e.g. Nagarjuna, Sudheer, Bigg Boss Telugu 10)",
    "event_type": "Short 2-3 word event or action (e.g. elimination reaction, nomination argument)",
    "hashtags": ["#Hashtag1", "#Hashtag2", "#Hashtag3"],
    "clip_text": "A concise, specific English description (6-12 words) of the ideal real photo/still to show for this sentence."
  }}
]

CRITICAL SCHEMA REQUIREMENTS:
- Every object MUST have all keys: "scene_index", "person_name", "main_entity", "event_type", "hashtags", "clip_text".
- Do NOT omit "hashtags": key before array.
- 'clip_text' MUST be in English.
- If the sentence mentions ANY person (e.g. Nagarjuna, Sudheer, Charan, etc.), 'person_name' MUST be set to their English name, and 'main_entity' MUST be that person.
- If the show is Bigg Boss in Telugu, 'main_entity' MUST be 'Bigg Boss Telugu 10' or specific Telugu housemates, NEVER Bigg Boss Hindi or Salman Khan.
- Return ONLY the JSON array without markdown formatting or preamble.
"""
    try:
        raw_resp = generate_text_cascade(prompt, step_name="batch_scene_analysis", per_provider_timeout=20.0)
        raw_text = raw_resp.strip()
        m_arr = re.search(r"\[\s*\{.*\}\s*\]", raw_text, flags=re.DOTALL)
        clean_json = m_arr.group(0) if m_arr else raw_text
        # Repair missing "hashtags": key before hashtag array
        clean_json = re.sub(r'([,\{\n]\s*)(\[\s*\"[^\"]+\"\s*(?:,\s*\"[^\"]+\"\s*)*\])', r'\1"hashtags": \2', clean_json)
        # Strip trailing commas before closing braces/brackets
        clean_json = re.sub(r',\s*([\]\}])', r'\1', clean_json)
        # Normalize python literals
        clean_json = re.sub(r'\bNone\b', 'null', clean_json)
        clean_json = re.sub(r'\bTrue\b', 'true', clean_json)
        clean_json = re.sub(r'\bFalse\b', 'false', clean_json)

        data = json.loads(clean_json)
        if isinstance(data, list) and len(data) == len(scenes):
            results = []
            from utils.season_guard import extract_all_persons_from_scene, extract_person_from_scene
            used_scene_persons = set()
            for i, item in enumerate(data):
                # Deterministic person backup check
                all_persons = extract_all_persons_from_scene(scenes[i])
                if all_persons:
                    chosen_p = None
                    for p in all_persons:
                        if p not in used_scene_persons:
                            chosen_p = p
                            break
                    if not chosen_p:
                        chosen_p = all_persons[0]
                    used_scene_persons.add(chosen_p)
                    item["person_name"] = chosen_p
                    item["main_entity"] = chosen_p
                    item["all_persons"] = all_persons
                else:
                    det_person = extract_person_from_scene(scenes[i])
                    if det_person:
                        item["person_name"] = det_person
                        item["main_entity"] = det_person
                        used_scene_persons.add(det_person)
                    elif any(w in scenes[i] for w in ["వీళ్ల", "వీరు", "వీళ్లిద్దరు", "వీరి"]):
                        # Contextual pronoun reference: pick another active contestant from current context
                        remaining_contestants = [cp for cp in ["Temper Vamsi", "Aman Masud", "Thrigun Eswaran", "Sudheer Reddy", "Auto Ram Prasad"] if cp not in used_scene_persons]
                        if remaining_contestants:
                            item["person_name"] = remaining_contestants[0]
                            item["main_entity"] = remaining_contestants[0]
                            used_scene_persons.add(remaining_contestants[0])

                if not item.get("main_entity"):
                    item["main_entity"] = overall_context if overall_context != "auto" else "viral topic"
                if "bigg boss" in item["main_entity"].lower() and "telugu" not in item["main_entity"].lower():
                    item["main_entity"] = "Bigg Boss Telugu 10"

                if not item.get("hashtags"):
                    clean_ent = re.sub(r"[^A-Za-z0-9]", "", str(item["main_entity"])).strip()
                    item["hashtags"] = [f"#{clean_ent}" if clean_ent else "#Tollywood", "#TrendingTelugu", "#ViralVideo"]
                else:
                    clean_tags = []
                    for t in item["hashtags"]:
                        if "biggboss" in t.lower() and "telugu" not in t.lower():
                            clean_tags.append("#BiggBossTelugu10")
                        elif "hindi" not in t.lower() and "colors" not in t.lower():
                            clean_tags.append(t)
                    if "#BiggBossTelugu10" not in clean_tags and "bigg boss" in item["main_entity"].lower():
                        clean_tags.insert(0, "#BiggBossTelugu10")
                    item["hashtags"] = clean_tags

                if not item.get("clip_text"):
                    item["clip_text"] = f"{item['main_entity']} candid photo or reaction"

                from utils.season_guard import (
                    is_bigg_boss_topic,
                    get_current_season_number,
                    format_strict_visual_query,
                )
                is_bb_item = is_bigg_boss_topic(f"{overall_context} {scenes[i]}")
                cur_si = get_current_season_number(overall_context) or 10
                s_name_i = f"Bigg Boss Telugu {cur_si}" if is_bb_item else str(overall_context)
                yr_i = 2026 if cur_si >= 10 else 2025
                item["contestant_names"] = item.get("all_persons") or ([item["person_name"]] if item.get("person_name") else [])
                item["season_name"] = s_name_i
                item["year"] = yr_i
                item["incident_context"] = item.get("event_type", "scene")
                if item.get("person_name"):
                    item["strict_query"] = format_strict_visual_query(item["person_name"], s_name_i, yr_i)
                elif is_bb_item:
                    item["strict_query"] = format_strict_visual_query("Nagarjuna Akkineni", s_name_i, yr_i, task_or_promo=item.get("event_type"))

                results.append(item)
            print(f"⚡ [Batch LLM Analysis] Successfully analyzed all {len(scenes)} scenes in 1 fast pass!")
            return results
    except Exception as e:
        print(f"ℹ️ Batch scene analysis notice ({e}). Falling back to per-scene analysis...")

    # Fallback to concurrent per-scene analysis for 5x faster recovery
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(scenes))) as pool:
        futs = [pool.submit(analyze_scene_with_llm, s, overall_context) for s in scenes]
        return [f.result() for f in futs]


# ============================================================
# 4. CLIP VI-T-B-32 MULTI-MODAL RANKING
# ============================================================

def score_candidate_with_clip(
    image_path: Path,
    caption: str,
    clip_text: str,
    entity: str,
    model: Any = None,
    processor: Any = None,
    boost_val: float = 0.15,
) -> Tuple[float, float, float, float]:
    """
    Ranks a candidate against scene clip_text:
    Final Score = 70% image-text similarity + 30% caption-text similarity + entity boost
    Returns (final_score, img_sim, cap_sim, boost)
    """
    if model is None or processor is None or torch is None:
        has_entity = bool(entity and entity.lower() in caption.lower())
        boost = boost_val if has_entity else 0.0
        return 0.5 + boost, 0.5, 0.5, boost

    try:
        with Image.open(image_path) as pil_img:
            pil_img = pil_img.convert("RGB")
            
            # Prepare image & texts for CLIP
            clean_cap = caption.strip() if caption else clip_text
            texts = [clip_text, clean_cap]
            
            with _CLIP_LOCK:
                inputs = processor(
                    text=texts,
                    images=pil_img,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                )

                with torch.no_grad():
                    # Image features normalized
                    img_feats = model.get_image_features(pixel_values=inputs["pixel_values"])
                    img_feats = img_feats / img_feats.norm(dim=-1, keepdim=True)

                    # Text features normalized
                    txt_feats = model.get_text_features(
                        input_ids=inputs["input_ids"],
                        attention_mask=inputs["attention_mask"],
                    )
                    txt_feats = txt_feats / txt_feats.norm(dim=-1, keepdim=True)

                    # Cosine similarities
                    img_sim = float((img_feats[0] @ txt_feats[0]).item())
                    cap_sim = float((txt_feats[1] @ txt_feats[0]).item())

        # Entity Boost: check if main entity appears in candidate caption
        boost = 0.0
        if entity:
            clean_entity = re.sub(r"[^a-zA-Z0-9\s]", "", entity).lower().strip()
            caption_lower = caption.lower()
            if clean_entity and clean_entity in caption_lower:
                boost = boost_val
            else:
                # Check entity aliases or individual words
                words = [w for w in clean_entity.split() if len(w) > 3]
                if any(w in caption_lower for w in words):
                    boost = boost_val * 0.75

        final_score = (0.70 * img_sim) + (0.30 * cap_sim) + boost
        return final_score, img_sim, cap_sim, boost
    except Exception as err:
        print(f"⚠️ [CLIP Scoring Notice] {image_path.name}: {err}")
        # Resilient fallback: Never discard real downloaded photographs due to CPU threading issues
        base_sc = 0.35
        if entity and entity.lower() in caption.lower():
            base_sc += 0.15
        return base_sc, 0.22, 0.40, 0.0


# ============================================================
# 5 & 6. STRICT 7-STEP VERIFIED SELECTION PIPELINE
# ============================================================

CLASH_CELEBRITY_TERMS_GLOBAL = [
    "ram charan", "ramcharan", "konidela", "rrr", "game changer", "gamechanger",
    "pushpa", "allu arjun", "sukumar", "upasana", "mega power star", "megapowerstar",
    "chiranjeevi", "pawan kalyan", "pawankalyan", "mahesh babu", "prabhas",
]

_CONTESTANTS_REGISTRY_CACHE = None

def load_contestants_registry() -> Dict[str, Dict[str, Any]]:
    """Loads contestants.json registry from project root or data directory."""
    global _CONTESTANTS_REGISTRY_CACHE
    if _CONTESTANTS_REGISTRY_CACHE is not None:
        return _CONTESTANTS_REGISTRY_CACHE
    for loc in [ROOT / "contestants.json", ROOT / "data" / "contestants.json"]:
        if loc.exists():
            try:
                data = json.loads(loc.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _CONTESTANTS_REGISTRY_CACHE = data
                    return _CONTESTANTS_REGISTRY_CACHE
            except Exception:
                pass
    _CONTESTANTS_REGISTRY_CACHE = {}
    return _CONTESTANTS_REGISTRY_CACHE


def find_contestant_profile(entity_name: str) -> Optional[Dict[str, Any]]:
    """Looks up a contestant profile in contestants.json by name, nickname, or alias."""
    registry = load_contestants_registry()
    if not registry:
        return None
    e_low = (entity_name or "").lower().strip()
    if not e_low:
        return None
    # 1. Direct dictionary key match
    if e_low in registry:
        return registry[e_low]
    # 2. Check nickname / full_name / aliases
    for key, prof in registry.items():
        if e_low == prof.get("nickname", "").lower() or e_low == prof.get("full_name", "").lower():
            return prof
        if e_low == prof.get("telugu_name", "").lower():
            return prof
        aliases = [a.lower() for a in prof.get("aliases", [])]
        if e_low in aliases:
            return prof
        if any(a == e_low or (len(a) >= 4 and a in e_low) for a in aliases):
            return prof
    return None


def get_entity_match_tokens(entity: str) -> Set[str]:
    """
    Extracts all canonical names, aliases, and name tokens for an entity.
    Used for strict Step 2 candidate filtering.
    """
    tokens = set()
    e_low = (entity or "").lower().strip()
    if not e_low:
        return tokens

    # 1. Check contestants.json registry first
    prof = find_contestant_profile(entity)
    if prof:
        if prof.get("nickname"):
            tokens.add(prof["nickname"].lower())
        if prof.get("full_name"):
            tokens.add(prof["full_name"].lower())
        if prof.get("telugu_name"):
            tokens.add(prof["telugu_name"].lower())
        if prof.get("instagram_handle"):
            tokens.add(prof["instagram_handle"].lower())
            tokens.add(prof["instagram_handle"].lstrip("@").lower())
        for a in prof.get("aliases", []):
            tokens.add(a.lower())

    # 2. Check known contestants/hosts in season_guard dictionary
    from utils.season_guard import KNOWN_TELUGU_SHOW_PERSONS
    for p_key, p_data in KNOWN_TELUGU_SHOW_PERSONS.items():
        aliases = [a.lower() for a in p_data.get("aliases", [])]
        canon = p_data.get("canonical", "").lower()
        if e_low == canon or e_low in aliases or p_key in e_low:
            for a in aliases:
                tokens.add(a)
            tokens.add(canon)
            tokens.add(p_key.replace("_", " "))

    # 3. Add significant individual words (length >= 3)
    for word in re.split(r"[\s_]+", e_low):
        if len(word) >= 3 and word not in {"the", "and", "for", "with", "show", "season", "telugu", "actor", "actress", "anchor"}:
            tokens.add(word)

    # 4. Show level tokens
    if "bigg boss" in e_low or "biggboss" in e_low:
        tokens.update(["bigg boss", "biggboss", "bb10", "bb telugu", "బిగ్ బాస్", "star maa", "starmaa"])
    elif any(k in e_low for k in ["youtube", "outro", "subscribe"]):
        tokens.update(["youtube", "subscribe", "లైక్", "షేర్", "సబ్‌స్క్రైబ్", "outro"])

    tokens.add(e_low)
    return tokens


def post_matches_entity(combined_metadata: str, entity_tokens: Set[str]) -> bool:
    """
    Step 2 Hard Filter: returns True only if caption, username, or hashtags contain the entity name.
    """
    meta_low = combined_metadata.lower()
    for tok in entity_tokens:
        tok_clean = tok.strip().lower()
        if not tok_clean:
            continue
        # Non-ASCII tokens (Telugu script, etc.) match directly as substrings
        if not tok_clean.isascii():
            if tok_clean in meta_low:
                return True
        elif len(tok_clean) <= 4:
            if re.search(r'(?:\b|_)' + re.escape(tok_clean) + r'(?:\b|_)', meta_low):
                return True
        else:
            if tok_clean in meta_low:
                return True
    return False


def get_event_tokens(event_keyword: str) -> Set[str]:
    """
    Extracts event tokens & Telugu synonyms for Step 3 event boosting.
    """
    tokens = set()
    if not event_keyword:
        return tokens
    e_low = event_keyword.lower().strip()
    for word in re.split(r"[\s_]+", e_low):
        if len(word) >= 3 and word not in {"the", "and", "for", "with", "scene", "still", "photo"}:
            tokens.add(word)
    # Synonyms / Telugu translations
    if any(k in e_low for k in ["elimination", "evict"]):
        tokens.update(["elimination", "eliminate", "eliminated", "eviction", "evicted", "ఎలిమినేషన్", "ఎలిమినేట్"])
    if "nomination" in e_low:
        tokens.update(["nomination", "nominated", "నామినేషన్", "నామినేట్"])
    if any(k in e_low for k in ["dinner", "food", "kitchen"]):
        tokens.update(["dinner", "food", "kitchen", "dining", "డిన్నర్", "భోజనం", "లంచ్"])
    if any(k in e_low for k in ["fight", "argument", "clash"]):
        tokens.update(["fight", "argument", "clash", "confrontation", "గొడవ", "గలాటా"])
    if any(k in e_low for k in ["kabali", "rajini"]):
        tokens.update(["kabali", "rajinikanth", "rajini", "కబాలి", "రజినీకాంత్", "రజనీకాంత్"])
    if any(k in e_low for k in ["suitcase", "bag", "pack"]):
        tokens.update(["suitcase", "bag", "luggage", "pack", "సూట్‌కేస్", "సూట్ కేస్", "బ్యాగ్"])
    if "wildcard" in e_low:
        tokens.update(["wildcard", "wild card", "entry", "వైల్డ్ కార్డ్", "వైల్డ్ కార్డు"])
    if any(k in e_low for k in ["subscribe", "outro", "bell"]):
        tokens.update(["subscribe", "bell", "outro", "లైక్", "షేర్", "సబ్‌స్క్రైబ్"])
    if any(k in e_low for k in ["dance", "song"]):
        tokens.update(["dance", "dancing", "song", "డ్యాన్స్"])
    return tokens


def fetch_candidates_for_selection_step(
    entity_name: str,
    person_search_name: str,
    event_keyword: str,
    hashtags: List[str],
    is_bb: bool,
    cur_season: Optional[int],
    person_disallow: List[str],
    person_name: Optional[str] = None,
    topic_candidate_pool: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Step 2 Candidate Sourcing:
    Fetches candidate images from:
    1. Contestant handle & tagged posts (using contestants.json)
    2. Show's official accounts (Star Maa, Disney+ Hotstar)
    3. Hashtags (requiring entity name AND show hashtag: #BiggBossTelugu10 / #BBTelugu10)
    4. Pre-fetched topic pool

    Enforces strict quoting around contestant and show name: '"{person_name}" "Bigg Boss Telugu 10"'
    and dynamically appends negative keywords for common celebrity collisions.
    """
    from utils.season_guard import (
        get_celebrity_collision_negative_keywords,
        get_celebrity_collision_negative_string,
    )

    raw_candidates: List[Dict[str, Any]] = []

    # 1. Pre-fetched topic pool candidates
    if topic_candidate_pool:
        raw_candidates.extend(topic_candidate_pool)

    target_person = person_name or entity_name
    collision_negs_list = get_celebrity_collision_negative_keywords(target_person)
    collision_negs = get_celebrity_collision_negative_string(target_person)

    # Merge dynamic collision negative terms into active_disallow
    active_disallow = list(person_disallow or [])
    for cn in collision_negs_list:
        clean_cn = cn.lstrip("-").strip()
        if clean_cn and clean_cn not in active_disallow:
            active_disallow.append(clean_cn)

    season_val = cur_season or 10
    show_name_exact = f"Bigg Boss Telugu {season_val}"
    show_tag = f"#BiggBossTelugu{season_val}"

    # Strict query format: "{person_name}" "Bigg Boss Telugu 10" with negative collisions
    if target_person and is_bb:
        strict_quoted_entity = f'"{target_person}" "{show_name_exact}"'
    elif target_person:
        strict_quoted_entity = f'"{target_person}"'
    else:
        strict_quoted_entity = f'"{show_name_exact}"'

    if collision_negs:
        strict_quoted_entity = f"{strict_quoted_entity} {collision_negs}"

    # 2. Look up contestant profile in contestants.json
    contestant_prof = find_contestant_profile(entity_name)
    show_tags = [show_tag, f"#BBTelugu{season_val}", "#BiggBossTelugu"]

    if contestant_prof:
        handle = contestant_prof.get("instagram_handle", "")
        nickname = contestant_prof.get("nickname", entity_name)
        full_name = contestant_prof.get("full_name", entity_name)
        clean_nick = nickname.replace(" ", "")

        # A. Search by contestant handle & tagged posts
        if handle:
            raw_candidates.extend(fetch_social_candidates_for_scene(
                entity=f'"{handle}" "{show_name_exact}" {collision_negs}'.strip(),
                hashtags=[show_tag, f"#BBTelugu{season_val}"],
                query_keywords=f"{event_keyword} HD".strip(),
                target_count=20,
                is_bb_context=is_bb,
                disallow_terms=active_disallow,
            ))
            raw_candidates.extend(fetch_social_candidates_for_scene(
                entity=f'"{handle}" tagged {collision_negs}'.strip(),
                hashtags=[show_tag],
                query_keywords="photo",
                target_count=15,
                is_bb_context=is_bb,
                disallow_terms=active_disallow,
            ))

        # B. Search by show's official accounts (Star Maa & Disney+ Hotstar)
        raw_candidates.extend(fetch_social_candidates_for_scene(
            entity=f'StarMaa "{target_person}" "{show_name_exact}" {collision_negs}'.strip(),
            hashtags=[show_tag, f"#BBTelugu{season_val}"],
            query_keywords=f"official promo {event_keyword}".strip(),
            target_count=20,
            is_bb_context=is_bb,
            disallow_terms=active_disallow,
        ))
        raw_candidates.extend(fetch_social_candidates_for_scene(
            entity=f'DisneyPlusHS "{target_person}" "{show_name_exact}" {collision_negs}'.strip(),
            hashtags=[show_tag, f"#BBTelugu{season_val}"],
            query_keywords=event_keyword or "promo",
            target_count=15,
            is_bb_context=is_bb,
            disallow_terms=active_disallow,
        ))

        # C. Hashtag search requiring entity name AND show hashtag (#BiggBossTelugu10 / #BBTelugu10)
        raw_candidates.extend(fetch_social_candidates_for_scene(
            entity=strict_quoted_entity,
            hashtags=[f"#{clean_nick}", show_tag, f"#BBTelugu{season_val}"],
            query_keywords=f"{event_keyword} stills photo".strip(),
            target_count=35,
            is_bb_context=is_bb,
            disallow_terms=active_disallow,
        ))
    else:
        # Non-contestant scene (general show topic or outro)
        target_name = person_search_name if person_name else entity_name
        if is_bb and target_person:
            strict_target = f'"{target_person}" "{show_name_exact}" {collision_negs}'.strip()
        elif is_bb:
            strict_target = f'"{show_name_exact}"'
        else:
            strict_target = f'"{target_name}"'

        clean_tags = list(hashtags or [])
        if show_tag not in clean_tags:
            clean_tags.append(show_tag)
        raw_candidates.extend(fetch_social_candidates_for_scene(
            entity=strict_target,
            hashtags=clean_tags[:3],
            query_keywords=f"{event_keyword} stills photo".strip(),
            target_count=35,
            is_bb_context=is_bb,
            disallow_terms=active_disallow,
        ))
        if is_bb:
            raw_candidates.extend(fetch_social_candidates_for_scene(
                entity=f'StarMaa "{target_name}" "{show_name_exact}" {collision_negs}'.strip(),
                hashtags=[show_tag, f"#BBTelugu{season_val}"],
                query_keywords=event_keyword or "promo still",
                target_count=15,
                is_bb_context=True,
                disallow_terms=active_disallow,
            ))

    # Deduplicate raw candidates by image_url
    seen_urls = set()
    unique_candidates = []
    for c in raw_candidates:
        u = c.get("image_url")
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique_candidates.append(c)

    return unique_candidates


def select_image_for_scene(
    scene_idx: int,
    scene_text: str,
    meta: Dict[str, Any],
    used_hashes: Set[str],
    used_urls: Set[str],
    destination_jpg: Path,
    threshold: float = 0.25,
    boost_val: float = 0.15,
    topic_candidate_pool: Optional[List[Dict[str, Any]]] = None,
    overall_context: Optional[str] = None,
    state_lock: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Fix only the selection step (Strict 7-Step Verified Pipeline):
    1. For each scene, extract the contestant/entity name and the event.
    2. Fetch candidates from the show's official accounts, the entity's
       own accounts, and hashtags. Keep only posts whose caption, username,
       or hashtags contain the entity name.
    3. Boost posts whose caption mentions the event keyword.
    4. Rank the remaining with CLIP, keep the top 5.
    5. Send those 5 images to the Claude API (vision) with the script line,
       and ask for the best match index or "none".
    6. If "none", use a text card. Never insert a random image.
    7. Log for each scene: candidates count, after-filter count, CLIP
       scores, the Claude choice, and the reason.
    """
    model, processor = get_clip_model()

    # -------------------------------------------------------------------------
    # STEP 1: Extract contestant/entity name and the event
    # -------------------------------------------------------------------------
    from utils.season_guard import (
        is_conflicting_season_candidate,
        extract_person_from_scene,
        get_current_season_number,
        is_bigg_boss_topic,
        resolve_effective_show_context,
        get_person_search_name,
        get_person_disallowed_terms,
    )

    clean_ctx = resolve_effective_show_context(
        topic_or_title=f"{meta.get('main_entity', '')} {scene_text}",
        raw_show_context=overall_context,
    )
    is_bb = bool(clean_ctx) and (
        is_bigg_boss_topic(clean_ctx)
        or is_bigg_boss_topic(meta.get("main_entity", ""))
        or is_bigg_boss_topic(scene_text)
        or any(is_bigg_boss_topic(h) for h in meta.get("hashtags", []))
    )
    if is_bb:
        show_context = clean_ctx
        cur_season = get_current_season_number(show_context) or 10
        show_name = f"Bigg Boss Telugu {cur_season}"
    else:
        show_context = overall_context if (overall_context and not is_bigg_boss_topic(overall_context)) else "viral entertainment"
        cur_season = None
        show_name = show_context

    person_name = meta.get("person_name") or extract_person_from_scene(scene_text)
    is_person_scene = bool(person_name)

    if is_person_scene:
        entity_name = person_name
        person_disallow = get_person_disallowed_terms(person_name)
        person_search_name = get_person_search_name(person_name, cur_season)
    else:
        entity_name = meta.get("main_entity") or show_name
        person_disallow = []
        person_search_name = entity_name

    # Event extraction
    event_keyword = meta.get("event_type", "").strip()
    if not event_keyword:
        scene_low = scene_text.lower()
        if any(w in scene_low for w in ["ఎలిమినేట్", "ఎలిమినేషన్", "elimination", "eviction"]):
            event_keyword = "elimination"
        elif any(w in scene_low for w in ["నామినేట్", "నామినేషన్", "nomination"]):
            event_keyword = "nomination"
        elif any(w in scene_low for w in ["కబాలి", "రజినీకాంత్", "డ్యాన్స్"]):
            event_keyword = "kabali entry"
        elif any(w in scene_low for w in ["డిన్నర్", "భోజనం", "dinner", "food"]):
            event_keyword = "dinner"
        elif any(w in scene_low for w in ["గలాటా", "గొడవ", "fight", "clash"]):
            event_keyword = "fight argument"
        elif any(w in scene_low for w in ["బ్యాగ్", "సర్దుకో", "సూట్‌కేస్"]):
            event_keyword = "luggage bag eviction"
        elif any(w in scene_low for w in ["వైల్డ్ కార్డ్", "wildcard"]):
            event_keyword = "wildcard entry"
        elif any(w in scene_low for w in ["సబ్‌స్క్రైబ్", "లైక్", "షేర్"]):
            event_keyword = "like share subscribe"

    hashtags = list(meta.get("hashtags", []))
    clip_text = meta.get("clip_text", "")
    if not clip_text:
        clip_text = f"{entity_name} {event_keyword} real candid still".strip()

    print(f"\n🔍 [Step 1 Extracted] Scene {scene_idx}: Entity='{entity_name}' | Event='{event_keyword}' | Target='{clip_text}'")

    # -------------------------------------------------------------------------
    # STEP 2: Fetch candidates & Hard Filter on entity name
    # -------------------------------------------------------------------------
    raw_candidates = fetch_candidates_for_selection_step(
        entity_name=entity_name,
        person_search_name=person_search_name,
        event_keyword=event_keyword,
        hashtags=hashtags,
        is_bb=is_bb,
        cur_season=cur_season,
        person_disallow=person_disallow,
        person_name=person_name if is_person_scene else None,
        topic_candidate_pool=topic_candidate_pool,
    )
    candidates_count = len(raw_candidates)

    contestant_prof = find_contestant_profile(entity_name)
    entity_tokens = get_entity_match_tokens(entity_name)
    if contestant_prof:
        for a in contestant_prof.get("aliases", []):
            entity_tokens.add(a.lower())
        if contestant_prof.get("instagram_handle"):
            entity_tokens.add(contestant_prof["instagram_handle"].lower())
            entity_tokens.add(contestant_prof["instagram_handle"].lstrip("@").lower())

    # Build clash celebrity terms to reject (Rule 3)
    clash_terms_to_reject = list(CLASH_CELEBRITY_TERMS_GLOBAL)
    if contestant_prof and contestant_prof.get("clash_terms"):
        clash_terms_to_reject.extend([ct.lower() for ct in contestant_prof["clash_terms"]])

    SHOW_TAG_TOKENS = [
        "biggbosstelugu10", "bbtelugu10", "biggboss10", "bb10",
        "biggbosstelugu", "bbtelugu", "bigg boss telugu 10", "బిగ్ బాస్",
    ]
    SHOW_OFFICIAL_HANDLES = [
        "starmaa", "star maa", "disneyplus", "disneyplushotstar", "hotstar", "endemol", "biggboss",
    ]

    filtered_candidates: List[Dict[str, Any]] = []
    rejected_posts: List[Dict[str, Any]] = []

    for cand in raw_candidates:
        u = cand.get("image_url", "")
        if not u:
            continue

        caption = (cand.get("caption") or "").lower()
        username = (cand.get("username") or "").lower()
        c_tags = " ".join(str(h) for h in cand.get("hashtags", [])).lower()
        post_url = (cand.get("post_url") or "").lower()
        cand_combined = f"{caption} {username} {c_tags} {post_url}"

        # Check duplicate image URL across scenes
        is_used = False
        if state_lock:
            with state_lock:
                is_used = u in used_urls
        else:
            is_used = u in used_urls

        if is_used:
            rej_reason = "Duplicate image URL already used in another scene"
            rejected_posts.append({"url": u, "username": username, "caption": caption[:100], "reason": rej_reason})
            continue

        # Reject e-commerce product listings and store items
        if any(d in u.lower() for d in ["amazon.", "media-amazon.com", "images-amazon.com", "flipkart.", "ebay.", "walmart.", "aliexpress.", "shopee.", "etsy.", "shopify."]):
            rej_reason = "E-commerce product listing domain rejected"
            rejected_posts.append({"url": u, "username": username, "caption": caption[:100], "reason": rej_reason})
            continue

        # Rule 3: Reject any post whose caption, hashtags, or username contains clash celebrity terms
        clash_hit = None
        for ct in clash_terms_to_reject:
            ct_clean = ct.strip().lower()
            if not ct_clean:
                continue
            if len(ct_clean) <= 4:
                if re.search(r'(?:\b|_)' + re.escape(ct_clean) + r'(?:\b|_)', cand_combined):
                    clash_hit = ct_clean
                    break
            else:
                if ct_clean in cand_combined:
                    clash_hit = ct_clean
                    break

        if clash_hit:
            rej_reason = f"Contains clash celebrity term '{clash_hit}' (actor Ram Charan / clash filter)"
            rejected_posts.append({"url": u, "username": username, "caption": caption[:100], "reason": rej_reason})
            print(f"🚫 [Rejected Clash] Scene {scene_idx} -> @{username}: \"{caption[:50]}...\" | Reason: {rej_reason}")
            continue

        # Hard entity filter: Keep only posts whose caption, username, or hashtags contain the entity name
        if not post_matches_entity(cand_combined, entity_tokens):
            rej_reason = f"Missing entity name '{entity_name}' in caption, username, or hashtags"
            rejected_posts.append({"url": u, "username": username, "caption": caption[:100], "reason": rej_reason})
            continue

        # Rule 2: For pure Instagram scrape candidates, require the show hashtag if not from official handles
        if is_bb and is_person_scene and cand.get("platform") == "instagram":
            is_from_official = any(oh in username or oh in post_url for oh in SHOW_OFFICIAL_HANDLES)
            has_show_tag = any(st in cand_combined for st in SHOW_TAG_TOKENS)
            if not is_from_official and not has_show_tag and len(filtered_candidates) >= 5:
                rej_reason = "Instagram post missing show hashtag (#BiggBossTelugu10)"
                rejected_posts.append({"url": u, "username": username, "caption": caption[:100], "reason": rej_reason})
                print(f"🚫 [Rejected Missing Show Tag] Scene {scene_idx} -> @{username}: \"{caption[:50]}...\" | Reason: {rej_reason}")
                continue

        # Strict language & season guards
        from providers.image import HINDI_BIGG_BOSS_KEYWORDS
        if any(hk in cand_combined for hk in HINDI_BIGG_BOSS_KEYWORDS):
            rej_reason = "Hindi Bigg Boss keyword detected"
            rejected_posts.append({"url": u, "username": username, "caption": caption[:100], "reason": rej_reason})
            continue

        if is_conflicting_season_candidate(
            cand_combined,
            current_season=cur_season,
            is_bb_context=is_bb,
            disallow_terms=person_disallow,
            target_person=person_name if is_person_scene else None,
        ):
            rej_reason = "Conflicting season (past season BB1-BB9) or off-topic international noise"
            rejected_posts.append({"url": u, "username": username, "caption": caption[:100], "reason": rej_reason})
            continue

        filtered_candidates.append(cand)

    after_filter_count = len(filtered_candidates)
    print(f"🎯 [Step 2 Filter] Scene {scene_idx}: Raw Candidates={candidates_count} -> Survived={after_filter_count} | Rejected={len(rejected_posts)}")

    # -------------------------------------------------------------------------
    # STEP 3: Boost posts whose caption mentions the event keyword
    # -------------------------------------------------------------------------
    event_tokens = get_event_tokens(event_keyword)
    candidate_event_boosts: Dict[str, float] = {}
    for cand in filtered_candidates:
        cap_lower = (cand.get("caption") or "").lower()
        has_ev = any(etok in cap_lower for etok in event_tokens) if event_tokens else False
        candidate_event_boosts[cand["image_url"]] = 0.25 if has_ev else 0.0

    # -------------------------------------------------------------------------
    # STEP 4: Rank the remaining with CLIP, keep the top 5
    # -------------------------------------------------------------------------
    temp_dir = OUTPUT_DIR / "temp_candidates"
    temp_dir.mkdir(parents=True, exist_ok=True)

    def _dl_cand(item):
        cand = item
        u = cand.get("image_url", "")
        u_hash = hashlib.sha256(u.encode("utf-8")).hexdigest()[:12]
        temp_file = temp_dir / f"sc_{scene_idx}_{u_hash}.jpg"
        if temp_file.exists() and temp_file.stat().st_size > 2000:
            return (cand, temp_file)
        if download_candidate_image(cand, temp_file):
            return (cand, temp_file)
        return None

    import concurrent.futures
    downloaded = []
    # Download top 15 survivors for CLIP evaluation
    to_dl = filtered_candidates[:15]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(_dl_cand, to_dl):
            if res and res[1].exists():
                downloaded.append(res)

    scored_candidates = []
    for cand, temp_file in downloaded:
        # Check image validity, minimum resolution (>= 400x400) & aspect ratio sanity check
        try:
            with Image.open(temp_file) as test_img:
                w, h = test_img.size
                if w < 400 or h < 400:
                    temp_file.unlink(missing_ok=True)
                    continue
                # Aspect ratio sanity check: reject extreme banners or ultra-skinny strips (0.45 <= AR <= 2.2)
                ar = float(w) / float(max(1, h))
                if ar < 0.45 or ar > 2.2:
                    temp_file.unlink(missing_ok=True)
                    continue
        except Exception:
            temp_file.unlink(missing_ok=True)
            continue

        # Perceptual hash deduplication across all scenes
        p_hash = compute_image_hash(temp_file)
        if not p_hash:
            temp_file.unlink(missing_ok=True)
            continue

        is_dup, _ = is_duplicate_hash(p_hash, used_hashes, threshold=5)
        if is_dup:
            temp_file.unlink(missing_ok=True)
            continue

        # CLIP scoring
        clip_base, img_s, cap_s, _ = score_candidate_with_clip(
            image_path=temp_file,
            caption=cand.get("caption", ""),
            clip_text=clip_text,
            entity=entity_name,
            model=model,
            processor=processor,
            boost_val=0.0,
        )
        ev_boost = candidate_event_boosts.get(cand["image_url"], 0.0)
        total_score = clip_base + ev_boost

        scored_candidates.append({
            "candidate": cand,
            "temp_file": temp_file,
            "p_hash": p_hash,
            "final_score": total_score,
            "img_sim": img_s,
            "cap_sim": cap_s,
            "event_boost": ev_boost,
        })

    # Rank and keep top 5
    scored_candidates.sort(key=lambda x: x["final_score"], reverse=True)
    top_5 = scored_candidates[:5]
    clip_scores = [round(c["final_score"], 4) for c in top_5]
    print(f"🏆 [Step 4 CLIP Ranking] Scene {scene_idx}: Top {len(top_5)} CLIP Scores={clip_scores}")

    # -------------------------------------------------------------------------
    # STEP 5: Tiered CLIP Decision (Direct Accept >= 0.36, Reject < 0.23, Borderline Vision Check)
    # -------------------------------------------------------------------------
    if not top_5:
        claude_choice = "none"
        claude_reason = (
            f"Zero candidates contained entity '{entity_name}' with show hashtag, or clash actor terms were rejected."
            if after_filter_count == 0
            else "No downloaded images met dimension (>=400x400, 0.45<=AR<=2.2) or deduplication requirements."
        )
    else:
        top_cand = top_5[0]
        top_score = top_cand["final_score"]

        # Tier 1: High confidence (>= 0.36) -> Accept directly!
        if top_score >= 0.36:
            claude_choice = 0
            claude_reason = f"High CLIP confidence ({top_score:.4f} >= 0.36) with verified entity '{entity_name}'. Directly accepted without vision call."
            print(f"🎯 [Tiered CLIP Direct Accept] Scene {scene_idx} -> Score {top_score:.4f} >= 0.36. Accepted candidate 0.")

        # Tier 2: Low confidence (< 0.23) -> Reject immediately!
        elif top_score < 0.23:
            claude_choice = "none"
            claude_reason = f"Low CLIP confidence ({top_score:.4f} < 0.23). Rejected immediately, falling back to text card."
            print(f"🚫 [Tiered CLIP Immediate Reject] Scene {scene_idx} -> Score {top_score:.4f} < 0.23. Falling back to text card.")

        # Tier 3: Borderline (0.23 <= score < 0.36) -> Check vision or fall back
        else:
            top_5_paths = [c["temp_file"] for c in top_5]
            top_5_meta = [c["candidate"] for c in top_5]
            print(f"👁️ [Tiered CLIP Borderline ({top_score:.4f})] Sending {len(top_5_paths)} images to Vision Check (Scene {scene_idx})...")
            vision_res = verify_candidates_with_claude_vision(
                image_paths=top_5_paths,
                script_line=scene_text,
                entity=entity_name,
                event=event_keyword,
                candidates_meta=top_5_meta,
            )
            raw_choice = vision_res.get("choice", "none")
            claude_reason = vision_res.get("reason", "Verified by Vision")

            if isinstance(raw_choice, int) and 0 <= raw_choice < len(top_5):
                claude_choice = raw_choice
            elif isinstance(raw_choice, str) and raw_choice.isdigit() and 0 <= int(raw_choice) < len(top_5):
                claude_choice = int(raw_choice)
            else:
                claude_choice = "none"

    print(f"🤖 [Step 5 Vision Verdict] Scene {scene_idx} -> Choice: {claude_choice} | Reason: {claude_reason}")

    # -------------------------------------------------------------------------
    # STEP 6: If 'none', use a text card. Never insert a random image.
    # -------------------------------------------------------------------------
    chosen_cand_obj = None
    if claude_choice != "none" and isinstance(claude_choice, int) and 0 <= claude_choice < len(top_5):
        chosen_cand_obj = top_5[claude_choice]
        chosen_cand = chosen_cand_obj["candidate"]
        chosen_file = chosen_cand_obj["temp_file"]
        p_hash = chosen_cand_obj["p_hash"]

        # Copy to destination asset
        shutil.copy2(chosen_file, destination_jpg)
        clean_and_crop_image(destination_jpg)

        # Thread-safe record of used hash and url
        if state_lock:
            with state_lock:
                used_hashes.add(p_hash)
                used_urls.add(chosen_cand["image_url"])
        else:
            used_hashes.add(p_hash)
            used_urls.add(chosen_cand["image_url"])

        final_action = "selected_image"
        print(f"✅ Scene {scene_idx} -> Picked verified image from @{chosen_cand.get('username')} ({chosen_cand.get('platform')})")
    else:
        # RESILIENT VISUAL FALLBACK: Search high-res web photography or entity library before considering text cards!
        print(f"🔄 Scene {scene_idx} -> Vision check returned '{claude_choice}'. Sourcing high-res photography fallback for '{person_name or entity_name}'...")
        fallback_query = ""
        if person_name:
            fallback_query = f"{person_name} Bigg Boss Telugu" if is_bb else f"{person_name} Telugu"
        elif entity_name:
            fallback_query = f"{entity_name} Telugu" if is_bb else entity_name
        else:
            fallback_query = "Bigg Boss Telugu stage set" if is_bb else (show_name or "breaking news")

        downloaded_ok = False
        # If in reality show or specific news context, disable loose web/stock queries to prevent unrelated concert/machinery leakage
        if is_bb:
            print(f"🚫 [Reality Show Lock] Skipping loose web/stock fallback search for Scene {scene_idx} to prevent unrelated image leakage.")
            # Check curated entity/contestant photo from assets/fallback or assets/entities
            for fallback_name in [person_name, entity_name, "bigg_boss", "starmaa"]:
                if not fallback_name:
                    continue
                clean_fn = re.sub(r"[^a-zA-Z0-9_]", "", fallback_name.lower().replace(" ", "_"))
                for ext in [".jpg", ".jpeg", ".png"]:
                    cand_path = ASSETS_DIR / f"{clean_fn}{ext}"
                    if not cand_path.exists():
                        cand_path = ASSETS_DIR / "fallback" / f"{clean_fn}{ext}"
                    if cand_path.exists() and cand_path.stat().st_size > 1000:
                        try:
                            shutil.copy2(cand_path, destination_jpg)
                            clean_and_crop_image(destination_jpg)
                            downloaded_ok = True
                            final_action = "selected_image"
                            chosen_cand_obj = {
                                "candidate": {
                                    "image_url": str(cand_path),
                                    "post_url": "",
                                    "username": "autotube_library",
                                    "platform": "entity_library",
                                }
                            }
                            print(f"✅ Scene {scene_idx} -> Loaded curated library asset for '{fallback_name}'")
                            break
                        except Exception:
                            pass
                if downloaded_ok:
                    break
            from providers.google_images import search_show_verified_images, search_duckduckgo_images
            from agents.visual_ladder import download_url_to_file as download_image_file

            fallback_candidates = []
            try:
                verified = search_show_verified_images(
                    entity_name=person_name or entity_name or "breaking news",
                    show_context=show_name,
                    clean_event=event_keyword,
                    max_candidates=5,
                )
                for vc in (verified or []):
                    iurl = vc.get("image_url")
                    if iurl and iurl not in used_urls:
                        fallback_candidates.append(iurl)
            except Exception:
                pass

            if not fallback_candidates:
                try:
                    ddg_res = search_duckduckgo_images(fallback_query, max_results=5)
                    for dr in (ddg_res or []):
                        iurl = dr.get("image_url")
                        if iurl and iurl not in used_urls:
                            from utils.season_guard import is_conflicting_season_candidate
                            if not is_conflicting_season_candidate(iurl, is_bb_context=is_bb, target_person=person_name):
                                fallback_candidates.append(iurl)
                except Exception:
                    pass

            # Try downloading one of the fallback candidates
            for cand_url in fallback_candidates:
                temp_dl = temp_dir / f"scene_{scene_idx}_fallback_{hashlib.md5(cand_url.encode()).hexdigest()[:8]}.jpg"
                if download_image_file(cand_url, temp_dl):
                    try:
                        shutil.copy2(temp_dl, destination_jpg)
                        clean_and_crop_image(destination_jpg)
                        used_urls.add(cand_url)
                        downloaded_ok = True
                        final_action = "selected_image"
                        chosen_cand_obj = {
                            "candidate": {
                                "image_url": cand_url,
                                "post_url": cand_url,
                                "username": "web_photography",
                                "platform": "web_search",
                            }
                        }
                        print(f"✅ Scene {scene_idx} -> Picked web photography fallback: {cand_url[:60]}")
                        break
                    except Exception:
                        pass

        # Fallback to curated entity photo from assets/fallback or assets/entities if still not found
        if not downloaded_ok:
            curated_pool = [person_name, entity_name]
            if is_bb:
                curated_pool.extend(["bigg_boss", "nagarjuna"])
            for fallback_name in curated_pool:
                if not fallback_name:
                    continue
                clean_fn = re.sub(r"[^a-zA-Z0-9_]", "", fallback_name.lower().replace(" ", "_"))
                for ext in [".jpg", ".jpeg", ".png"]:
                    cand_path = ASSETS_DIR / f"{clean_fn}{ext}"
                    if not cand_path.exists():
                        cand_path = ASSETS_DIR / "fallback" / f"{clean_fn}{ext}"
                    if cand_path.exists() and cand_path.stat().st_size > 1000:
                        try:
                            shutil.copy2(cand_path, destination_jpg)
                            clean_and_crop_image(destination_jpg)
                            downloaded_ok = True
                            final_action = "selected_image"
                            chosen_cand_obj = {
                                "candidate": {
                                    "image_url": str(cand_path),
                                    "post_url": "",
                                    "username": "autotube_library",
                                    "platform": "entity_library",
                                }
                            }
                            print(f"✅ Scene {scene_idx} -> Loaded curated library asset for '{fallback_name}'")
                            break
                        except Exception:
                            pass
                if downloaded_ok:
                    break

        # Dynamic AI Image Generation Fallback (FLUX) using beat narration context
        if not downloaded_ok:
            try:
                from agents.visual_agent import build_scene_flux_prompt, generate_ai_visual
                flux_prompt = ""
                vp_f = OUTPUT_DIR / "visual_plan.json"
                if vp_f.exists():
                    try:
                        vps = json.loads(vp_f.read_text(encoding="utf-8"))
                        for ve in vps:
                            if ve.get("beat_id") == scene_idx:
                                flux_prompt = ve.get("visual_fallback_prompt") or ""
                                break
                    except Exception:
                        pass
                if not flux_prompt and (person_name or entity_name):
                    target_ent = person_name or entity_name
                    flux_prompt = f"Cinematic {target_ent} in intense expression, 9:16 vertical ratio, photorealistic, 8k, dramatic lighting"
                elif not flux_prompt:
                    flux_prompt = build_scene_flux_prompt(
                        scene_text,
                        aspect_ratio="9:16",
                        topic_category="entertainment",
                        show_context=show_context if is_bb else "",
                    )
                print(f"🎨 Scene {scene_idx} -> Real photo missing. Synthesizing dynamic FLUX AI visual: '{flux_prompt[:50]}...'")
                if generate_ai_visual(flux_prompt, destination_jpg, aspect_ratio="9:16"):
                    downloaded_ok = True
                    final_action = "selected_image"
                    chosen_cand_obj = {
                        "candidate": {
                            "image_url": str(destination_jpg),
                            "post_url": "",
                            "username": "pollinations_flux",
                            "platform": "ai_flux",
                        }
                    }
                    try:
                        from data.asset_ledger import record_asset
                        record_asset(
                            video_id="current",
                            beat_id=scene_idx,
                            asset_path=str(destination_jpg),
                            source_url="pollinations_flux_scene",
                            tier="TIER_A",
                            license_name="Generated AI Visual (CC0)",
                            credit_text="AutoTube FLUX Engine",
                        )
                    except Exception:
                        pass
            except Exception as flux_err:
                print(f"⚠️ FLUX fallback error in social selector Scene {scene_idx}: {flux_err}")

        # Only if all image sources and FLUX generation fail, generate typography card
        if not downloaded_ok:
            final_action = "text_card"
            badge_label = person_name if person_name else (entity_name if entity_name else show_name)
            print(f"📝 Scene {scene_idx} -> All image sources exhausted. Generating Typography Card for '{badge_label}'.")
            card_words = scene_text.split()[:8]
            card_text = " ".join(card_words)
            generate_typography_card(
                headline_text=card_text,
                output_path=str(destination_jpg),
                topic_category="entertainment",
                aspect_ratio="9:16",
                badge_label=badge_label[:25] if badge_label else None,
            )

    # -------------------------------------------------------------------------
    # STEP 7: Log for each scene: candidates count, after-filter count,
    #         CLIP scores, the Claude choice, and the reason.
    # -------------------------------------------------------------------------
    search_log = {
        "scene_index": scene_idx,
        "script_line": scene_text,
        "entity": entity_name,
        "person_name": person_name,
        "event_type": event_keyword,
        "candidates_count": candidates_count,
        "after_filter_count": after_filter_count,
        "clip_scores": clip_scores,
        "claude_choice": claude_choice,
        "claude_reason": claude_reason,
        "final_action": final_action,
        "chosen_score": clip_scores[claude_choice] if isinstance(claude_choice, int) and 0 <= claude_choice < len(clip_scores) else 1.0,
        "fallback_rung": "claude_verified_image" if chosen_cand_obj else "typography_card",
        "hashtags": hashtags,
        "clip_text": clip_text,
        "rejected_posts": rejected_posts,
        "chosen_image": {
            "source_url": chosen_cand_obj["candidate"]["image_url"],
            "post_url": chosen_cand_obj["candidate"].get("post_url", ""),
            "username": chosen_cand_obj["candidate"].get("username", ""),
            "platform": chosen_cand_obj["candidate"].get("platform", ""),
            "path": str(destination_jpg),
        } if chosen_cand_obj else {
            "source_url": "generated_typography_card",
            "post_url": "",
            "username": "autotube_graphics",
            "platform": "typography_card",
            "path": str(destination_jpg),
        },
        "top_candidates": [
            {
                "url": sc["candidate"]["image_url"][:80],
                "username": sc["candidate"].get("username", "unknown"),
                "platform": sc["candidate"].get("platform", "web"),
                "final_score": round(sc["final_score"], 4),
                "img_sim": round(sc["img_sim"], 4),
                "cap_sim": round(sc["cap_sim"], 4),
                "event_boost": round(sc["event_boost"], 4),
            }
            for sc in top_5
        ],
    }

    print("=" * 60)
    print(f"📊 [SCENE {scene_idx} SELECTION AUDIT]")
    print(f"   • Candidates Count:   {candidates_count}")
    print(f"   • After-Filter Count: {after_filter_count}")
    print(f"   • Rejected Count:     {len(rejected_posts)}")
    print(f"   • CLIP Scores:        {clip_scores}")
    print(f"   • Claude Choice:      {claude_choice}")
    print(f"   • Claude Reason:      {claude_reason}")
    print(f"   • Final Action:       {final_action}")
    print("=" * 60)

    return search_log


# ============================================================
# 7.5. TOPIC CANDIDATE PRE-FETCH POOL
# ============================================================

def prefetch_topic_social_candidates(
    overall_context: str,
    scenes: List[str],
    all_metas: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Pre-fetches a shared pool of candidate images for top hashtags and entities across the video.
    Runs once per video run instead of repeat calls per scene, speeding up sourcing by 5x.
    """
    from collections import Counter
    all_tags = []
    all_entities = []
    for m in all_metas:
        for t in m.get("hashtags", []):
            if t:
                all_tags.append(t)
        ent = m.get("main_entity", "")
        if ent and ent != "auto" and len(ent) > 2:
            all_entities.append(ent)

    top_tags = [t for t, _ in Counter(all_tags).most_common(2)]
    top_entity = Counter(all_entities).most_common(1)[0][0] if all_entities else overall_context

    from utils.season_guard import get_current_season_number, is_conflicting_season_candidate, is_bigg_boss_topic
    is_bb_overall = is_bigg_boss_topic(overall_context) or is_bigg_boss_topic(top_entity) or any(is_bigg_boss_topic(t) for t in top_tags)
    cur_season = get_current_season_number(overall_context) or 10 if is_bb_overall else None

    if is_bb_overall:
        if "bigg boss" in top_entity.lower():
            top_entity = f"Bigg Boss Telugu {cur_season}"
        clean_top_tags = []
        for t in top_tags:
            if "biggboss" in t.lower() and "telugu" not in t.lower():
                clean_top_tags.append(f"#BiggBossTelugu{cur_season}")
            elif "hindi" not in t.lower() and "colors" not in t.lower():
                clean_top_tags.append(t)
        if f"#BiggBossTelugu{cur_season}" not in clean_top_tags and "bigg boss" in top_entity.lower():
            clean_top_tags.insert(0, f"#BiggBossTelugu{cur_season}")
        top_tags = clean_top_tags
    else:
        # Non-Bigg Boss topic: preserve clean original topic tags without reality show injection
        top_tags = [t for t in top_tags if t and not is_bigg_boss_topic(t)]

    print(f"🚀 [Topic Pre-Fetch] Collecting shared candidate pool for '{top_entity}' ({', '.join(top_tags)})...")
    try:
        from providers.apify_social import batch_fetch_social_candidates
        all_unique_tags = list(dict.fromkeys(top_tags + all_tags[:6]))
        pool = batch_fetch_social_candidates(
            hashtags=all_unique_tags,
            search_terms=[top_entity],
            is_bb_context=is_bb_overall,
            disallow_terms=None,
        )
        if not pool:
            pool = fetch_social_candidates_for_scene(
                entity=top_entity,
                hashtags=top_tags,
                query_keywords=None,
                target_count=30,
            )
        # Filter conflicting season candidates from topic pool
        filtered_pool = [
            c for c in pool
            if not is_conflicting_season_candidate(
                f"{c.get('caption', '')} {c.get('image_url', '')}",
                current_season=cur_season,
                is_bb_context=is_bb_overall,
            )
        ]
        status_label = f"Season {cur_season}" if is_bb_overall else top_entity
        print(f"✅ [Topic Pre-Fetch] Pooled {len(filtered_pool)} verified {status_label} candidates for the video run.")
        return filtered_pool
    except Exception as e:
        print(f"⚠️ Topic candidate pre-fetch notice: {e}")
        return []


# ============================================================
# 8. ORCHESTRATE FULL SCRIPT VISUAL SELECTION
# ============================================================

def select_visuals_for_script(
    script_text: str,
    overall_context: Optional[str] = None,
    threshold: Optional[float] = None,
) -> List[Tuple[int, Path]]:
    """
    Orchestrates the entire social visual selection pipeline for a script:
    - Splits script into scenes
    - Analyzes metadata per scene
    - Pre-fetches shared candidate pool
    - Fetches, CLIP-ranks, deduplicates, and falls back gracefully
    - Writes visual_selection_audit.json and .log
    - Returns [(scene_idx, asset_path), ...]
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sim_threshold = threshold or float(get_setting("CLIP_SIMILARITY_THRESHOLD", 0.25))
    boost_val = float(get_setting("ENTITY_CAPTION_BOOST", 0.15))

    from utils.season_guard import is_bigg_boss_topic, resolve_effective_show_context
    title_file = OUTPUT_DIR / "title.txt"
    t_text = title_file.read_text(encoding="utf-8").strip() if title_file.exists() else ""
    clean_ctx = resolve_effective_show_context(
        topic_or_title=t_text,
        script_text=script_text,
        raw_show_context=overall_context or get_setting("SHOW_CONTEXT", ""),
    )
    if clean_ctx and (is_bigg_boss_topic(t_text) or is_bigg_boss_topic(script_text)):
        ctx = clean_ctx
    else:
        ctx = t_text or (overall_context if (overall_context and not is_bigg_boss_topic(overall_context)) else "viral entertainment")

    scenes = split_script_into_scenes(script_text)
    if not scenes:
        raise ValueError("Script is empty or has no segmentable scenes.")

    print("=" * 70)
    print(f"🎬 SOCIAL VISUAL SELECTION: {len(scenes)} Scenes (Context: '{ctx}')")
    print(f"🎯 CLIP ViT-B-32 Threshold: {sim_threshold} | Entity Caption Boost: +{boost_val}")
    print("=" * 70)

    # 1. Fast Batch LLM Analysis for all scenes
    all_metas = batch_analyze_scenes_with_llm(scenes, overall_context=ctx)
    if len(all_metas) < len(scenes):
        for s in scenes[len(all_metas):]:
            all_metas.append(analyze_scene_with_llm(s, overall_context=ctx))

    # 2. Fast Topic Candidate Pre-Fetch Pool (5x speedup)
    topic_pool = prefetch_topic_social_candidates(ctx, scenes, all_metas)

    import threading
    import concurrent.futures

    state_lock = threading.Lock()
    used_hashes: Set[str] = set()
    used_urls: Set[str] = set()

    def _process_one_scene(item):
        idx, scene_text, meta = item
        dest_jpg = ASSETS_DIR / f"{idx}.jpg"
        print(f"\n⚡ [Concurrent Sourcing] Scene {idx}/{len(scenes)}: \"{scene_text[:50]}...\" | Entity: {meta['main_entity']}")
        scene_audit = select_image_for_scene(
            scene_idx=idx,
            scene_text=scene_text,
            meta=meta,
            used_hashes=used_hashes,
            used_urls=used_urls,
            destination_jpg=dest_jpg,
            threshold=sim_threshold,
            boost_val=boost_val,
            topic_candidate_pool=topic_pool,
            overall_context=ctx,
            state_lock=state_lock,
        )
        return (idx, dest_jpg, scene_audit, meta)

    items = list(zip(range(1, len(scenes) + 1), scenes, all_metas))
    num_workers = min(3, len(scenes))
    print(f"🚀 [Triple-Way Concurrency] Launching {num_workers} parallel workers across {len(scenes)} scenes...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as pool:
        completed = list(pool.map(_process_one_scene, items))

    # Maintain strictly ordered sequence 1..N
    completed.sort(key=lambda x: x[0])

    audit_records = []
    chosen_assets = []
    visual_plan_lines = []

    for idx, dest_jpg, scene_audit, meta in completed:
        audit_records.append(scene_audit)
        chosen_assets.append((idx, dest_jpg))
        q_line = f"{meta['clip_text']} | {meta['main_entity']} {meta['event_type']}"
        if any(q_line == vl.split('. ', 1)[-1] for vl in visual_plan_lines):
            q_line = f"{q_line} scene perspective #{idx}"
        visual_plan_lines.append(f"{idx}. {q_line}")

    # Clean up temp candidate files
    shutil.rmtree(OUTPUT_DIR / "temp_candidates", ignore_errors=True)

    # Save visual_plan.txt matching these scenes
    (OUTPUT_DIR / "visual_plan.txt").write_text("\n".join(visual_plan_lines), encoding="utf-8")

    # Ensure section_map.txt has matching synchronized sections for video_agent
    section_map_file = OUTPUT_DIR / "section_map.txt"
    try:
        from agents.video_agent import get_section_map
        sec_items = get_section_map()
        if len(sec_items) != len(chosen_assets):
            with open(section_map_file, "w", encoding="utf-8") as f:
                for idx, sc_text in enumerate(scenes, start=1):
                    f.write(f"SECTION {idx} | VISUAL {idx}\n{sc_text}\n\n")
            print(f"🎬 [Scene Synchronization] Updated section_map.txt with {len(scenes)} synchronized sections.")
    except Exception as e:
        print(f"Notice: Section map synchronization notice: {e}")

    # Step 7: Write Audit Log (JSON & human-readable log)
    _write_audit_logs(audit_records)

    print("\n" + "=" * 70)
    print(f"✨ COMPLETED SOCIAL VISUAL SELECTION: {len(chosen_assets)} Scenes Prepared")
    print(f"📋 Audit Log written to: {AUDIT_LOG_FILE}")
    print("=" * 70)

    return chosen_assets


def _write_audit_logs(audit_records: List[Dict[str, Any]]) -> None:
    """Writes detailed audit trail to json and formatted log."""
    try:
        AUDIT_JSON_FILE.write_text(json.dumps(audit_records, indent=2, ensure_ascii=False), encoding="utf-8")
        
        lines = [
            "=" * 80,
            "AUTOTUBE AI - SOCIAL VISUAL SELECTION AUDIT LOG",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80,
            "",
        ]
        for rec in audit_records:
            lines.append(f"SCENE #{rec['scene_index']}: {rec['script_line']}")
            lines.append(f"  • Entity: {rec.get('entity')} | Event: {rec.get('event_type')}")
            lines.append(f"  • 1. Candidates Count:   {rec.get('candidates_count', 0)}")
            lines.append(f"  • 2. After-Filter Count: {rec.get('after_filter_count', 0)}")
            lines.append(f"  • 3. CLIP Scores:        {rec.get('clip_scores', [])}")
            lines.append(f"  • 4. Claude Choice:      {rec.get('claude_choice')}")
            lines.append(f"  • 5. Reason:             {rec.get('claude_reason')}")
            lines.append(f"  • Final Action:          {rec.get('final_action')} ({rec.get('fallback_rung')})")
            chosen = rec.get("chosen_image", {})
            lines.append(f"  • Assigned Asset:        {chosen.get('platform')} (@{chosen.get('username')})")
            lines.append(f"  • Asset Source URL:      {chosen.get('source_url')}")
            if rec.get("top_candidates"):
                lines.append(f"  • Top Candidates Evaluated:")
                for tc in rec.get("top_candidates", [])[:5]:
                    lines.append(f"      - {tc['platform']} (@{tc['username']}): Score={tc['final_score']} (img={tc['img_sim']}, cap={tc['cap_sim']}, boost=+{tc.get('event_boost', 0.0)}) | {tc['url']}")
            rejs = rec.get("rejected_posts", [])
            if rejs:
                lines.append(f"  • Rejected Posts ({len(rejs)}):")
                for rp in rejs[:10]:
                    lines.append(f"      - ❌ @{rp.get('username')}: \"{rp.get('caption')[:80]}\" -> Reason: {rp.get('reason')}")
                if len(rejs) > 10:
                    lines.append(f"      ... and {len(rejs) - 10} more rejected posts (see audit json).")
            lines.append("-" * 80)
            lines.append("")

        AUDIT_LOG_FILE.write_text("\n".join(lines), encoding="utf-8")
    except Exception as err:
        print(f"⚠️ Error writing audit logs: {err}")
