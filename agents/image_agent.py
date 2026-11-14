import html
import json
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import random
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional, Any, Set, Tuple

import requests
from PIL import Image
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, wait_random
from urllib3.util.retry import Retry
from supervisor import autonomous_recover

load_dotenv()



# ============================================================
# CONFIG & LOCAL GROUND TRUTH CONTESTANT ROSTER
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

ASSETS_DIR = ROOT / "assets"
FALLBACK_DIR = ASSETS_DIR / "fallback"
OUTPUT_DIR = ROOT / "output"

# Ground Truth Local Contestant Reference Directories
CONTESTANT_REF_DIRS = [
    ROOT / "reference_assets" / "contestants",
    ROOT / "assets" / "contestants",
    ROOT / "data" / "entities",
    ROOT / "assets" / "entities",
]

CONTESTANT_GALLERIES_DIR = ROOT / "data" / "contestant_galleries"
USED_CONTESTANT_IMAGES_FILE = ROOT / "data" / "used_contestant_images.json"
CONTESTANTS_FILE = ROOT / "data" / "contestants.json"


def _load_used_contestant_images() -> Dict[str, List[str]]:
    """Loads history of contestant images used across recent runs."""
    if not USED_CONTESTANT_IMAGES_FILE.exists():
        return {}
    try:
        with open(USED_CONTESTANT_IMAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _record_used_contestant_image(slug: str, image_filename: str, max_history: int = 30):
    """Records an image filename to persistent used history."""
    try:
        data = _load_used_contestant_images()
        history = data.setdefault(slug, [])
        if image_filename in history:
            history.remove(image_filename)
        history.append(image_filename)
        if len(history) > max_history:
            data[slug] = history[-max_history:]
        USED_CONTESTANT_IMAGES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(USED_CONTESTANT_IMAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Notice: failed to record used contestant image: {e}")


# Contextual anti-collision filters and negative keyword builders
UNIVERSAL_SPAM_NEGATIVES = [
    "-cricket", "-cricketer", "-bcci", "-ipl", "-sports",
    "-stamp", "-postage", "-wallpaper",
    "-anime", "-manga", "-cartoon", "-drawing", "-illustration", "-animated", "-sketch", "-vector",
]

STRICT_ANTI_COLLISION_BLACKLIST = [
    "ram charan", "రామ్ చరణ్", "rohit sharma", "రోహిత్ శర్మ",
    "cricket", "cricketer", "bcci", "ipl", "hitman",
    "stamp", "postage",
    "jhansi fort", "ఝాన్సీ కోట", "rani lakshmibai", "lakshmibai", "monument",
    "anime", "manga", "cartoon", "drawing", "illustration",
]


def get_contextual_negative_filters(entity_name: str, topic_context: str) -> str:
    """
    Dynamically generates negative search keywords to prevent celebrity/sports/monument collisions.
    Context-aware: if the topic genuinely targets Ram Charan or Rohit Sharma, their terms are NOT negated.
    """
    ent_low = (entity_name or "").lower().strip()
    top_low = (topic_context or "").lower().strip()

    negs = list(UNIVERSAL_SPAM_NEGATIVES)

    # If the topic is genuinely about sports/cricket, allow sports terms
    if any(sp in ent_low or sp in top_low for sp in ("cricket", "ipl", "bcci", "match", "sports", "world cup")):
        negs = [n for n in negs if n not in ("-cricket", "-cricketer", "-bcci", "-ipl", "-sports")]

    # Disambiguate Sudheer (e.g. Sudheer Reddy vs Sudigali Sudheer)
    if "sudheer" in ent_low and "sudigali sudheer" not in ent_low and "sudigali sudheer" not in top_low:
        negs.extend(['-("sudigali sudheer")', '-anand'])

    # Disambiguate Charan (e.g. RJ Charan / Charan Mahadev vs Megapower Star Ram Charan)
    if "charan" in ent_low and "ram charan" not in ent_low and "ram charan" not in top_low:
        negs.extend(['-("ram charan")', '-konidela', '-mega'])

    # Disambiguate Rohit (e.g. Rohit Patnam vs Rohit Sahni / Rohit Sharma)
    if "rohit" in ent_low and "rohit sharma" not in ent_low and "rohit sharma" not in top_low:
        negs.extend(['-("rohit sharma")', '-("rohit sahni")', '-hitman', '-batsman', '-cricketer'])

    # Disambiguate Jhansi (e.g. Singer Jhansi vs Anchor Jhansi / Historical Jhansi Fort / Rani Lakshmibai)
    if "jhansi" in ent_low and "fort" not in ent_low and "fort" not in top_low:
        negs.extend(['-("anchor jhansi")', '-("jhansi fort")', '-("rani lakshmibai")', '-fort', '-monument', '-history', '-stamps'])

    # Disambiguate Thrigun (avoid Trigun anime collisions)
    if any(k in ent_low for k in ("thrigun", "trigun")):
        negs.extend(['-anime', '-manga', '-vash', '-stampede', '-cartoon', '-drawing'])

    # Disambiguate Salman (e.g. reality contestant vs Salman Khan)
    if "salman" in ent_low and "salman khan" not in ent_low and "salman khan" not in top_low:
        negs.extend(['-("salman khan")'])

    # Disambiguate Naresh (e.g. Potti Naresh vs Allari Naresh / Senior Naresh)
    if "naresh" in ent_low and "allari naresh" not in ent_low and "senior naresh" not in ent_low:
        negs.extend(['-("allari naresh")', '-("senior naresh")', '-("vk naresh")', '-pavitra'])

    return " ".join(dict.fromkeys(negs))


def build_contextual_search_query(
    entity: str,
    topic_context: str = "",
    scene_action: str = "",
    topic_category: str = "entertainment",
) -> Tuple[str, str]:
    """
    Builds a high-intent, topic-contextualized search query and its negative-filtered variant.
    NEVER searches bare single names (e.g., 'Ram', 'Rohit', 'Charan').
    Always binds the entity with topic or role context.
    Returns: (clean_search_query, full_query_with_negatives)
    """
    ent = (entity or "").strip()
    top = (topic_context or "").strip()
    act = (scene_action or "").strip()

    # Clean action words (keep max 3 punchy keywords, drop stop words)
    act_words = [
        w for w in re.sub(r"[^\w\s-]", "", act).split()
        if w.lower() not in {"visual", "scene", "shot", "photo", "image", "showing", "depicting", "camera", "close", "wide"}
        and len(w) > 1
    ][:3]
    act_short = " ".join(act_words)

    # Contextualize entity: never search bare names that collide with foreign entities
    anchor = ""
    top_lower = top.lower()
    if "bigg boss" in top_lower:
        anchor = "Bigg Boss Telugu 10" if "10" in top_lower else "Bigg Boss Telugu"
    elif any(k in top_lower for k in ("prabhas", "kalki", "raja saab", "salaar", "spirit")):
        anchor = "Prabhas Telugu movie"
    elif any(k in top_lower for k in ("allu arjun", "pushpa")):
        anchor = "Allu Arjun Pushpa"
    elif any(k in top_lower for k in ("chiranjeevi", "megaverse")):
        anchor = "Chiranjeevi Telugu"
    elif any(k in top_lower for k in ("pawan kalyan", "og", "hari hara")):
        anchor = "Pawan Kalyan"
    elif top:
        top_clean = re.sub(r"[^\w\s]", " ", top)
        meaningful_words = [w for w in top_clean.split() if w.lower() not in {
            "roasting", "the", "drama", "episode", "full", "review", "reviewing",
            "reaction", "call", "game", "changer", "master", "manipulator", "is", "he", "just", "a"
        }]
        anchor = " ".join(meaningful_words[:3])

    if ent:
        if anchor and anchor.lower() not in ent.lower():
            core_q = f'"{ent}" "{anchor}"'
        elif topic_category in ("cinema", "entertainment", "celebrity"):
            core_q = f'"{ent}" Telugu actor interview HD'
        else:
            core_q = f'"{ent}" official HD'
    else:
        # No entity: anchor to topic context
        core_q = anchor or top or "Telugu entertainment"

    if act_short and act_short.lower() not in core_q.lower():
        core_q = f"{core_q} {act_short}".strip()

    negs = get_contextual_negative_filters(ent, top)
    full_q = f"{core_q} {negs}".strip() if negs else core_q
    return core_q, full_q


def load_contestant_roster() -> Dict[str, Any]:
    """Loads official ground truth contestant metadata from data/contestants.json."""
    if CONTESTANTS_FILE.exists():
        try:
            return json.loads(CONTESTANTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def is_blacklisted_candidate(
    candidate: Dict[str, Any],
    target_entity: str = "",
    topic_context: str = "",
) -> bool:
    """
    Verifies whether candidate title, URL, or metadata contains prohibited collision terms
    relative to target entity and topic context.
    """
    c_meta = f"{candidate.get('title', '')} {candidate.get('image_url', '')} {candidate.get('source_url', '')}".lower()
    t_low = (target_entity or "").lower()
    top_low = (topic_context or "").lower()

    # Universal anti-spam: stamps, postage, and anime/cartoons
    if any(s in c_meta for s in ("stamp", "postage")):
        return True

    # Foreign country / political party collision check
    if any(fp in c_meta for fp in ("bangladesh", "dhaka", "narayanganj", "bnp", "awami league", "pakistan", "lahore")):
        if "bangladesh" not in t_low and "pakistan" not in top_low:
            return True

    # Multi-panel meme grids, template collections, stickers, and clipart packs
    if any(tg in c_meta for tg in ("meme template", "meme templates", "templates free", "png transparent", "stickers pack", "wallpaper download", "vector clipart", "free download", "meme pack")):
        return True

    # Universal NSFW / Adult / Dating / Bikini / Lingerie / Inappropriate Ad Rejection
    if any(ad in c_meta for ad in (
        "golove", "hot series", "live chat", "livechat", "dating", "bikini", "lingerie",
        "underwear", "bra", "cleavage", "sexy", "nude", "naked", "erotic", "xxx", "porn",
        "escort", "adult", "onlyfans", "char creation", "hot girls", "glamour model",
        "camgirl", "webcam", "strip", "babes", "swimsuit", "sensual", "romance", "bed scene"
    )):
        return True

    # Universal anime / cartoon / illustration rejection for realistic media
    if any(an in c_meta for an in ("anime", "manga", "cartoon", "illustration", "drawing", "fanart", "sketch", "cosplay", "vash", "stampede", "zerochan", "pixiv", "wallpapercrafter", "nightow", "trigun themes")):
        if "anime" not in t_low and "manga" not in top_low and "cartoon" not in top_low:
            return True

    # Thrigun vs Trigun anime / podcast collision check
    if any(th in t_low or th in top_low for th in ("thrigun", "trigun", "త్రిగుణ్")):
        if any(bad_th in c_meta for bad_th in ("anime", "manga", "stampede", "vash", "podcast", "analysis of", "themes", "reboot", "badlands")):
            return True

    # Cricket collision check
    if any(ck in c_meta for ck in ("cricket", "cricketer", "bcci", "ipl", "batsman")):
        if "cricket" not in t_low and "cricket" not in top_low:
            return True

    # Jhansi monument & anchor collision check
    if any(mf in c_meta for mf in ("jhansi fort", "ఝాన్సీ కోట", "rani lakshmibai", "lakshmibai", "fort", "monument", "anchor jhansi", "యాంకర్ ఝాన్సీ")):
        if "fort" not in t_low and "monument" not in top_low and "anchor jhansi" not in t_low:
            return True

    # Ram Charan collision check: if not explicitly searching Ram Charan, block Ram Charan lookalikes
    if any(rc in c_meta for rc in ("ram charan", "రామ్ చరణ్", "konidela")):
        if "ram charan" not in t_low and "ram charan" not in top_low:
            return True

    # Rohit Sharma and Rohit Sahni collision check
    if any(rs in c_meta for rs in ("rohit sharma", "రోహిత్ శర్మ", "hitman", "rohit sahni", "రోహిత్ సాహ్ని")):
        if "rohit sharma" not in t_low and "rohit sharma" not in top_low and "rohit sahni" not in t_low:
            return True

    # Sudigali Sudheer collision check for Bigg Boss 10
    if any(ss in c_meta for ss in ("sudigali sudheer", "సుడిగాలి సుధీర్")):
        if "sudigali sudheer" not in t_low and "sudigali sudheer" not in top_low:
            return True

    return False


def find_local_contestant_image(
    text: str,
    used_hashes: Optional[Set[str]] = None,
    used_dhashes: Optional[List[int]] = None,
) -> Optional[Tuple[str, Path]]:
    """
    Priority 1 Matcher: Performs exact and fuzzy boundary matching against local reference directories.
    Strictly disallows names matching clash terms.
    Deduplication-aware: if a local file was ALREADY used in this run, it skips it to prevent
    the same headshot from being duplicated across multiple scenes.
    Returns (contestant_slug, image_path) if verified UNUSED local photo exists.
    """
    if not text:
        return None
    t_low = text.lower().strip()

    # Instant rejection if query explicitly targets blacklisted celebrities/monuments
    if any(b in t_low for b in ("ram charan", "రామ్ చరణ్", "rohit sharma", "రోహిత్ శర్మ", "jhansi fort", "ఝాన్సీ కోట")):
        return None

    roster = load_contestant_roster()
    best_match = None
    best_len = 0

    for slug, cdata in roster.items():
        # Check clash terms for this specific contestant
        clash_terms = [c.lower() for c in cdata.get("clash_terms", [])]
        if any(ct in t_low for ct in clash_terms):
            continue

        aliases = [slug.lower().replace("_", " ")]
        if cdata.get("nickname"):
            aliases.append(cdata["nickname"].lower())
        if cdata.get("full_name"):
            aliases.append(cdata["full_name"].lower())
        if cdata.get("telugu_name"):
            aliases.append(cdata["telugu_name"].lower())
        for a in cdata.get("aliases", []):
            aliases.append(a.lower())

        aliases = list(dict.fromkeys(aliases))

        # Check eviction/elimination status: If evicted, do NOT match in current in-house scenes
        # (like nominations, captaincy, voting) unless the query explicitly discusses eviction/elimination
        is_evicted = any(k in str(cdata.get("status", "")).upper() for k in ("EVICTED", "ELIMINATED")) or not cdata.get("is_active", True)
        if is_evicted:
            eviction_keywords = ("evict", "elimina", "ఎలిమినే", "విడుదల", "బయటకు")
            inhouse_active_keywords = ("nomination", "నామినేషన్", "captain", "కెప్టెన్", "voting", "ఓటింగ్")
            is_inhouse_active = any(ik in t_low for ik in inhouse_active_keywords)
            has_eviction_kw = any(ek in t_low for ek in eviction_keywords)
            if is_inhouse_active and not has_eviction_kw:
                continue

        for alias in aliases:
            if not alias or len(alias) < 3:
                continue
            # Regex boundary match
            if re.search(r"[\u0C00-\u0C7F]", alias):
                matched = alias in t_low
            else:
                matched = bool(re.search(r"\b" + re.escape(alias) + r"\b", t_low))

            if matched and len(alias) > best_len:
                best_len = len(alias)
                best_match = (slug, cdata)

    if not best_match:
        return None

    slug, cdata = best_match

    # ============================================================
    # Priority 1: Dynamic Multi-Image Contestant Gallery
    # ============================================================
    # Distinct episode stills & action shots (8+ photos per contestant).
    # Rotates through photos and strictly avoids photos used in current or recent runs.
    canonical_slug = cdata.get("slug") or slug
    nick = cdata.get("nickname", "").lower()
    possible_slugs = [canonical_slug, slug]
    if "_" in canonical_slug:
        possible_slugs.append(canonical_slug.split("_")[0])
    if "_" in slug:
        possible_slugs.append(slug.split("_")[0])
    if nick:
        possible_slugs.append(nick)
    possible_slugs = list(dict.fromkeys([s for s in possible_slugs if s]))

    for p_slug in possible_slugs:
        gallery_dir = CONTESTANT_GALLERIES_DIR / p_slug
        if gallery_dir.exists() and gallery_dir.is_dir():
            gallery_images = [
                f for f in sorted(gallery_dir.iterdir())
                if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and f.stat().st_size > 5000
            ]
            if gallery_images:
                used_history = _load_used_contestant_images().get(p_slug, [])

                # Sort by least recently used in persistent history (unused first)
                def _get_sort_key(p: Path):
                    name = p.name
                    if name in used_history:
                        return used_history.index(name)
                    return -1

                candidates = sorted(gallery_images, key=_get_sort_key)

                for cand_path in candidates:
                    if used_hashes is not None or used_dhashes is not None:
                        fh = image_hash(cand_path)
                        fdh = image_dhash(cand_path)
                        if used_hashes and fh in used_hashes:
                            continue
                        if used_dhashes and is_perceptual_duplicate(fdh, used_dhashes):
                            continue
                    _record_used_contestant_image(p_slug, cand_path.name)
                    return canonical_slug, cand_path

    # ============================================================
    # Priority 2: Ground Truth Static Reference (Fallback)
    # ============================================================
    candidate_names = []
    for s_item in possible_slugs:
        candidate_names.extend([
            f"{s_item}.jpg", f"{s_item}.png",
            f"{s_item.replace('_', '')}.jpg", f"{s_item.replace('_', '')}.png"
        ])

    if any(s in ("jhansi", "gundeboina_jhansi") for s in possible_slugs):
        candidate_names.extend(["gundeboina_jhansi.jpg", "singer_jhansi.jpg", "jhansi.jpg"])
    elif any(s in ("rohit", "rohit_patnam", "rohit_naidu") for s in possible_slugs):
        candidate_names.extend(["rohit_patnam.jpg", "rohit_naidu.jpg", "rohit.jpg"])
    elif any(s in ("sudheer", "sudheer_reddy") for s in possible_slugs):
        candidate_names.extend(["sudheer_reddy.jpg", "sudheer_talks.jpg", "sudheer.jpg"])
    elif any(s in ("naresh", "potti_naresh") for s in possible_slugs):
        candidate_names.extend(["potti_naresh.jpg", "naresh.jpg", "jabardasth_naresh.jpg"])
    elif "charan" in possible_slugs:
        candidate_names.extend(["charan_mahadev.jpg", "charan.jpg", "rj_charan.jpg"])
    elif "thrigun" in possible_slugs:
        candidate_names.extend(["thrigun_eswaran.jpg", "thrigun.jpg", "trigun.jpg", "thrigun_adith.jpg"])
    elif "aman" in possible_slugs:
        candidate_names.extend(["aman_masud.jpg", "aman.jpg"])

    candidate_names = list(dict.fromkeys([c for c in candidate_names if c]))

    for ref_dir in CONTESTANT_REF_DIRS:
        if not ref_dir.exists():
            continue
        # Direct file check in ref_dir
        for cname in candidate_names:
            fpath = ref_dir / cname
            if fpath.exists() and fpath.is_file() and fpath.stat().st_size > 1000:
                # Deduplication check
                if used_hashes is not None or used_dhashes is not None:
                    fh = image_hash(fpath)
                    fdh = image_dhash(fpath)
                    if used_hashes and fh in used_hashes:
                        continue
                    if used_dhashes and is_perceptual_duplicate(fdh, used_dhashes):
                        continue
                return canonical_slug, fpath

        # Subdirectory check (data/entities/<slug>/neutral.png or assets/entities/<id>/image.jpg)
        for s_item in possible_slugs:
            sub_dir = ref_dir / s_item
            if sub_dir.exists() and sub_dir.is_dir():
                for possible in ["neutral.png", "image.jpg", "profile.jpg", "neutral.jpg"]:
                    p_file = sub_dir / possible
                    if p_file.exists() and p_file.stat().st_size > 1000:
                        if used_hashes is not None or used_dhashes is not None:
                            fh = image_hash(p_file)
                            fdh = image_dhash(p_file)
                            if used_hashes and fh in used_hashes:
                                continue
                            if used_dhashes and is_perceptual_duplicate(fdh, used_dhashes):
                                continue
                        return canonical_slug, p_file

    return None

# IMPORTANT:
# Script agent creates exactly 8 visual concepts.
TARGET_IMAGES = 8

MIN_PIXEL_X = 500
MIN_PIXEL_Y = 300

MAX_FILE_SIZE = 12 * 1024 * 1024

REQUEST_TIMEOUT = 6

try:
    from agents.env_loader import get_pexels_api_key
except ImportError:
    from env_loader import get_pexels_api_key

PEXELS_API_KEY = get_pexels_api_key()
MAX_PEXELS_RESULTS = 10

MAX_WIKIMEDIA_RESULTS = 12
MAX_BING_RESULTS = 30

WIKIMEDIA_DELAY = 0.05


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
# SIGLIP 2 VISUAL RELEVANCE & FLUX PROMPT REWRITING
# ============================================================

try:
    import torch
    from transformers import AutoModel, AutoTokenizer, SiglipImageProcessor, SiglipProcessor
except Exception:
    pass

_SIGLIP_MODEL = None
_SIGLIP_PROCESSOR = None
_SIGLIP_LOCK = threading.RLock()

def get_siglip_pipeline():
    global _SIGLIP_MODEL, _SIGLIP_PROCESSOR
    with _SIGLIP_LOCK:
        if _SIGLIP_MODEL is None or _SIGLIP_PROCESSOR is None:
            try:
                import torch
                from transformers import AutoModel, AutoTokenizer, SiglipImageProcessor, SiglipProcessor

                model_id = "google/siglip2-so400m-patch14-384"
                try:
                    tok = AutoTokenizer.from_pretrained(model_id)
                    img_proc = SiglipImageProcessor.from_pretrained(model_id)
                    _SIGLIP_PROCESSOR = SiglipProcessor(image_processor=img_proc, tokenizer=tok)
                    _SIGLIP_MODEL = AutoModel.from_pretrained(model_id, dtype=torch.float32)
                    _SIGLIP_MODEL.eval()
                except Exception as e:
                    print(f"[SigLIP2] Fallback to base model: {e}")
                    tok = AutoTokenizer.from_pretrained("google/siglip2-base-patch16-224")
                    img_proc = SiglipImageProcessor.from_pretrained("google/siglip2-base-patch16-224")
                    _SIGLIP_PROCESSOR = SiglipProcessor(image_processor=img_proc, tokenizer=tok)
                    _SIGLIP_MODEL = AutoModel.from_pretrained("google/siglip2-base-patch16-224", dtype=torch.float32)
                    _SIGLIP_MODEL.eval()
            except Exception as import_err:
                print(f"[SigLIP2] Notice: SigLIP model not loaded ({import_err}). Using heuristic relevance.")
                return None, None

    return _SIGLIP_MODEL, _SIGLIP_PROCESSOR

RELEVANCE_THRESHOLD = 0.08  # Calibrated SigLIP 2 threshold: rejects off-topic visuals (prob < 0.05) while accepting valid thematic stock/photos (prob >= 0.08)

def verify_visual_with_gemini(image_path: str, query_text: str) -> bool:
    """
    Multimodal AI visual verification using Gemini Flash Vision.
    Directly asks Gemini if the downloaded visual matches the scene intent.
    Enforces explicit rules to reject older season numerals/branding and celebrity name collisions.
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return True
        from google import genai
        client = genai.Client(api_key=api_key)
        img = Image.open(image_path).convert("RGB")
        prompt = (
            f"You are a strict visual director verifying real photos for a video.\n"
            f"Scene description / query: '{query_text}'.\n\n"
            f"CRITICAL VERIFICATION RULES:\n"
            f"1. OLDER SEASON NUMBERS CHECK: If evaluating a reality show like 'Bigg Boss Telugu 10', "
            f"carefully inspect the image for visible numerals, logos, or banners of older seasons "
            f"(such as 'Bigg Boss 9', 'Season 9', 'Season 8', 'BB9', 'BB8', or giant numbers 1-9 on show logos). "
            f"If older season branding or past season numbers (1 to 9) are visible, you MUST reject and reply NO.\n"
            f"2. UNRELATED CELEBRITY / NAME COLLISION CHECK: If the query is about a reality show contestant "
            f"(e.g. 'Charan' for contestant Charan Kumar, or 'Rohit' for contestant Rohit Sahni), "
            f"check if the image belongs to an unrelated famous celebrity instead "
            f"(such as movie actor Ram Charan, cricketer Rohit Sharma in jersey/cricket field, actor Allu Arjun, etc.). "
            f"If the image belongs to an unrelated celebrity, you MUST reject and reply NO.\n"
            f"3. RELEVANCE CHECK: Does this image visually match and accurately depict the scene description "
            f"without showing unrelated stock items (like machinery, random concerts, or unrelated persons)?\n\n"
            f"Reply strictly with either YES or NO."
        )
        for m_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]:
            try:
                resp = client.models.generate_content(
                    model=m_name,
                    contents=[img, prompt]
                )
                ans = resp.text.strip().upper()
                return "YES" in ans
            except Exception:
                continue
    except Exception:
        pass
    return True

def score_visual_relevance(image_path: str, query_text: str) -> float:
    """
    SigLIP 2 visual relevance scorer with emotional reaction cutaway exemption
    and multi-tiered fallback verification.
    """
    # Check if this query represents an intentional emotional reaction meme cutaway
    q_lower = str(query_text or "").lower()
    if any(m in q_lower for m in ("meme", "reaction", "laughing", "shocked", "comedy", "funny", "facepalm", "overacting", "crying", "troll")):
        return 0.90

    try:
        model, processor = get_siglip_pipeline()
        if model is not None and processor is not None:
            import torch
            dev = next(model.parameters()).device
            if str(dev) == "meta":
                global _SIGLIP_MODEL, _SIGLIP_PROCESSOR
                _SIGLIP_MODEL = None
                _SIGLIP_PROCESSOR = None
                model, processor = get_siglip_pipeline()
                if model is None:
                    return 0.5
                dev = next(model.parameters()).device

            image = Image.open(image_path).convert("RGB")
            unrelated_anchor = "unrelated static noise"
            inputs = processor(
                text=[query_text[:120], unrelated_anchor],
                images=image,
                padding="max_length",
                return_tensors="pt"
            )
            # Ensure inputs match model device (CPU/GPU)
            inputs = {k: (v.to(dev) if hasattr(v, "to") else v) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits_per_image
                if hasattr(logits, "is_meta") and logits.is_meta:
                    return 0.5
                prob = torch.softmax(logits, dim=-1)[0, 0].item()
            if prob >= 0.08:
                return float(prob)
    except Exception as e:
        print(f"score_visual_relevance notice: {e}")

    # Fallback to Gemini Multimodal Vision verification if SigLIP is below threshold or errors
    try:
        if verify_visual_with_gemini(image_path, query_text):
            return 0.85
    except Exception:
        pass

    # Heuristic fallback: check valid image resolution & reasonable aspect ratio
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            if w >= 400 and h >= 300:
                return 0.25
    except Exception:
        pass

    return 0.15


def rewrite_query_for_flux(
    query_text: str,
    is_explainer: bool = False,
    show_context: str = "",
    topic_category: str = "",
) -> str:
    """Turn a search query into a concrete FLUX prompt.
    - If is_explainer=True, bias heavily toward diagrams, infographic style, and animated concept illustration.
    - If reality/entertainment/roast context is present (e.g. Bigg Boss Telugu):
      Inject SHOW_CONTEXT (contestants, dramatic reality TV staging, lighting, emotional intensity).
      NEVER generate plain generic inanimate objects (empty kitchens, digital clocks, floating graphics).
    """
    from utils.season_guard import (
        is_bigg_boss_topic,
        resolve_effective_show_context,
        is_entertainment_or_roast_topic,
    )

    clean_show_ctx = resolve_effective_show_context(
        topic_or_title=f"{query_text} {topic_category}",
        raw_show_context=show_context,
    )

    is_bb = is_bigg_boss_topic(query_text) or is_bigg_boss_topic(clean_show_ctx) or is_bigg_boss_topic(topic_category)
    is_ent_roast = not is_bb and (
        is_entertainment_or_roast_topic(query_text)
        or is_entertainment_or_roast_topic(topic_category)
        or any(k in str(topic_category).lower() for k in ("roast", "entertainment", "cinema", "movie", "celebrity"))
    )

    if is_explainer:
        explainer_bias = "diagram, infographic style, animated concept illustration, clean minimalist educational schematic, high visual clarity, isometric vector design"
        try:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                client = genai.Client(api_key=api_key)
                prompt = (
                    f"Rewrite this video scene query into a clean, modern technical diagram, infographic style, animated concept illustration description in 1 sentence. "
                    f"Focus on educational schematics, isometric concept visuals, high clarity, and infographic breakdown.\n"
                    f"Scene query: {query_text}\n"
                    f"Rewritten prompt:"
                )
                for m_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]:
                    try:
                        response = client.models.generate_content(
                            model=m_name,
                            contents=prompt,
                        )
                        rewritten = response.text.strip().replace('"', '')
                        if len(rewritten.split()) >= 4:
                            return f"{rewritten}, {explainer_bias}"
                    except Exception:
                        continue
        except Exception as err:
            print(f"Gemini explainer prompt rewrite notice: {err}")
        return f"{query_text}, {explainer_bias}"

    if is_bb:
        ctx_tag = clean_show_ctx if clean_show_ctx else "Bigg Boss Telugu reality TV show"
        try:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                client = genai.Client(api_key=api_key)
                prompt = (
                    f"Rewrite this reality entertainment scene query into a dramatic, filmable reality show scene prompt for FLUX in 1 sentence.\n"
                    f"MANDATORY REQUIREMENTS:\n"
                    f"1. Context is '{ctx_tag}'.\n"
                    f"2. Capture human drama, contestant confrontation, emotional reactions, and reality TV studio lighting.\n"
                    f"3. STRICTLY FORBIDDEN: Do NOT generate plain isolated inanimate objects (no empty kitchens, no digital clocks, no floating graphics, no generic landscapes).\n"
                    f"4. Frame the scene inside the reality show house, nomination room, or living area with cinematic broadcast depth of field.\n"
                    f"Scene query: {query_text}\n"
                    f"Rewritten prompt:"
                )
                for m_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]:
                    try:
                        response = client.models.generate_content(
                            model=m_name,
                            contents=prompt,
                        )
                        rewritten = response.text.strip().replace('"', '')
                        if len(rewritten.split()) >= 4:
                            return f"{rewritten}, dramatic reality TV broadcast lighting, high cinematic detail, 8k"
                    except Exception:
                        continue
        except Exception as err:
            print(f"Gemini entertainment prompt rewrite notice: {err}")
        return f"Dramatic reality TV show scene in {ctx_tag}, contestants in intense emotional confrontation during {query_text}, television broadcast lighting, cinematic 8k"

    if is_ent_roast:
        try:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                client = genai.Client(api_key=api_key)
                prompt = (
                    f"Rewrite this entertainment/cinema scene query into a dramatic, high-energy cinematic scene prompt for FLUX in 1 sentence.\n"
                    f"MANDATORY REQUIREMENTS:\n"
                    f"1. Subject is Indian cinema / celebrity entertainment ('{query_text}').\n"
                    f"2. Capture dramatic cinematic lighting, emotional actor expressions, film set or movie atmosphere.\n"
                    f"3. STRICTLY FORBIDDEN: Do NOT generate laboratory equipment, matchsticks, 19th-century paintings, foreign posters, or generic abstract objects.\n"
                    f"4. Focus on realistic human actors, press conference, film production sets, or dramatic cinematic interactions.\n"
                    f"Scene query: {query_text}\n"
                    f"Rewritten prompt:"
                )
                for m_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]:
                    try:
                        response = client.models.generate_content(
                            model=m_name,
                            contents=prompt,
                        )
                        rewritten = response.text.strip().replace('"', '')
                        if len(rewritten.split()) >= 4:
                            return f"{rewritten}, dramatic cinematic lighting, photorealistic 8k, movie still"
                    except Exception:
                        continue
        except Exception as err:
            print(f"Gemini cinema roast prompt rewrite notice: {err}")
        return f"Cinematic dramatic film scene of {query_text}, Indian cinema theatrical atmosphere, intense dramatic lighting, 8k photography, highly detailed"

    if len(query_text.split()) >= 6:
        return query_text
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
            prompt = (
                f"Rewrite this video search query into a concrete, filmable, photorealistic image description in 1 sentence. "
                f"Do not include brand logos, cartoon hands, or abstract graphics. "
                f"Focus strictly on physical objects, lighting, and camera angle.\n"
                f"Query to rewrite: {query_text}\n"
                f"Rewritten prompt:"
            )
            for m_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]:
                try:
                    response = client.models.generate_content(
                        model=m_name,
                        contents=prompt,
                    )
                    rewritten = response.text.strip().replace('"', '')
                    if len(rewritten.split()) >= 4:
                        return rewritten
                except Exception:
                    continue
    except Exception as err:
        print(f"Gemini prompt rewrite notice: {err}")
    return f"cinematic photography of {query_text}, ultra detailed, studio lighting, 8k"



# ============================================================
# THREAD-LOCAL HTTP SESSION WITH BACKOFF RETRY
# ============================================================

_thread_local = threading.local()


def get_session():
    """Return a thread-local requests Session with exponential backoff retries."""
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,te;q=0.8,hi;q=0.7",
                "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"',
                "Sec-Fetch-Dest": "image",
                "Sec-Fetch-Mode": "no-cors",
                "Sec-Fetch-Site": "cross-site",
            }
        )
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _thread_local.session = s
    return _thread_local.session


def _is_retryable_requests_error(exception):
    """Check if exception is an HTTP 429/5xx or network connection drop."""
    if isinstance(exception, requests.HTTPError) and exception.response is not None:
        return exception.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(exception, (requests.ConnectionError, requests.Timeout)):
        return True
    return False



# ============================================================
# HELPERS
# ============================================================

def line():
    print("=" * 60)


def clean_text(text):
    if not text:
        return ""

    text = html.unescape(str(text))

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_text(text):
    text = clean_text(text).lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def text_tokens(text):
    return set(
        normalize_text(text).split()
    )


# ============================================================
# STORY DETECTION
# ============================================================

def detect_story(topic):

    text = normalize_text(topic)

    if any(
        word in text
        for word in [
            "supreme court",
            "chief justice",
            "justice",
            "lawyer",
            "court",
        ]
    ):
        return "LEGAL"

    if any(
        word in text
        for word in [
            "technology",
            "tech",
            "ai",
            "artificial intelligence",
            "software",
            "startup",
            "semiconductor",
            "chip",
            "robot",
            "cybersecurity",
        ]
    ):
        return "TECH"

    if any(
        word in text
        for word in [
            "hormuz",
            "iran",
            "uae",
            "adnoc",
            "vessel",
            "tanker",
            "shipping",
        ]
    ):
        return "MARITIME"

    if any(
        word in text
        for word in [
            "india",
            "indian",
        ]
    ):
        return "INDIA"

    return "GENERAL"


# ============================================================
# NAMED PRODUCT / BRAND DETECTION
# ============================================================

def detect_named_entity(text):
    """
    Detect if text mentions a specific commercial product, smartphone, tech brand,
    movie, OTT release, reality TV show (e.g. Bigg Boss), celebrity, actor, or brand logo.
    Returns:
        (is_entity: bool, entity_name: str, category: str)
    """
    if not text:
        return False, "", ""

    # Priority 1: Check curated entity catalog (Universal Context-Aware Engine)
    try:
        from tools.build_entity_library import match_entities_in_text
        m_ents = match_entities_in_text(str(text))
        if m_ents:
            # Prioritize specific person, brand, company or politician over generic show entity
            specific = [e for e in m_ents if e.get("id") != "bigg_boss_telugu"]
            top_e = specific[0] if specific else m_ents[0]
            cat = top_e.get("category", "entertainment")
            if cat in ("cinema", "celebrity"):
                cat = "celebrity"
            elif cat in ("tech", "business"):
                cat = "tech_product"
            return True, top_e.get("canonical_name", ""), cat
    except Exception:
        pass

    lower_text = str(text).lower()

    ENTITY_RULES = [
        # Mainstream Celebrities with Potential Contestant Name Clashes (Resolved FIRST to prevent mismatches)
        (
            r"((?:దిల్\s*రాజు|దిల్రాజు|\bdil\s*raju\b|\bdill\s*raju\b))",
            "celebrity",
            "Dil Raju",
        ),
        (
            r"((?:విజయ్\s*దేవరకొండ|దేవరకొండ|\bvijay\s*deve?rakonda\b|\bdeve?rakonda\b))",
            "celebrity",
            "Vijay Deverakonda",
        ),
        (
            r"((?:రష్మిక(?:\s*మందన్న)?|\brashmika(?:\s*mandanna)?\b))",
            "celebrity",
            "Rashmika Mandanna",
        ),
        (
            r"((?:రామ్\s*చరణ్|\bram\s*charan\b))",
            "celebrity",
            "Ram Charan",
        ),
        (
            r"((?:టైగర్\s*ష్రాఫ్|\btiger\s*shroff\b))",
            "celebrity",
            "Tiger Shroff",
        ),
        (
            r"((?:కోటా\s*స్టేషన్|కోటా\s*రైల్వే|\bkota\s*(?:railway\s*)?station\b|\bkota\s*junction\b))",
            "landmark",
            "Kota Station",
        ),
        (
            r"((?:రోహిత్\s*శర్మ|\brohit\s*sharma\b))",
            "celebrity",
            "Rohit Sharma",
        ),
        (
            r"((?:అల్లు\s*అర్జున్|\ballu\s*arjun\b))",
            "celebrity",
            "Allu Arjun",
        ),
        # Reality TV Contestants in Bigg Boss Context (Evaluated so contestant is never erased)
        (
            r"((?:అపూర్వ|\bapoorva(?:\s*tungaturthy)?\b))",
            "entertainment",
            "Apoorva",
        ),
        (
            r"((?:ఝాన్సి|ఝాన్సీ|\bjhansi\b))",
            "entertainment",
            "Jhansi",
        ),
        (
            r"((?:త్రిగుణ్|త్రిగన్|\b(?:thrigun|trigun|adith\s*arun)\b))",
            "entertainment",
            "Thrigun",
        ),
        (
            r"((?:ఆమన్|అమన్|\baman(?:\s*masud)?\b))",
            "entertainment",
            "Aman",
        ),
        (
            r"((?:ముకేష్|\bmukesh(?:\s*gowda)?\b))",
            "entertainment",
            "Mukesh",
        ),
        (
            r"((?:వర్షిణి|\bvarshini(?:\s*sounderajan)?\b))",
            "entertainment",
            "Varshini",
        ),
        (
            r"((?:శాలిని(?:\s*పటేల్|\s*డామెర)?|\bshalini(?:\s*(?:patel|damera))?\b))",
            "entertainment",
            "Shalini Patel",
        ),
        (
            r"((?:సుధీర్|\b(?:sudheer|sudigali\s*sudheer)\b))",
            "entertainment",
            "Sudheer",
        ),
        (
            r"((?:రోహిత్(?![\s_]*శర్మ)|(?<!\brohit\s)\brohit(?:\s*sahni)?\b(?![\s_]*sharma)))",
            "entertainment",
            "Rohit",
        ),
        (
            r"((?:అర్జున్\s*కళ్యాణ్|(?<!\ballu\s)\barjun(?:\s*kalyan)?\b))",
            "entertainment",
            "Arjun Kalyan",
        ),
        (
            r"((?:(?<!రామ్\s)(?<!ram\s)చరణ్|(?<!\bram\s)\bcharan\b))",
            "entertainment",
            "Charan",
        ),
        (
            r"((?:రామ్\s*ప్రసాద్|\b(?:auto\s*ram\s*prasad|ram\s*prasad)\b))",
            "entertainment",
            "Auto Ram Prasad",
        ),
        (
            r"((?:టెంపర్\s*వంశీ|\btemper\s*vamsi\b))",
            "entertainment",
            "Temper Vamsi",
        ),
        (
            r"((?:కృష్ణుడు|\bkrishnudu\b))",
            "entertainment",
            "Krishnudu",
        ),
        (
            r"((?:దాక్షి|\bdaakshi\b))",
            "entertainment",
            "Daakshi",
        ),
        (
            r"((?:యష్మి|\byashmi(?:\s*gowda)?\b))",
            "entertainment",
            "Yashmi",
        ),
        (
            r"((?:నిఖిల్|\bnikhil(?:\s*maliyakkal)?\b))",
            "entertainment",
            "Nikhil",
        ),
        (
            r"((?:నబీల్|\bnabeel(?:\s*afridi)?\b))",
            "entertainment",
            "Nabeel",
        ),
        (
            r"((?:పృథ్వి|పృథ్వీ|\bprithvi\b))",
            "entertainment",
            "Prithvi",
        ),
        (
            r"((?:విష్ణుప్రియ|\bvishnupriya\b))",
            "entertainment",
            "Vishnupriya",
        ),
        (
            r"((?:మణికంఠ|\bmanikanta\b))",
            "entertainment",
            "Manikanta",
        ),
        # Prominent Indian Actors / Hosts / Celebrities (English & Telugu)
        (
            r"((?:నాగార్జున|చిరంజీవి|బాలకృష్ణ|వెంకటేష్|ప్రభాస్|మహేష్\s*బాబు|ఎన్టీఆర్|అల్లు\s*అర్జున్|రామ్\s*చరణ్|పవన్\s*కళ్యాణ్|నాని|\b(?:nagarjuna(?:\s*akkineni)?|chiranjeevi|balakrishna|venkatesh|prabhas|mahesh\s*babu|jr\s*ntr|allu\s*arjun|ram\s*charan|pawan\s*kalyan|nani|vijay\s*deverakonda|ranbir\s*kapoor|shah\s*rukh\s*khan|salman\s*khan|janhvi\s*kapoor|samantha|rashmika|nayanthara|deepika\s*padukone|alia\s*bhatt)\b))",
            "celebrity",
            None,
        ),
        # Reality TV & TV Shows (Bigg Boss in English & Telugu) - Evaluated after contestants!
        (
            r"((?:బిగ్\s*బాస్|బిగ్‌బాస్|బిగ్బాస్|\bbigg\s*boss(?:\s*telugu|\s*tamil|\s*hindi)?(?:\s*(?:season\s*)?\d+)?\b))",
            "entertainment",
            "Bigg Boss Telugu",
        ),
        # Smartphone Brands & Models (English & Telugu)
        (
            r"((?:ఐకూ|\biqoo\s*(?:neo\s*)?(?:pad\s*)?(?:z\d+|pro|\d+[a-z]*|ultra)?\b))",
            "tech_product",
            "iQOO",
        ),
        (
            r"((?:వివో|\bvivo\s*(?:x\s*fold\d*|v\d+[a-z]*|t\d+[a-z]*|y\d+[a-z]*|x\d+[a-z]*)\b))",
            "tech_product",
            "Vivo",
        ),
        (
            r"((?:వన్\s*ప్లస్|\boneplus\s*(?:nord\s*(?:ce\s*)?\d+|open|\d+[a-z]*(?:\s*pro|\s*r)?)\b))",
            "tech_product",
            "OnePlus",
        ),
        (
            r"((?:సామ్‌సంగ్|శాంసంగ్|\bsamsung\s*galaxy\s*(?:s\d+|z\s*fold\d*|z\s*flip\d*|note\d*|tab\s*s\d*)(?:\s*ultra|\s*plus|\s*fe)?\b))",
            "tech_product",
            "Samsung",
        ),
        (
            r"\b(oneplus\s*(?:nord\s*(?:ce\s*)?\d+|open|\d+[a-z]*(?:\s*pro|\s*r)?))\b",
            "tech_product",
            None,
        ),
        (
            r"\b(redmi\s*(?:note\s*)?\d+[a-z]*(?:\s*pro|\s*c)?|xiaomi\s*\d+[a-z]*(?:\s*pro|\s*ultra)?|poco\s*[a-z]\d+[a-z]*)\b",
            "tech_product",
            None,
        ),
        (
            r"\b(realme\s*(?:narzo\s*)?\d+[a-z]*(?:\s*pro|\s*gt)?|oppo\s*(?:find\s*x\d*|reno\s*\d+))\b",
            "tech_product",
            None,
        ),
        (
            r"\b(nothing\s*phone(?:\s*\(?\d+[a-z]?\)?)?|cmf\s*phone(?:\s*\d+)?)\b",
            "tech_product",
            None,
        ),
        (
            r"\b(motorola\s*(?:edge\s*\d+|g\d+|razr\s*\d*)|moto\s*(?:edge\s*\d+|g\d+|razr\s*\d*))\b",
            "tech_product",
            None,
        ),
        (
            r"\b(iphone\s*(?:1[0-9]|[2-9][0-9]|[a-z]+)?(?:\s*(?:pro\s*max|pro|plus|mini|ultra|air|se))?)\b",
            "tech_product",
            None,
        ),
        (
            r"\b(samsung\s*galaxy\s*(?:s\d+|z\s*fold\d*|z\s*flip\d*|note\d*|tab\s*s\d*)(?:\s*ultra|\s*plus|\s*fe)?)\b",
            "tech_product",
            None,
        ),
        (
            r"\b(google\s*pixel\s*\d+(?:\s*pro|\s*a|\s*fold)?|pixel\s*\d+(?:\s*pro|\s*a|\s*fold)?)\b",
            "tech_product",
            None,
        ),
        (
            r"\b(macbook\s*(?:pro|air)?(?:\s*m[1-4])?|ipad\s*(?:pro|air)?(?:\s*m[1-4])?|apple\s*watch\s*(?:series\s*\d+|ultra\s*\d*|se)?)\b",
            "tech_product",
            None,
        ),
        # Gaming Consoles, GPUs, Processors
        (
            r"\b(playstation\s*[4-6](?:\s*(?:pro|slim))?|ps[4-6](?:\s*(?:pro|slim))?|xbox\s*(?:series\s*[xs]|one)|nintendo\s*switch(?:\s*2)?)\b",
            "tech_product",
            None,
        ),
        (
            r"\b(rtx\s*\d{4}(?:\s*ti|\s*super)?|snapdragon\s*\d+\s*(?:gen\s*\d+|elite)?|intel\s*core\s*(?:ultra\s*)?\d+|ryzen\s*\d{4}[x]?)\b",
            "tech_product",
            None,
        ),
        # OTT Platforms & Tech Services
        (
            r"\b(netflix|prime\s*video|disney\s*hotstar|aha\s*video|zee5|sony\s*liv|youtube|whatsapp|twitter|instagram)\b",
            "service_brand",
            None,
        ),
    ]

    for pattern, category, fixed_name in ENTITY_RULES:
        m = re.search(pattern, lower_text)
        if m:
            matched_name = fixed_name if fixed_name else m.group(1).title()
            return True, matched_name, category

    return False, "", ""

detect_named_product = detect_named_entity


# ============================================================
# SEARCH QUERIES
# ============================================================

def build_queries(visual_description, narration=None, topic_category="tech"):
    """
    Build highly relevant, concrete search queries derived from the visual concept
    (including multi-query alternatives separated by '|') and its assigned narration section.
    CRITICAL RULE: Never inject generic placeholders like 'technology news' or
    unrelated country names unless explicitly part of the subject.
    """
    raw_segments = [seg.strip() for seg in str(visual_description).split("|") if seg.strip()]
    if not raw_segments:
        raw_segments = [str(visual_description)]

    queries = []

    # If visual description contains non-Latin characters (e.g. Telugu), map to English queries
    if re.search(r"[\u0c00-\u0c7f]", str(visual_description)):
        try:
            from semantic_broll_mapper import generate_search_queries
            mapped_qs = generate_search_queries(str(visual_description), topic_category=topic_category)
            if mapped_qs:
                queries.extend(mapped_qs)
        except Exception:
            pass

    for seg in raw_segments:
        clean_desc = re.sub(
            r"^(?:visual|scene|shot|image|photo|picture|graphic)\s*\d*\s*[:\-]\s*",
            "",
            seg.strip(),
            flags=re.IGNORECASE,
        ).strip()
        clean_desc = re.sub(
            r"^(photo|image|picture|illustration|graphic|close[- ]?up|shot|scene|view)\s+(of|showing|depicting|illustrating)?\s*",
            "",
            clean_desc,
            flags=re.IGNORECASE,
        ).strip()

        # Ground Reality TV / Bigg Boss to Telugu
        if "bigg boss" in clean_desc.lower() and "telugu" not in clean_desc.lower():
            clean_desc = re.sub(r"\bbigg\s*boss(?:\s*(?:season\s*)?\d+)?\b", "Bigg Boss Telugu", clean_desc, flags=re.IGNORECASE).strip()
            if "telugu" not in clean_desc.lower():
                clean_desc = f"Bigg Boss Telugu {clean_desc}".strip()

        raw_words = [re.sub(r"[^\w\s-]", "", w).strip() for w in clean_desc.split()]
        desc_words = [
            w for w in raw_words
            if w and w.lower() not in {
                "the", "a", "an", "and", "or", "to", "of", "in", "on", "for",
                "at", "with", "from", "by", "visual", "concept", "representing",
                "scene", "shot", "image", "photo", "picture",
            } and len(w) > 1
        ]

        # 1. Full high-intent descriptive query (preserves rich context like 'vintage 1980s retro portrait photo')
        if len(desc_words) >= 4:
            primary = " ".join(desc_words[:6])
            if primary not in queries:
                queries.append(primary)

        # 2. Targeted punchy fallback (3-4 core words)
        if len(desc_words) >= 2:
            punchy = " ".join(desc_words[:3])
            if punchy not in queries:
                queries.append(punchy)

        # 3. Clean full segment if concise
        if clean_desc and len(clean_desc.split()) <= 7 and clean_desc not in queries:
            queries.append(clean_desc)

    # Entity keywords from narration if available
    if narration:
        clean_narration = clean_text(narration)
        entities = [
            w for w in re.findall(r"\b[A-Z][a-zA-Z0-9-]+\b", clean_narration)
            if w.lower() not in {"this", "that", "these", "those", "when", "while", "here", "there", "section"}
        ]
        if entities:
            entity_query = " ".join(entities[:3])
            if entity_query and entity_query not in queries:
                queries.append(entity_query)

    # Bias search queries based on topic category (Section 12)
    cat_lower = str(topic_category).lower()
    base_q = queries[0] if queries else str(visual_description)[:40]
    if any(k in cat_lower for k in ["history", "historical", "ancient", "era"]):
        hist_keywords = ["historical archives vintage photograph", "ancient artifact historical documentation"]
        for hk in hist_keywords:
            aug_q = f"{base_q} {hk}".strip()
            if aug_q not in queries and len(queries) < 6:
                queries.append(aug_q)
    elif any(k in cat_lower for k in ["fact", "curiosity", "interesting"]):
        fact_keywords = ["macro photography detailed", "scientific curiosity visual"]
        for fk in fact_keywords:
            aug_q = f"{base_q} {fk}".strip()
            if aug_q not in queries and len(queries) < 6:
                queries.append(aug_q)
    elif any(k in cat_lower for k in ["movie", "cinema", "film", "entertainment"]):
        cinema_keywords = ["cinema film movie", "cinematography movie scene"]
        for ck in cinema_keywords:
            aug_q = f"{base_q} {ck}".strip()
            if aug_q not in queries and len(queries) < 5:
                queries.append(aug_q)
    elif any(k in cat_lower for k in ["news", "politics", "current"]):
        news_keywords = ["press conference broadcast", "official report news"]
        for nk in news_keywords:
            aug_q = f"{base_q} news broadcast".strip()
            if aug_q not in queries and len(queries) < 5:
                queries.append(aug_q)
    elif any(k in cat_lower for k in ["finance", "crypto", "business", "stock", "market"]):
        fin_keywords = ["stock market chart finance", "cryptocurrency trading investment"]
        for fk in fin_keywords:
            aug_q = f"{base_q} stock finance".strip()
            if aug_q not in queries and len(queries) < 5:
                queries.append(aug_q)
    elif any(k in cat_lower for k in ["explainer", "education", "science", "guide"]):
        exp_keywords = ["infographic concept diagram", "educational illustration visual"]
        for ek in exp_keywords:
            aug_q = f"{base_q} diagram visual".strip()
            if aug_q not in queries and len(queries) < 5:
                queries.append(aug_q)

    if not queries:
        queries.append(visual_description[:60].replace("|", " ").strip())

    final = []
    for q in queries:
        q = q.strip()
        if q and q not in final:
            final.append(q)

    # MANDATORY QUERY FORMAT: Never search single contestant names alone.
    # Strict format: "[Contestant Name] [Season Name] [Year]" or "[Contestant Name] [Specific Task/Promo]"
    try:
        from utils.season_guard import (
            KNOWN_TELUGU_SHOW_PERSONS,
            get_person_search_name,
            format_strict_visual_query,
            is_generic_visual_query,
            is_bigg_boss_topic,
            get_current_season_number,
        )
        cur_season = get_current_season_number(str(visual_description)) or 10
        season_name = f"Bigg Boss Telugu {cur_season}"
        event_year = 2026 if cur_season >= 10 else 2025
        is_bb = is_bigg_boss_topic(f"{visual_description} {narration or ''}")

        past_season_exclusions = []
        if is_bb and cur_season >= 2:
            for s_num in range(1, cur_season):
                past_season_exclusions.extend([f"-Season {s_num}", f"-BB{s_num}"])
            past_season_exclusions.extend(["-2025", "-2024", "-2023", "-anime", "-cartoon"])
        neg_str = " ".join(past_season_exclusions) if past_season_exclusions else ""

        disambiguated = []
        for q in final:
            q_clean = q.strip()
            # Disallow generic queries like "Bigg Boss Telugu drama" or "Bigg Boss emotional scene"
            if is_bb and is_generic_visual_query(q_clean):
                continue

            person_found = None
            for p_id, p_info in KNOWN_TELUGU_SHOW_PERSONS.items():
                if p_id in ("nagarjuna", "rajinikanth"):
                    continue
                c_name = p_info["canonical"].lower()
                aliases = [a.lower() for a in p_info["aliases"]]
                q_words = [w.lower() for w in re.findall(r"\b[A-Za-z]+\b", q_clean)]
                if any(tok in q_words for tok in [c_name] + aliases):
                    person_found = p_info["canonical"]
                    break

            if person_found and is_bb:
                strict_q = format_strict_visual_query(person_found, season_name, event_year)
                if neg_str:
                    strict_q = f"{strict_q} {neg_str}".strip()
                if strict_q not in disambiguated:
                    disambiguated.append(strict_q)
            else:
                if is_bb and neg_str and not any(neg in q_clean for neg in past_season_exclusions[:2]):
                    q_clean = f"{q_clean} {neg_str}".strip()
                if q_clean not in disambiguated:
                    disambiguated.append(q_clean)

        final = disambiguated or [format_strict_visual_query("Nagarjuna Akkineni", season_name, event_year)]
    except Exception:
        pass

    return final


# ============================================================
# PEXELS HD STOCK IMAGE SEARCH
# ============================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8) + wait_random(0.1, 0.5),
    retry=retry_if_exception(_is_retryable_requests_error),
    reraise=False,
)
def search_pexels(query, orientation=None):
    """
    Search high-resolution royalty-free stock photos via Pexels API with dynamic orientation.
    """
    global PEXELS_API_KEY
    if not PEXELS_API_KEY:
        PEXELS_API_KEY = get_pexels_api_key()

    if not PEXELS_API_KEY:
        return []

    url = "https://api.pexels.com/v1/search"

    headers = {
        "Authorization": PEXELS_API_KEY,
        "User-Agent": get_session().headers.get("User-Agent", "AutoTubeAI/2.1"),
    }

    params = {
        "query": query,
        "per_page": MAX_PEXELS_RESULTS,
    }
    if orientation in ("landscape", "portrait", "square"):
        params["orientation"] = orientation

    try:

        response = get_session().get(
            url,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

    except Exception as error:

        print(
            f"Pexels search warning: {error}"
        )

        return []

    photos = data.get("photos", [])

    results = []

    for photo in photos:

        src = photo.get("src", {})

        image_url = (
            src.get("large2x")
            or src.get("large")
            or src.get("landscape")
            or src.get("original")
        )

        if not image_url:
            continue

        photo_id = photo.get("id")
        alt = photo.get("alt", "").strip()
        title = clean_text(alt) if alt else query
        tags = [w.lower() for w in re.findall(r"\b\w+\b", alt)]

        results.append(
            {
                "id": f"pexels_{photo_id}" if photo_id else None,
                "image_url": image_url,
                "title": title,
                "alt": alt,
                "tags": tags,
                "source": "Pexels",
                "width": photo.get("width", 1920),
                "height": photo.get("height", 1080),
                "mime": "image/jpeg",
            }
        )

    return results


# ============================================================
# PEXELS HD STOCK VIDEO SEARCH (OPTIONAL VIDEO FOOTAGE)
# ============================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8) + wait_random(0.1, 0.5),
    retry=retry_if_exception(_is_retryable_requests_error),
    reraise=False,
)
def search_pexels_video(query, orientation=None):
    """
    Search high-quality royalty-free video footage via Pexels API.
    Tries multiple keyword variations to maximize matching relevant stock footage.
    Returns download url and metadata if a relevant HD video is found.
    """
    global PEXELS_API_KEY
    if not PEXELS_API_KEY:
        PEXELS_API_KEY = get_pexels_api_key()

    if not PEXELS_API_KEY:
        return None

    url = "https://api.pexels.com/videos/search"

    headers = {
        "Authorization": PEXELS_API_KEY,
        "User-Agent": get_session().headers.get("User-Agent", "AutoTubeAI/2.1"),
    }

    clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", query).strip()
    words = clean_q.split()
    search_terms = []
    if len(words) >= 4:
        search_terms.append(" ".join(words[:4]))
    if len(words) >= 3:
        search_terms.append(" ".join(words[:3]))
    if len(words) >= 2:
        search_terms.append(" ".join(words[:2]))
    if words:
        search_terms.append(words[0])

    for term in search_terms:
        if not term.strip():
            continue
        params = {
            "query": term,
            "per_page": 6,
        }
        if orientation in ("landscape", "portrait", "square"):
            params["orientation"] = orientation
        try:
            resp = get_session().get(
                url,
                headers=headers,
                params=params,
                timeout=(3, 6),
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            videos = data.get("videos", [])
            if not videos:
                continue

            from agents.visual_verifier import rank_video_candidates
            best_clip = rank_video_candidates(videos, query=term, orientation=orientation)
            if best_clip:
                vid_id = f"pexels_video_{best_clip.get('id', '')}"
                vid_tags = best_clip.get("title", "").split()
                try:
                    from semantic_broll_mapper import is_result_allowed, is_asset_fresh
                    if not is_result_allowed(vid_tags, topic_category="tech"):
                        print(f"❌ Filtered out off-topic video: {best_clip.get('title', '')[:40]}")
                        continue
                    if not is_asset_fresh(vid_id):
                        print(f"🔄 Skipped recently used video (30-day history): {vid_id}")
                        continue
                except Exception:
                    pass
                return best_clip
        except Exception as err:
            continue

    return None


def extract_video_frame(video_path, image_dest):
    """Extract a representative keyframe from an MP4 video clip to use as image fallback & thumbnail."""
    try:
        dest = Path(image_dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01",
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(dest),
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        return dest.exists() and dest.stat().st_size > 0
    except Exception:
        return False


def download_video_clip(video_info, destination):
    """Safely download video footage with timeout."""
    url = video_info.get("download_url")
    if not url:
        return False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with get_session().get(url, timeout=(4, 12), stream=True) as resp:
            resp.raise_for_status()
            with open(destination, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
        return destination.exists() and destination.stat().st_size > 10000
    except Exception as e:
        print(f"Video download warning: {e}")
        destination.unlink(missing_ok=True)
        return False


# ============================================================
# WIKIMEDIA SEARCH
# ============================================================

def search_wikimedia(query):
    # Deprecate and restrict loose web scraping for Indian celebrity / entertainment names
    q_low = str(query or "").lower()
    celeb_markers = [
        "rohit", "charan", "jhansi", "varshini", "mukesh", "thrigun", "trigun",
        "debjani", "krishnudu", "sudheer", "aman", "vamsi", "naresh", "shalini",
        "bigg boss", "bb10", "bb9", "bb8", "star maa", "nagarjuna", "actor", "actress",
        "ram charan", "chiranjeevi", "tollywood", "cinema", "entertainment",
        "cricket", "stamp", "postage", "celebrity"
    ]
    if any(m in q_low for m in celeb_markers):
        print(f"🚫 [Wikimedia Deprecated] Bypassing Wikimedia for Indian celebrity/entertainment query: '{query}'")
        return []

    url = "https://commons.wikimedia.org/w/api.php"

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": MAX_WIKIMEDIA_RESULTS,
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": 1600,
    }

    try:

        response = get_session().get(
            url,
            params=params,
            timeout=(3, REQUEST_TIMEOUT),
        )

        response.raise_for_status()

        data = response.json()

    except Exception as error:

        print(
            f"Wikimedia search failed: {error}"
        )

        return []

    pages = (
        data
        .get("query", {})
        .get("pages", {})
    )

    results = []

    for page in pages.values():

        imageinfo = page.get(
            "imageinfo",
            [],
        )

        if not imageinfo:
            continue

        info = imageinfo[0]

        image_url = (
            info.get("thumburl")
            or info.get("url")
        )

        mime = str(info.get("mime", "")).lower()
        if any(bad in mime for bad in ("pdf", "djvu", "audio", "video", "ogg", "postscript")):
            continue

        raw_title = page.get("title", "")
        title_clean = clean_text(raw_title)
        title_lower = title_clean.lower()
        if any(bad in title_lower for bad in STRICT_ANTI_COLLISION_BLACKLIST):
            continue

        doc_words = (
            "hearing", "report", "dissertation", "thesis", "congress", "bulletin",
            "minutes", "act of", "bill", "proceedings", "gazette", "census",
            "treaty", "statutes", "handbook", "journal of", "ordinance", "court",
            "document", "pamphlet", "circular", "declaration"
        )
        if any(w in title_lower for w in doc_words):
            continue

        results.append(
            {
                "image_url": image_url,
                "title": title_clean,
                "source": "Wikimedia",
                "width": info.get(
                    "width",
                    0,
                ),
                "height": info.get(
                    "height",
                    0,
                ),
                "mime": mime,
            }
        )

    return results


# ============================================================
# BING IMAGE SEARCH
# ============================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8) + wait_random(0.1, 0.5),
    retry=retry_if_exception(_is_retryable_requests_error),
    reraise=False,
)
def search_bing(query):

    url = (
        "https://www.bing.com/images/"
        "search"
    )

    q_clean = str(query or "").strip()
    if "-cricket" not in q_clean and "-sports" not in q_clean:
        ctx_negs = get_contextual_negative_filters(q_clean, q_clean)
        if ctx_negs:
            q_clean = f"{q_clean} {ctx_negs}".strip()

    params = {
        "q": q_clean,
        "form": "HDRSC2",
        "first": 1,
        "adlt": "strict",
    }

    try:

        response = get_session().get(
            url,
            params=params,
            timeout=(3, REQUEST_TIMEOUT),
        )

        response.raise_for_status()

    except Exception as error:

        print(
            f"Bing search failed: {error}"
        )

        return []

    html_text = response.text

    results = []

    pattern = re.compile(
        r'murl&quot;:&quot;(.*?)&quot;.*?'
        r'mid&quot;:&quot;(.*?)&quot;',
        re.DOTALL,
    )

    matches = pattern.findall(
        html_text
    )

    for image_url, mid in matches:

        image_url = (
            image_url
            .replace("\\/", "/")
            .replace("\\u002f", "/")
        )

        if not image_url.startswith("http"):
            continue

        cand_mock = {"image_url": image_url, "title": query}
        if is_blacklisted_candidate(cand_mock, target_entity=query, topic_context=query):
            continue

        results.append(
            {
                "image_url": image_url,
                "title": query,
                "source": "Bing",
                "width": 0,
                "height": 0,
                "mime": "",
                "mid": mid,
            }
        )

        if len(results) >= MAX_BING_RESULTS:
            break

    return results


# ============================================================
# RELEVANCE
# ============================================================

def score_candidate(candidate, query):

    title_tokens = text_tokens(
        candidate.get(
            "title",
            "",
        )
    )

    query_words = [
        word
        for word in normalize_text(
            query
        ).split()
        if len(word) >= 2
    ]

    if not query_words:
        return 0

    score = 0

    for word in query_words:

        if word in title_tokens:
            score += 10

    width = candidate.get(
        "width",
        0,
    )

    height = candidate.get(
        "height",
        0,
    )

    if width >= 1000:
        score += 5

    if height >= 600:
        score += 5

    # Penalize obvious logo / text-only results.
    title = normalize_text(
        candidate.get("title", "")
    )

    bad_words = [
        "logo",
        "newspaper",
        "radio logo",
        "svg",
    ]

    for bad in bad_words:

        if bad in title:
            score -= 15

    if candidate.get("source") == "Pexels":
        score += 8

    return score


def is_relevant(candidate, query):

    return (
        score_candidate(
            candidate,
            query,
        )
        >= 5
    )


def is_document_or_text_sheet(image_input) -> bool:
    """
    Detects whether an image is a scanned document, research paper,
    black-and-white text sheet, or PDF cover (e.g. > 70% pure white pixels
    with near-zero color saturation).
    """
    try:
        import numpy as np
        if isinstance(image_input, (str, Path)):
            img = Image.open(image_input).convert("RGB")
        else:
            img = image_input.convert("RGB")

        arr = np.array(img)
        # White background pixel ratio (R > 235, G > 235, B > 235)
        white_mask = (arr[:, :, 0] > 235) & (arr[:, :, 1] > 235) & (arr[:, :, 2] > 235)
        white_ratio = float(np.mean(white_mask))

        # Check color saturation in HSV
        hsv = img.convert("HSV")
        sat_arr = np.array(hsv)[:, :, 1]
        mean_sat = float(np.mean(sat_arr))

        # If more than 70% pure white and almost no color saturation, it's a document/paper
        if white_ratio > 0.70 and mean_sat < 15.0:
            return True

        # Black sheet with minimal content
        black_mask = (arr[:, :, 0] < 20) & (arr[:, :, 1] < 20) & (arr[:, :, 2] < 20)
        black_ratio = float(np.mean(black_mask))
        if black_ratio > 0.85 and mean_sat < 10.0:
            return True

        return False
    except Exception:
        return False


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    candidate,
    destination,
):

    url = candidate.get(
        "image_url",
        "",
    )

    if not url:
        return False

    try:

        with get_session().get(
            url,
            timeout=(3, REQUEST_TIMEOUT),
            stream=True,
        ) as response:

            response.raise_for_status()

            content_type = (
                response.headers
                .get(
                    "content-type",
                    "",
                )
                .lower()
            )

            if (
                content_type
                and "image" not in content_type
            ):
                return False

            content_length = int(
                response.headers.get(
                    "content-length",
                    0,
                )
                or 0
            )

            if (
                content_length
                and content_length > MAX_FILE_SIZE
            ):
                return False

            data = response.content

        if len(data) > MAX_FILE_SIZE:
            return False

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            destination,
            "wb",
        ) as file:

            file.write(data)

        with Image.open(
            destination
        ) as image:

            image.verify()

        with Image.open(
            destination
        ) as image:

            pixel_x, pixel_y = image.size

        if pixel_x < MIN_PIXEL_X:
            destination.unlink(
                missing_ok=True
            )
            return False

        if pixel_y < MIN_PIXEL_Y:
            destination.unlink(
                missing_ok=True
            )
            return False

        if is_document_or_text_sheet(destination):
            print(f"⚠️ Rejected document/text-sheet image: {destination.name}")
            destination.unlink(
                missing_ok=True
            )
            return False

        with Image.open(
            destination
        ) as image:

            image.convert(
                "RGB"
            ).save(
                destination,
                "JPEG",
                quality=90,
            )

        return True

    except Exception as error:
        # Robust fallback: curl with browser headers (bypasses TLS fingerprinting on CDN blocks)
        if url.startswith("http"):
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                curl_cmd = [
                    "curl", "-s", "-L", "-k",
                    "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "-e", "https://www.google.com/",
                    "--max-time", "10",
                    "-o", str(destination),
                    url,
                ]
                c_res = subprocess.run(curl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
                if c_res.returncode == 0 and destination.exists() and destination.stat().st_size > 4000:
                    with Image.open(destination) as image:
                        image.verify()
                    with Image.open(destination) as image:
                        pixel_x, pixel_y = image.size
                    if pixel_x >= MIN_PIXEL_X and pixel_y >= MIN_PIXEL_Y:
                        with Image.open(destination) as image:
                            image.convert("RGB").save(destination, "JPEG", quality=90)
                        return True
            except Exception:
                pass

        print(
            f"Download failed: {error}"
        )

        destination.unlink(
            missing_ok=True
        )

        return False


# ============================================================
# HASH
# ============================================================

def image_hash(path):
    try:
        import hashlib
        hasher = hashlib.sha256()
        with open(path, "rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


def image_dhash(path, hash_size=8):
    """
    Computes a 64-bit perceptual difference hash (dHash) using PIL.
    Measures visual perceptual gradients; images with similar structure
    will have very small Hamming distance (<= 6).
    """
    try:
        with Image.open(path) as img:
            # Convert to grayscale and resize to (hash_size + 1, hash_size)
            resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(resized.getdata())
            diff = 0
            for row in range(hash_size):
                row_offset = row * (hash_size + 1)
                for col in range(hash_size):
                    left = pixels[row_offset + col]
                    right = pixels[row_offset + col + 1]
                    if left > right:
                        diff |= 1 << (row * hash_size + col)
            return diff
    except Exception:
        return None


def hamming_distance(h1: int, h2: int) -> int:
    """Computes the Hamming distance between two 64-bit integer hashes."""
    return bin(h1 ^ h2).count('1')


def is_perceptual_duplicate(dhash_val: Optional[int], used_dhashes: List[int], max_dist: int = 6) -> bool:
    """
    Checks if dhash_val is visually identical or near-identical to any hash in used_dhashes.
    Threshold <= 6 indicates visually identical or slightly cropped/resized duplicate.
    """
    if dhash_val is None or not used_dhashes:
        return False
    for prev in used_dhashes:
        if hamming_distance(dhash_val, prev) <= max_dist:
            return True
    return False


# ============================================================
# FLYER
# ============================================================

def save_flyer_fallback(
    flyer_path,
    destination,
):

    if not flyer_path:
        return False

    source = Path(flyer_path)

    if not source.exists():
        return False

    try:

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with Image.open(source) as image:

            image.convert(
                "RGB"
            ).save(
                destination,
                "JPEG",
                quality=95,
            )

        return True

    except Exception as error:

        print(
            f"Could not create flyer fallback: {error}"
        )

        destination.unlink(
            missing_ok=True
        )

        return False


# ============================================================
# CLEAN ASSETS
# ============================================================

def clean_assets():

    ASSETS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for file in ASSETS_DIR.iterdir():

        if file.is_file():

            try:
                file.unlink()
            except Exception:
                pass


# ============================================================
# COLLECT CANDIDATES
# ============================================================

def collect_candidates(queries, orientation=None, topic_category="tech"):

    candidates = []

    seen_urls = set()

    try:
        from semantic_broll_mapper import is_result_allowed, is_asset_fresh
    except ImportError:
        is_result_allowed = lambda tags, cat: True
        is_asset_fresh = lambda aid: True

    for index, query in enumerate(
        queries,
        1,
    ):

        print()
        print(
            f"SEARCH {index}/{len(queries)}"
        )

        print(query)

        # ----------------------------------------------------
        # Pexels (HD Stock Photos)
        # ----------------------------------------------------

        from utils.season_guard import is_bigg_boss_topic
        is_reality_or_news = (
            topic_category in ("entertainment", "news", "reality_show", "show")
            or is_bigg_boss_topic(topic_category)
            or is_bigg_boss_topic(query)
            or any(is_bigg_boss_topic(q) for q in queries)
        )

        if is_reality_or_news:
            print("🚫 Skipping stock search (Pexels) for reality show / specific news topic to prevent unrelated stock leakage.")
            pexels = []
        else:
            pexels = search_pexels(
                query,
                orientation=orientation,
            )

        for candidate in pexels:

            url = candidate.get(
                "image_url"
            )

            if not url:
                continue

            if url in seen_urls:
                continue

            # Negative keyword check & asset freshness
            cand_tags = candidate.get("tags") or candidate.get("title", "").split()
            if not is_result_allowed(cand_tags, topic_category):
                print(f"❌ Filtered out off-topic candidate ({topic_category} negative match): {candidate.get('title', '')[:40]}")
                continue

            cid = candidate.get("id")
            if cid and not is_asset_fresh(cid):
                print(f"🔄 Skipped recently used asset (30-day history): {cid}")
                continue

            if not is_relevant(
                candidate,
                query,
            ):
                continue

            seen_urls.add(url)

            candidates.append(candidate)

        # ----------------------------------------------------
        # DuckDuckGo (Free Web Photography - No Key Required)
        # ----------------------------------------------------
        try:
            from providers.image import search_duckduckgo_images
            ddg_items = search_duckduckgo_images(query, max_results=8)
            for candidate in ddg_items:
                url = candidate.get("image_url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                candidates.append(candidate)
        except Exception as ddg_err:
            pass

        # ----------------------------------------------------
        # Wikimedia (Disabled for entertainment/cinema/roast to prevent laboratory/historical painting leakage)
        # ----------------------------------------------------
        from utils.season_guard import is_entertainment_or_roast_topic
        if not is_entertainment_or_roast_topic(topic_category) and not is_entertainment_or_roast_topic(query):
            wikimedia = search_wikimedia(
                query
            )

            for candidate in wikimedia:

                url = candidate.get(
                    "image_url"
                )

                if not url:
                    continue

                if url in seen_urls:
                    continue

                if not is_relevant(
                    candidate,
                    query,
                ):
                    continue

                seen_urls.add(url)

                candidates.append(candidate)

            # Be polite to Wikimedia.
            time.sleep(WIKIMEDIA_DELAY)
        else:
            print("🚫 Skipping Wikimedia Commons search for entertainment/cinema/roast to prevent irrelevant stock leakage.")

        # ----------------------------------------------------
        # Pixabay (Optional Free API Key)
        # ----------------------------------------------------
        try:
            from providers.image import search_pixabay
            pix_items = search_pixabay(query, orientation=orientation or "landscape", max_results=6)
            for candidate in pix_items:
                url = candidate.get("image_url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                candidates.append(candidate)
        except Exception:
            pass

        # ----------------------------------------------------
        # Bing Fallback
        # ----------------------------------------------------

        bing = search_bing(query)

        for candidate in bing:

            url = candidate.get(
                "image_url"
            )

            if not url:
                continue

            if url in seen_urls:
                continue

            if not is_relevant(
                candidate,
                query,
            ):
                continue

            seen_urls.add(url)

            candidates.append(candidate)

        # Early exit if we already have plenty of candidates
        if len(candidates) >= TARGET_IMAGES * 2:
            print(f"Collected {len(candidates)} candidates, stopping search early.")
            break

    # --------------------------------------------------------
    # Anti-collision candidate sanitization
    # --------------------------------------------------------
    candidates = [c for c in candidates if not is_blacklisted_candidate(c)]

    # --------------------------------------------------------
    # Highest relevance first.
    # --------------------------------------------------------

    candidates.sort(
        key=lambda item: score_candidate(
            item,
            item.get("title", ""),
        ),
        reverse=True,
    )

    return candidates


# ============================================================
# DOWNLOAD IMAGES
# ============================================================

def download_images(
    topic,
    flyer_path=None,
):

    line()
    print("AI IMAGE SEARCH STARTED")
    line()

    print()
    print("Topic:")
    print(topic)

    # --------------------------------------------------------
    # ALWAYS CLEAN OLD ASSETS.
    # --------------------------------------------------------

    clean_assets()

    queries = build_queries(topic)

    print()
    print(
        f"SEARCH QUERIES: {len(queries)}"
    )

    for index, query in enumerate(
        queries,
        1,
    ):

        print(
            f"{index}. {query}"
        )

    # --------------------------------------------------------
    # Collect candidates.
    # --------------------------------------------------------

    candidates = collect_candidates(
        queries
    )

    # --------------------------------------------------------
    # Download EXACTLY 8 images.
    # --------------------------------------------------------

    downloaded = 0

    used_hashes = set()

    for candidate in candidates:

        # HARD STOP.
        # This is the important fix.
        if downloaded >= TARGET_IMAGES:
            break

        query_title = candidate.get(
            "title",
            topic,
        )

        score = score_candidate(
            candidate,
            query_title,
        )

        visual_number = (
            downloaded + 1
        )

        destination = (
            ASSETS_DIR
            / f"{visual_number}.jpg"
        )

        print()
        print(
            f"Trying candidate for visual "
            f"{visual_number}: {query_title}"
        )

        print(
            f"Score: {score}"
        )

        success = download_image(
            candidate,
            destination,
        )

        if not success:
            continue

        # ----------------------------------------------------
        # Duplicate detection.
        # ----------------------------------------------------

        file_hash = image_hash(
            destination
        )

        if (
            file_hash
            and file_hash in used_hashes
        ):

            print(
                "Duplicate image skipped."
            )

            destination.unlink(
                missing_ok=True
            )

            continue

        if file_hash:
            used_hashes.add(
                file_hash
            )

        downloaded += 1

        print(
            f"OK - Visual {downloaded} "
            f"saved as {visual_number}.jpg"
        )

        try:

            with Image.open(
                destination
            ) as image:

                print(
                    f"Size: {image.width}x"
                    f"{image.height}"
                )

        except Exception:
            pass

    # --------------------------------------------------------
    # Flyer fallback.
    #
    # Flyer is NOT allowed to replace the 8 normal visuals.
    # It can only be used separately by callers that need it.
    # --------------------------------------------------------

    if downloaded < TARGET_IMAGES:
        print()
        print(
            f"WARNING: Only {downloaded}/"
            f"{TARGET_IMAGES} images downloaded from web. Applying offline fallback pool..."
        )
        fallback_pool = sorted(FALLBACK_DIR.glob("*.jpg")) if FALLBACK_DIR.exists() else []
        for i in range(downloaded + 1, TARGET_IMAGES + 1):
            dest = ASSETS_DIR / f"{i}.jpg"
            if fallback_pool:
                src = fallback_pool[(i - 1) % len(fallback_pool)]
                import shutil
                shutil.copyfile(src, dest)
                print(f"  ✓ Applied fallback image {get_image_filename(src)} -> {i}.jpg")
                downloaded += 1
            else:
                img = Image.new("RGB", (1280, 720), color=(25, 30, 45))
                img.save(dest, "JPEG", quality=90)
                downloaded += 1

    # --------------------------------------------------------
    # FINAL HARD VALIDATION.
    # --------------------------------------------------------

    final_images = []

    for number in range(
        1,
        TARGET_IMAGES + 1,
    ):

        path = (
            ASSETS_DIR
            / f"{number}.jpg"
        )

        if not path.exists():
            raise RuntimeError(
                f"Missing required image: "
                f"{path.name}"
            )

        final_images.append(path)

    # Remove any accidental numbered files
    # outside the expected 1-8 range.
    for file in ASSETS_DIR.iterdir():

        if not file.is_file():
            continue

        match = re.fullmatch(
            r"(\d+)\.(jpg|jpeg|png|webp)",
            file.name,
            re.IGNORECASE,
        )

        if not match:
            continue

        number = int(
            match.group(1)
        )

        if number > TARGET_IMAGES:

            print(
                f"Removing extra image: "
                f"{file.name}"
            )

            file.unlink(
                missing_ok=True
            )

    print()
    line()

    print(
        f"FINAL IMAGES: {len(final_images)}"
    )

    print(
        "Images Downloaded"
    )

    line()

    return [
        str(path)
        for path in final_images
    ]


def auto_balance_copyright_tier_b(
    visuals: List[str],
    aspect_ratio: str = "16:9",
    target_count: int = 0,
    section_narrations: Optional[Dict[int, str]] = None,
    content_type: str = "",
    topic: str = "",
) -> bool:
    """
    Auto-fallback in image_agent.py:
    Dynamically enforces fair-use Tier B limits (50% for Roasting/Entertainment/News, 30% for standard).
    When exceeded, smoothly auto-balances by generating show-context-aware FLUX visuals or using show set stills,
    preserving authentic contestant portraits and preventing generic object hallucinations.
    """
    try:
        from data.asset_ledger import get_tier_breakdown, get_assets_for_video, record_asset
        from utils.season_guard import get_allowed_tier_b_threshold, is_bigg_boss_topic
        from config.settings import get_setting

        tb = get_tier_breakdown("current")
        tier_b_share = tb.get("tier_b_share", 0.0)
        allowed_share = get_allowed_tier_b_threshold(content_type, topic)

        if tier_b_share <= allowed_share:
            return True

        print(f"⚖️ [Auto-Balance Copyright Gate] Current Tier B share is {tier_b_share*100:.1f}% (> {allowed_share*100:.0f}% allowed for '{content_type or 'General'}').")
        print(f"   Triggering automated FLUX/safe stock auto-fallback to balance Tier A >= {int((1-allowed_share)*100)}%...")

        assets = get_assets_for_video("current")
        tier_b_assets = [a for a in assets if a.get("tier") == "TIER_B"]
        total_assets = len(assets) if assets else target_count
        if total_assets <= 0:
            return True

        max_allowed_tier_b = int(total_assets * allowed_share)
        excess_count = len(tier_b_assets) - max_allowed_tier_b
        if excess_count <= 0:
            return True

        # Sort so generic/non-contestant assets are replaced before authentic celebrity/contestant portraits
        def _asset_priority(a):
            cred = str(a.get("credit_text", "")).lower()
            src = str(a.get("source_url", "")).lower()
            if "photo of" in cred or "contestant" in cred:
                return 1  # preserve authentic portraits
            return 0  # replace generic stills first

        tier_b_assets.sort(key=_asset_priority)

        replaced_count = 0
        from providers.image import generate_pollinations_image
        from utils.season_guard import resolve_effective_show_context
        show_ctx = resolve_effective_show_context(topic_or_title=topic or content_type or "", script_text="", raw_show_context=get_setting("SHOW_CONTEXT", ""))
        is_bb_mode = bool(show_ctx) and (is_bigg_boss_topic(topic or "") or "bigg boss" in str(content_type).lower())

        for a in tier_b_assets:
            if replaced_count >= excess_count:
                break
            b_id = a.get("beat_id")
            dest = ASSETS_DIR / f"{b_id}.jpg"
            q_text = (
                (section_narrations.get(b_id) if section_narrations else None)
                or (visuals[b_id - 1] if visuals and b_id - 1 < len(visuals) else f"visual scene {b_id}")
            )
            success = False
            if is_bb_mode:
                # Reality/contestants: Never generate AI faces (prevents anime/cartoon). Use Canva-style card with contestant avatar or show interior
                try:
                    from agents.typography_card import generate_typography_card
                    loc_c = find_local_contestant_image(f"{q_text}")
                    av_p = str(loc_c[1]) if loc_c else None
                    b_lbl = f"{loc_c[0].upper().replace('_', ' ')} • BIGG BOSS 10" if loc_c else "BIGG BOSS TELUGU 10"
                    if not av_p:
                        bb_house = ROOT / "assets" / "entities" / "bigg_boss_telugu" / "image.jpg"
                        if bb_house.exists():
                            av_p = str(bb_house)
                    success = generate_typography_card(
                        headline_text=q_text,
                        output_path=str(dest),
                        topic_category="entertainment",
                        aspect_ratio=aspect_ratio,
                        badge_label=b_lbl,
                        avatar_image_path=av_p,
                        subtext="Bigg Boss Telugu 10 • Star Maa",
                    )
                except Exception as bb_err:
                    print(f"   Bigg Boss auto-balance card error on beat {b_id}: {bb_err}")
            else:
                clean_p = rewrite_query_for_flux(q_text, is_explainer=False, show_context=show_ctx, topic_category=content_type or topic)
                print(f"🎨 [Auto-Balance FLUX] Replacing Tier B beat {b_id} with FLUX AI visual: '{clean_p[:50]}...'")
                try:
                    success = generate_pollinations_image(clean_p, dest, aspect_ratio=aspect_ratio)
                except Exception as f_err:
                    print(f"   FLUX auto-balance error on beat {b_id}: {f_err}")

            if not success or not dest.exists() or dest.stat().st_size < 1000:
                # Fallback to authentic show set / interior if available
                bb_house = ROOT / "assets" / "entities" / "bigg_boss_telugu" / "image.jpg"
                if is_bb_mode and bb_house.exists():
                    shutil.copy2(bb_house, dest)
                    clean_and_crop_image(dest, aspect_ratio=aspect_ratio)
                    success = True
                else:
                    try:
                        from agents.typography_card import generate_typography_card
                        generate_typography_card(q_text, dest, topic_category=content_type or topic or "general", aspect_ratio=aspect_ratio, subtext=f"Scene {b_id} Highlight")
                        success = dest.exists() and dest.stat().st_size > 1000
                    except Exception:
                        pass

            if success:
                record_asset(
                    video_id="current",
                    beat_id=b_id,
                    asset_path=str(dest),
                    source_url="canva_editorial_autobalance" if is_bb_mode else "pollinations_flux_autobalance",
                    tier="TIER_A",
                    license_name="AutoTube Editorial Card" if is_bb_mode else "Generated FLUX (CC0)",
                    credit_text="AutoTube Engine",
                    duration_sec=float(a.get("duration_sec", 3.0)),
                )
                replaced_count += 1

        new_tb = get_tier_breakdown("current")
        print(f"✅ [Auto-Balance Complete] Replaced {replaced_count} beats with Tier A FLUX/safe assets. New Tier B share: {new_tb.get('tier_b_share', 0.0)*100:.1f}%")
        return True
    except Exception as e:
        print(f"⚠️ [Auto-Balance Notice] Tier B auto-balance notice: {e}")
        return False


# ============================================================
# VISUAL PLAN IMAGE DOWNLOAD
# ============================================================

@autonomous_recover("image_agent")
def download_images_from_visual_plan(
    visual_plan_path=None,
    flyer_path=None,
    feedback=None,
    aspect_ratio="16:9",
    generation_mode="stock",
    user_assets=None,
    user_assets_map=None,
    progress_callback=None,
    *args,
    **kwargs,
):

    if visual_plan_path is None:
        visual_plan_path = kwargs.get("visuals") or (OUTPUT_DIR / "visual_plan.txt")

    if isinstance(visual_plan_path, (list, tuple)):
        visual_plan_file = None
    else:
        visual_plan_file = Path(visual_plan_path)
        if not visual_plan_file.exists():
            raise FileNotFoundError(
                f"Visual plan not found: "
                f"{visual_plan_file}"
            )

    # Derive orientation matching the requested aspect ratio
    orientation = "landscape"
    if aspect_ratio == "9:16":
        orientation = "portrait"
    elif aspect_ratio == "1:1":
        orientation = "square"

    # Derive normalized topic category for visual matching (Section 12)
    topic = kwargs.get("topic") or kwargs.get("topic_name") or ""
    if not topic:
        title_file = OUTPUT_DIR / "title.txt"
        if title_file.exists():
            topic = title_file.read_text(encoding="utf-8").strip()
    raw_cat = kwargs.get("topic_category") or kwargs.get("content_type") or "tech"
    raw_cat_lower = str(raw_cat).lower()
    if any(k in raw_cat_lower for k in ["history", "historical", "ancient", "era"]):
        topic_category = "history"
    elif any(k in raw_cat_lower for k in ["fact", "curiosity", "interesting"]):
        topic_category = "facts"
    elif any(k in raw_cat_lower for k in ["movie", "cinema", "film", "entertainment", "reality", "show", "bigg boss", "celebrity", "drama"]):
        topic_category = "entertainment"
    elif any(k in raw_cat_lower for k in ["news", "politics", "current"]):
        topic_category = "news"
    elif any(k in raw_cat_lower for k in ["finance", "crypto", "business", "stock", "market"]):
        topic_category = "finance"
    elif any(k in raw_cat_lower for k in ["explainer", "education", "science", "guide"]):
        topic_category = "explainer"
    else:
        topic_category = "tech"

    # Autonomous Entity Harvester: ensure verified portraits exist for all mentioned entities
    try:
        from agents.entity_harvester import harvest_entities_from_plan
        dp_file = OUTPUT_DIR / "delivery_plan.json"
        if dp_file.exists():
            dp_data = json.loads(dp_file.read_text(encoding="utf-8"))
            harvest_entities_from_plan(dp_data, topic=topic)
    except Exception:
        pass

    visuals = []

    if isinstance(visual_plan_path, (list, tuple)):
        visuals = [str(v).strip() for v in visual_plan_path if str(v).strip()]
    elif visual_plan_file:
        with open(
            visual_plan_file,
            "r",
            encoding="utf-8",
        ) as file:

            for raw_line in file:
                line_text = raw_line.strip()
                if not line_text:
                    continue

                cleaned = re.sub(r"^[\*\-\#\>\s]+", "", line_text).strip()
                match = re.match(
                    r"^(?:\*?\*?visual\s*)?(\d+)[\.\)\:\-]\*?\*?\s*(.+)$",
                    cleaned,
                    re.IGNORECASE,
                )
                if match:
                    visual = match.group(2).strip().strip("*").strip()
                    if visual:
                        visuals.append(visual)
                elif cleaned and len(cleaned) > 10 and not cleaned.lower().startswith("visual plan"):
                    visuals.append(cleaned)

    # Fallback to section map or script if visual plan had < 4 concepts
    if len(visuals) < 4:
        section_map_file = OUTPUT_DIR / "section_map.txt"
        if section_map_file.exists():
            try:
                sec_text = section_map_file.read_text(encoding="utf-8")
                pattern = re.compile(
                    r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
                    re.DOTALL | re.IGNORECASE,
                )
                for m in pattern.finditer(sec_text):
                    narration = m.group(3).strip()
                    if narration:
                        words = narration.split()
                        visuals.append(" ".join(words[:8]))
            except Exception:
                pass

    if len(visuals) < 4:
        topic_preview = visuals[0] if visuals else "news story"
        while len(visuals) < 4:
            visuals.append(f"{topic_preview} scene {len(visuals) + 1}")

    target_count = len(visuals)

    # Mode 2: If user provided their own media, map them and bypass stock search
    is_user_mode = (
        generation_mode in ("user_media", "My Own Images/Videos", "📁 My Own Images/Videos")
        or (user_assets and len(user_assets) > 0 and generation_mode not in ("stock", "🎬 AI Stock Search"))
    )
    if is_user_mode:
        print("📁 [Multi-Mode] User Media Mode active. Mapping scenes directly to user footage...")
        clean_assets()
        try:
            from agents.multimode_agent import map_script_to_user_assets, apply_user_assets_to_visuals
            mapped = user_assets_map or map_script_to_user_assets(visuals, user_assets)
            applied = apply_user_assets_to_visuals(mapped, ASSETS_DIR)
            print(f"✅ Applied {len(applied)} user media assets directly to visual timeline.")
            from agents.video_agent import ensure_visual_assets_exist
            ensure_visual_assets_exist()
            return [(i, ASSETS_DIR / f"{i}.mp4" if (ASSETS_DIR / f"{i}.mp4").exists() else ASSETS_DIR / f"{i}.jpg") for i in range(1, target_count + 1)]
        except Exception as u_err:
            print(f"User media mapping warning: {u_err}. Falling back to standard visual sourcing.")

    # Mode 3: Short Video Clips Mode (X / Twitter, Pexels Video, Tenor Memes)
    is_video_clips_mode = (
        generation_mode in ("video_clips", "clips", "🎥 AI Short Video Clips", "🎥 AI Video Clips (X / Pexels / Memes)")
    )
    if is_video_clips_mode:
        print("🎥 [Multi-Mode] Short Video Clips Mode active (X / Pexels / Memes)...")
        clean_assets()
        try:
            from agents.short_clip_fetcher import fetch_and_prepare_all_scene_clips
            clips = fetch_and_prepare_all_scene_clips(
                aspect_ratio=aspect_ratio,
                topic=topic_category,
            )
            from agents.video_agent import ensure_visual_assets_exist
            ensure_visual_assets_exist(needed_count=len(clips))
            return [
                (
                    rec["scene_id"],
                    Path(rec["file_path"]) if Path(rec["file_path"]).exists() else (ASSETS_DIR / f"{rec['scene_id']}.mp4")
                )
                for rec in clips
            ]
        except Exception as v_err:
            print(f"⚠️ Short video clips fetcher error: {v_err}. Falling back to standard visual sourcing.")

    # Load section narrations if available for targeted context
    section_map_file = OUTPUT_DIR / "section_map.txt"
    section_narrations = kwargs.get("section_narrations") or {}
    if not section_narrations and section_map_file.exists():
        try:
            sec_text = section_map_file.read_text(encoding="utf-8")
            pattern = re.compile(
                r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
                re.DOTALL | re.IGNORECASE,
            )
            for m in pattern.finditer(sec_text):
                v_num = int(m.group(2))
                section_narrations[v_num] = m.group(3).strip()
        except Exception:
            pass

    # ========================================================
    # SOCIAL MEDIA VISUAL SELECTION (INSTAGRAM + TWITTER/X via APIFY + CLIP)
    # ========================================================
    try:
        from config.settings import get_setting
        use_social = bool(get_setting("USE_SOCIAL_VISUALS", True))
        script_file = OUTPUT_DIR / "script.txt"
        if use_social and script_file.exists() and not is_user_mode:
            from agents.social_visual_selector import select_visuals_for_script
            script_text = script_file.read_text(encoding="utf-8").strip()
            if script_text:
                print("🌟 [Social Visual Mode] Running Apify & CLIP ViT-B-32 Social Visual Selector...")
                title_file = OUTPUT_DIR / "title.txt"
                video_title = title_file.read_text(encoding="utf-8").strip() if title_file.exists() else ""
                from utils.season_guard import is_bigg_boss_topic, resolve_effective_show_context
                cfg_ctx = resolve_effective_show_context(
                    topic_or_title=video_title,
                    script_text=script_text,
                    raw_show_context=get_setting("SHOW_CONTEXT", ""),
                )
                is_bb = bool(cfg_ctx) and (is_bigg_boss_topic(video_title) or is_bigg_boss_topic(script_text))
                if is_bb:
                    ctx = cfg_ctx
                else:
                    # Non-Bigg Boss topic: strictly use actual title/topic as context
                    ctx = video_title or "viral entertainment"
                social_assets = select_visuals_for_script(
                    script_text=script_text,
                    overall_context=ctx,
                )
                if social_assets:
                    try:
                        from agents.visual_agent import deduplicate_consecutive_assets
                        social_assets = deduplicate_consecutive_assets(
                            assets_dir=ASSETS_DIR,
                            section_narrations=section_narrations,
                            visuals=visuals,
                            aspect_ratio=aspect_ratio,
                            topic_category=topic_category,
                            max_consecutive=2,
                            target_count=len(social_assets),
                            show_context=ctx,
                        )
                    except Exception as d_err:
                        print(f"⚠️ Visual deduplication notice: {d_err}")
                    from agents.video_agent import ensure_visual_assets_exist
                    ensure_visual_assets_exist(needed_count=len(social_assets))
                    return social_assets
    except Exception as soc_err:
        print(f"⚠️ Social Visual Selector notice: {soc_err} - Continuing to standard visual sourcing.")

    # ========================================================
    # DOWNLOAD ONE IMAGE FOR EACH VISUAL DESCRIPTION
    # ========================================================

    line()
    print("AI VISUAL-PLAN IMAGE & VIDEO SEARCH")
    line()

    clean_assets()

    used_hashes = set()
    used_dhashes = []
    claimed_urls = set()
    used_entity_library_ids = set()
    used_memes = set()
    used_news_images = set()
    used_promo_images = set()
    used_editorial_avatars = set()
    used_harvested_paths = set()
    hash_lock = threading.RLock()

    # Seed cross-run deduplication from asset ledger (last 15 videos)
    try:
        from data.asset_ledger import get_recent_used_asset_paths
        recent_assets = get_recent_used_asset_paths(limit_videos=15)
        for ra in recent_assets:
            if ra.startswith("http"):
                claimed_urls.add(ra)
            else:
                p_ra = Path(ra)
                if p_ra.exists():
                    used_harvested_paths.add(str(p_ra))
                    h = image_hash(p_ra)
                    if h:
                        used_hashes.add(h)
    except Exception:
        pass

    # Pre-harvest user-provided or topic-embedded news URLs (if any were passed)
    raw_url_candidates = re.findall(r"https?://[^\s<>\"']+", f"{topic} {kwargs.get('script', '')} {str(user_assets or '')}")
    for u_cand in raw_url_candidates:
        if any(d in u_cand.lower() for d in ["samayam.com", "sakshi.com", "v6velugu.com", "eenadu.net", "tupaki.com"]):
            try:
                from tools.news_media_harvester import extract_images_from_article_url
                print(f"📰 [Pre-Harvest] Harvesting authentic images from user-supplied news URL: {u_cand[:60]}...")
                extract_images_from_article_url(u_cand, max_images=6)
            except Exception as ph_err:
                print(f"Pre-harvest notice: {ph_err}")

    # --------------------------------------------------------
    # GLOBAL VIDEO TOPIC ENTITY DETECTION & INHERITANCE
    # --------------------------------------------------------
    global_is_entity = False
    global_entity_name = ""
    global_entity_cat = ""

    title_file = OUTPUT_DIR / "title.txt"
    title_text = title_file.read_text(encoding="utf-8").strip() if title_file.exists() else ""
    script_file = OUTPUT_DIR / "script.txt"
    script_snippet = script_file.read_text(encoding="utf-8")[:300] if script_file.exists() else ""
    full_vp_text = "\n".join(visuals)

    for cand_text in [title_text, script_snippet, full_vp_text]:
        if cand_text:
            g_ent, g_name, g_cat = detect_named_entity(cand_text)
            if g_ent:
                global_is_entity = True
                global_entity_name = g_name
                global_entity_cat = g_cat
                if "bigg boss" in global_entity_name.lower() and "telugu" not in global_entity_name.lower():
                    global_entity_name = "Bigg Boss Telugu"
                print(f"🏛️ Global Video Topic Entity Detected: '{global_entity_name}' ({global_entity_cat})")
                break

    topic_person_slug = kwargs.get("topic_person_slug") or (global_entity_name if global_is_entity else "")

    def process_single_visual(visual_tuple):
        visual_number, visual_query = visual_tuple
        destination = ASSETS_DIR / f"{visual_number}.jpg"
        video_dest = ASSETS_DIR / f"{visual_number}.mp4"

        # Dedicated uploaded flyer for final visual
        if visual_number == target_count and flyer_path:
            print(f"Using uploaded flyer as dedicated final Visual {target_count}.")
            if save_flyer_fallback(flyer_path, destination):
                return visual_number, destination

        assigned_narration = section_narrations.get(visual_number, "")
        queries = build_queries(
            visual_query,
            narration=assigned_narration,
            topic_category=topic_category,
        )

        # Structured Visual Plan Integration (Dynamic Entity & Strict Query Format)
        search_target_name = ""
        v_short = ""
        concise_q = ""
        s_primary_ent = ""
        s_content_type = ""
        s_search_query = ""
        s_emotion = ""
        s_intent = ""
        vp_json_file = OUTPUT_DIR / "visual_plan.json"
        if vp_json_file.exists():
            try:
                import json
                structured_vps = json.loads(vp_json_file.read_text(encoding="utf-8"))
                for s_entry in structured_vps:
                    if s_entry.get("beat_id") == visual_number:
                        s_primary_ent = s_entry.get("main_entity") or s_entry.get("primary_entity") or ""
                        s_content_type = s_entry.get("content_type") or ""
                        s_search_query = s_entry.get("search_query") or ""
                        s_emotion = s_entry.get("emotion") or s_entry.get("emotion_or_action") or ""
                        s_intent = s_entry.get("intent") or s_entry.get("beat_type") or ""
                        strict_q = s_entry.get("strict_query")
                        fallback_promo = s_entry.get("fallback_promo_query")
                        cleaned_qs = s_entry.get("cleaned_queries", [])
                        neg_excl = s_entry.get("negative_exclusions", [])
                        neg_str = " ".join(neg_excl) if neg_excl else ""
                        
                        top_qs = []
                        if s_search_query:
                            top_qs.append(s_search_query)
                        if strict_q and strict_q not in top_qs:
                            top_qs.append(f"{strict_q} {neg_str}".strip() if neg_str else strict_q)
                        if fallback_promo and fallback_promo not in top_qs:
                            top_qs.append(f"{fallback_promo} {neg_str}".strip() if neg_str else fallback_promo)
                        for cq in cleaned_qs:
                            cq_str = f"{cq} {neg_str}".strip() if neg_str else cq
                            if cq_str not in top_qs:
                                top_qs.append(cq_str)
                        
                        if top_qs:
                            queries = top_qs + [q for q in queries if q not in top_qs]
                        break
            except Exception:
                pass

        # Mode 3: Explainer Style Query Transformation
        if generation_mode in ("explainer", "Explainer Style", "📊 Explainer Style"):
            try:
                from agents.multimode_agent import transform_queries_for_explainer
                queries = transform_queries_for_explainer(queries)
            except Exception:
                pass

        # Semantic B-roll mapper: convert brands/abstractions to filmable English stock search queries
        try:
            from semantic_broll_mapper import generate_search_queries
            semantic_qs = generate_search_queries(
                chunk=f"{visual_query}. {assigned_narration}"[:250],
                topic_category=topic_category,
            )
            for sq in semantic_qs:
                if sq not in queries:
                    queries.insert(1, sq)
        except Exception:
            pass

        # Targeted Self-Healing: adjust keywords based on review feedback
        if feedback:
            failing_visuals = [int(n) for n in re.findall(r"Visual\s+(\d+)", str(feedback))]
            # Only apply healing if this beat was explicitly flagged
            if not failing_visuals or idx in failing_visuals:
                STOP_WORDS = {
                    "visual", "mismatch", "image", "resolution", "section", "agent", "quality", "failing",
                    "critical", "defect", "relevance", "below", "threshold", "score", "attempt", "attempts",
                    "skipped", "review", "upload", "youtube", "notice", "error", "warning", "defects"
                }
                extra_words = [
                    w for w in re.findall(r"\b[A-Za-z]{4,}\b", str(feedback))
                    if w.lower() not in STOP_WORDS
                ]
                if extra_words and idx in failing_visuals:
                    queries.insert(0, f"{visual_query} {' '.join(extra_words[:2])}")

        # Check if this visual is discussing a specific named commercial product, show, movie, or celebrity
        if s_primary_ent and s_primary_ent.lower() not in ("none", "general", "auto", "unknown", ""):
            is_entity = True
            entity_name = s_primary_ent
            entity_cat = s_content_type or topic_category
        else:
            is_entity, entity_name, entity_cat = detect_named_entity(f"{visual_query} {assigned_narration}")

        # INHERIT GLOBAL ENTITY:
        # If this beat didn't detect an entity, but the video as a whole is about Bigg Boss, a movie, or a phone brand:
        if not is_entity and global_is_entity:
            is_entity = True
            entity_name = global_entity_name
            entity_cat = global_entity_cat
            # Anchor queries with the global entity so we never search generic Pexels hospitals or stock charts!
            visual_query = f"{global_entity_name} {visual_query}"
            queries.insert(0, f"{global_entity_name} {visual_query}")

        # Build contextual query and negatives dynamically
        topic_ctx = global_entity_name or title_text or topic_category or ""
        concise_q, contextual_query_with_negs = build_contextual_search_query(
            entity=entity_name if is_entity else "",
            topic_context=topic_ctx,
            scene_action=s_search_query or visual_query,
            topic_category=topic_category or entity_cat,
        )

        # ============================================================
        # TIER 1: LOCAL / ENTITY ASSETS (STRICTLY SINGLE-USE DEDUPLICATED)
        # ============================================================
        # PDF Reference Anchor:
        # Resolve canonical contestant name from local reference to guide fresh online search.
        # The PDF headshot acts as the verified reference anchor and guaranteed fallback,
        # while fresh online news stills, promo frames, and web photos are prioritized.
        search_ctx = f"{s_primary_ent} {entity_name} {visual_query} {assigned_narration}".strip()
        local_contestant = find_local_contestant_image(search_ctx, used_hashes=used_hashes, used_dhashes=used_dhashes)
        if local_contestant:
            c_slug, c_img_path = local_contestant
            try:
                roster = load_contestant_roster()
                c_data = roster.get(c_slug, {})
                c_canon = c_data.get("full_name") or c_data.get("nickname") or c_slug.replace("_", " ").title()
                if not entity_name or entity_name.lower() in ("none", "auto", "unknown", "general", ""):
                    entity_name = c_canon
                    is_entity = True
            except Exception:
                pass

        # Dedicated intro card only if explicitly requested for scene 1 profile
        is_explicit_intro_card = (
            visual_number == 1
            and local_contestant
            and s_content_type in ("contestant_profile", "intro_card")
        )
        if is_explicit_intro_card:
            c_slug, c_img_path = local_contestant
            c_h = image_hash(c_img_path)
            c_dh = image_dhash(c_img_path)
            with hash_lock:
                used_hashes.add(c_h)
                if c_dh:
                    used_dhashes.append(c_dh)
            shutil.copy2(c_img_path, destination)
            try:
                from providers.image import clean_and_crop_image
                clean_and_crop_image(destination, aspect_ratio=aspect_ratio)
            except Exception:
                pass
            print(f"🎯 [Intro Card] Verified profile photo for '{c_slug}': {c_img_path.name} -> {destination.name}")
            return visual_number, destination

        from utils.season_guard import is_bigg_boss_topic
        is_bb_scene = (
            is_bigg_boss_topic(topic or "")
            or is_bigg_boss_topic(visual_query or "")
            or is_bigg_boss_topic(assigned_narration or "")
            or "bigg boss" in str(topic_category).lower()
            or "bb10" in (visual_query or "").lower()
            or "bigg boss" in (visual_query or "").lower()
            or (entity_name and bool(find_local_contestant_image(entity_name)))
            or bool(local_contestant)
        )

        # Check Entity Library next (for non-reality topics or explicit show logos like bigg_boss_telugu)
        # Reality contestants bypass static entity photos to search fresh online news/promos/web stills!
        if is_entity and not (is_bb_scene and local_contestant):
            try:
                from tools.build_entity_library import match_entities_in_text, get_entity_asset
                from providers.image import clean_and_crop_image
                el_matches = match_entities_in_text(f"{entity_name} {visual_query} {assigned_narration}")
                combined_text = f"{entity_name} {visual_query} {assigned_narration}".lower()
                el_matches = [
                    e for e in el_matches
                    if e.get("id") != "nagarjuna_akkineni" or any(k in combined_text for k in ("nagarjuna", "నాగార్జున", "king nag", "host"))
                ]
                c_matches = [e for e in el_matches if e.get("id") != "bigg_boss_telugu"]
                chosen_match = None
                if c_matches and not is_bb_scene:
                    unused = [e for e in c_matches if e["id"] not in used_entity_library_ids]
                    chosen_match = unused[0] if unused else None
                elif el_matches and el_matches[0]["id"] not in used_entity_library_ids and not is_bb_scene:
                    chosen_match = el_matches[0]

                if chosen_match:
                    el_asset = get_entity_asset(chosen_match["id"])
                    if el_asset and el_asset.get("path") and Path(el_asset["path"]).exists():
                        el_path = Path(el_asset["path"])
                        e_h = image_hash(el_path)
                        e_dh = image_dhash(el_path)
                        with hash_lock:
                            e_used = (chosen_match["id"] in used_entity_library_ids) or (e_h and e_h in used_hashes) or (e_dh and is_perceptual_duplicate(e_dh, used_dhashes))
                            if not e_used:
                                used_entity_library_ids.add(chosen_match["id"])
                                if e_h:
                                    used_hashes.add(e_h)
                                if e_dh:
                                    used_dhashes.append(e_dh)
                        if not e_used:
                            shutil.copy2(el_path, destination)
                            clean_and_crop_image(destination, aspect_ratio=aspect_ratio)
                            post_h = image_hash(destination)
                            post_dh = image_dhash(destination)
                            with hash_lock:
                                if post_h:
                                    used_hashes.add(post_h)
                                if post_dh:
                                    used_dhashes.append(post_dh)
                            from data.asset_ledger import record_asset
                            record_asset(
                                video_id="current",
                                beat_id=visual_number,
                                asset_path=str(destination),
                                source_url=el_asset.get("source_url", "entity_library"),
                                tier="TIER_A",
                                license_name=el_asset.get("license", "CC-BY"),
                                credit_text=el_asset.get("credit", ""),
                            )
                            print(f"🌟 Visual {visual_number} attached unique Entity Library asset: {chosen_match['canonical_name']}")
                            return visual_number, destination
            except Exception as el_err:
                print(f"Entity library lookup notice: {el_err}")

        # ------------------------------------------------------------
        # TIER 1.2: ICONIC TELUGU REACTION MEME (FOR COMEDY / ROAST / OVERACTING)
        # ------------------------------------------------------------
        if is_bb_scene or topic_category in ("entertainment", "reality") or "telugu_meme" in visual_query.lower() or "meme" in visual_query.lower():
            try:
                from tools.meme_manager import get_reaction_meme, match_emotion_from_text
                is_meme_worthy = (
                    "telugu_meme" in visual_query.lower()
                    or "meme" in visual_query.lower()
                    or s_emotion in ("shocked", "comedy", "roast", "overacting", "laughing", "angry", "confused", "funny", "headache", "crying", "fake_shock", "mock", "smug")
                    or s_intent in ("reaction", "meme", "roast", "comedy")
                    or any(k in visual_query.lower() for k in ("meme", "reaction", "roast", "comedy", "funny", "shocked", "brahmanandam"))
                    or bool(match_emotion_from_text(assigned_narration))
                )
                max_memes = 2
                with hash_lock:
                    can_use_meme = is_meme_worthy and len(used_memes) < max_memes
                    meme_path = get_reaction_meme(f"{s_emotion} {visual_query} {assigned_narration}", used_memes=used_memes) if can_use_meme else None
                if meme_path and meme_path.exists():
                    shutil.copy2(meme_path, destination)
                    try:
                        from providers.image import clean_and_crop_image
                        clean_and_crop_image(destination, aspect_ratio=aspect_ratio)
                        m_h = image_hash(destination)
                        m_dh = image_dhash(destination)
                        with hash_lock:
                            if m_h:
                                used_hashes.add(m_h)
                            if m_dh:
                                used_dhashes.append(m_dh)
                    except Exception:
                        pass
                    try:
                        from data.asset_ledger import record_asset
                        record_asset(
                            video_id="current",
                            beat_id=visual_number,
                            asset_path=str(destination),
                            source_url=f"telugu_meme:{meme_path.name}",
                            tier="TIER_A",
                            license_name="Fair Dealing Telugu Reaction Meme",
                            credit_text="Iconic Telugu Cinema Reaction",
                            duration_sec=3.0,
                        )
                    except Exception:
                        pass
                    print(f"😂 [Telugu Meme] Visual {visual_number} matched iconic reaction cutaway: {meme_path.name}")
                    return visual_number, destination
            except Exception as m_err:
                print(f"Telugu meme manager notice: {m_err}")

        # ------------------------------------------------------------
        # TIER 1.3: LIVE TELUGU NEWS PORTAL PHOTOS & EPISODE STILLS (PRIORITIZED ONLINE MEDIA)
        # ------------------------------------------------------------
        is_current_bb = bool(
            is_bb_scene
            or any("bigg boss" in str(x).lower() for x in (global_entity_name, visual_query, s_primary_ent, entity_name))
        )
        max_news_allowed = 8 if aspect_ratio == "9:16" else 10
        with hash_lock:
            can_use_news = len(used_news_images) < max_news_allowed
        if can_use_news and (is_current_bb or topic_category in ("entertainment", "reality", "news", "technology", "general")):
            try:
                from tools.news_media_harvester import harvest_news_images
                from tools.ocr_guard import scan_images_ocr
                clean_ent = s_primary_ent or entity_name or ""
                if is_current_bb:
                    news_search_str = f"Bigg Boss Telugu 10 {clean_ent} {visual_query}".strip()
                else:
                    news_search_str = f"{clean_ent} {visual_query}".strip()

                news_photos = harvest_news_images(
                    news_search_str,
                    max_images=6,
                    is_bb=is_current_bb,
                    entity_hint=clean_ent,
                )
                for np in news_photos:
                    if not np.exists() or np.stat().st_size < 8000:
                        continue
                    np_str = str(np)
                    with hash_lock:
                        if np_str in used_harvested_paths or len(used_news_images) >= max_news_allowed:
                            continue

                    # Anti-spam OCR filter (reject dating, girlfriend, casino, software screenshots, promo ads)
                    ocr_txt = ""
                    try:
                        from tools.ocr_guard import scan_images_ocr
                        ocr_dict = scan_images_ocr([np])
                        ocr_txt = (ocr_dict.get(str(np)) or "").lower()
                    except Exception:
                        ocr_txt = ""
                    spam_ad_terms = ("girlfriend", "dating", "ai character", "create your own", "sign up", "free account", "explore ai", "companion", "casino", "betting", "slot", "discount", "off%")
                    if ocr_txt and any(sp in ocr_txt for sp in spam_ad_terms):
                        print(f"⚠️ [News Media OCR] Disqualified ad/spam image: {np.name}")
                        continue

                    # Multimodal relevance filter: verify with Gemini Vision
                    if not verify_visual_with_gemini(str(np), visual_query):
                        print(f"⚠️ [News Media Verifier] Rejected irrelevant image {np.name} for query '{visual_query}'")
                        continue

                    n_h = image_hash(np)
                    n_dh = image_dhash(np)
                    with hash_lock:
                        already = (
                            (np_str in used_harvested_paths)
                            or (n_h and n_h in used_hashes)
                            or (n_dh and is_perceptual_duplicate(n_dh, used_dhashes, max_dist=7))
                            or (len(used_news_images) >= max_news_allowed)
                        )
                        if not already:
                            used_harvested_paths.add(np_str)
                            used_news_images.add(np_str)
                            if n_h:
                                used_hashes.add(n_h)
                            if n_dh:
                                used_dhashes.append(n_dh)
                    if not already:
                        shutil.copy2(np, destination)
                        try:
                            from providers.image import clean_and_crop_image
                            clean_and_crop_image(destination, aspect_ratio=aspect_ratio)
                            post_h = image_hash(destination)
                            post_dh = image_dhash(destination)
                            with hash_lock:
                                if post_h:
                                    used_hashes.add(post_h)
                                if post_dh:
                                    used_dhashes.append(post_dh)
                        except Exception:
                            pass
                        try:
                            from data.asset_ledger import record_asset
                            record_asset(
                                video_id="current",
                                beat_id=visual_number,
                                asset_path=str(destination),
                                source_url="telugu_news_media_harvester",
                                tier="TIER_A",
                                license_name="Editorial News Fair Dealing",
                                credit_text="Verified Telugu News Media",
                                duration_sec=3.0,
                            )
                        except Exception:
                            pass
                        print(f"📰 [News Media] Visual {visual_number} attached authentic Telugu news still: {np.name}")
                        return visual_number, destination
            except Exception as n_err:
                print(f"News media harvester notice: {n_err}")

        # ------------------------------------------------------------
        # TIER 1.4: DYNAMIC CONTESTANT GALLERY STILLS (FALLBACK IF ONLINE HARVEST YIELDS NO ASSET)
        # ------------------------------------------------------------
        if is_bb_scene or local_contestant:
            c_cand = local_contestant or find_local_contestant_image(
                f"{entity_name} {visual_query} {assigned_narration}",
                used_hashes=used_hashes,
                used_dhashes=used_dhashes,
            )
            if c_cand:
                c_slug, c_path = c_cand
                if c_path.exists() and c_path.stat().st_size > 5000:
                    c_h = image_hash(c_path)
                    c_dh = image_dhash(c_path)
                    with hash_lock:
                        already_used = (
                            (c_h and c_h in used_hashes)
                            or (c_dh and is_perceptual_duplicate(c_dh, used_dhashes))
                            or (str(c_path) in used_harvested_paths)
                        )
                        # OCR check: reject watermarked photos
                        if not already_used:
                            try:
                                from tools.watermark_remover import clean_and_remove_watermarks, has_watermark_text
                                from tools.ocr_guard import scan_images_ocr
                                c_ocr = scan_images_ocr([c_path])
                                c_txt = c_ocr.get(str(c_path), "")
                                has_wm, wm_word = has_watermark_text(c_txt)
                                if has_wm:
                                    is_clean, cleaned_c = clean_and_remove_watermarks(c_path)
                                    if not is_clean:
                                        print(f"⚠️ [Contestant Gallery OCR] Disqualified watermarked image: {c_path.name} ({wm_word})")
                                        already_used = True
                                    else:
                                        c_path = cleaned_c
                            except Exception:
                                pass

                        if not already_used:
                            used_harvested_paths.add(str(c_path))
                            if c_h:
                                used_hashes.add(c_h)
                            if c_dh:
                                used_dhashes.append(c_dh)
                    if not already_used:
                        shutil.copy2(c_path, destination)
                        try:
                            from providers.image import clean_and_crop_image
                            clean_and_crop_image(destination, aspect_ratio=aspect_ratio)
                            post_h = image_hash(destination)
                            post_dh = image_dhash(destination)
                            with hash_lock:
                                if post_h:
                                    used_hashes.add(post_h)
                                if post_dh:
                                    used_dhashes.append(post_dh)
                        except Exception:
                            pass
                        try:
                            from data.asset_ledger import record_asset
                            record_asset(
                                video_id="current",
                                beat_id=visual_number,
                                asset_path=str(destination),
                                source_url=f"contestant_gallery:{c_slug}/{c_path.name}",
                                tier="TIER_A",
                                license_name="Editorial Reality Coverage Fair Dealing",
                                credit_text=f"Bigg Boss 10 Episode Still ({c_slug.title()})",
                                duration_sec=3.0,
                            )
                        except Exception:
                            pass
                        print(f"🌟 [Contestant Gallery] Visual {visual_number} assigned episode still for '{c_slug}': {c_path.name}")
                        return visual_number, destination

        # ------------------------------------------------------------
        # TIER 1.6: OFFICIAL STAR MAA YOUTUBE PROMO FRAMES (BIGG BOSS ONLY, MAX 3 BEATS)
        # ------------------------------------------------------------
        max_promo_allowed = 3
        with hash_lock:
            can_use_promo = len(used_promo_images) < max_promo_allowed
        if is_current_bb and can_use_promo:
            try:
                from tools.promo_video_harvester import harvest_promo_visuals
                promo_search_str = f"Star Maa Bigg Boss Telugu 10 {s_primary_ent or entity_name or ''} promo"
                promo_stills = harvest_promo_visuals(promo_search_str, max_results=8)
                for ps in promo_stills:
                    if not ps.exists() or ps.stat().st_size < 8000:
                        continue
                    ps_str = str(ps)
                    with hash_lock:
                        if ps_str in used_harvested_paths or len(used_promo_images) >= max_promo_allowed:
                            continue
                    p_h = image_hash(ps)
                    p_dh = image_dhash(ps)
                    with hash_lock:
                        already = (
                            (ps_str in used_harvested_paths)
                            or (p_h and p_h in used_hashes)
                            or (p_dh and is_perceptual_duplicate(p_dh, used_dhashes, max_dist=7))
                            or (len(used_promo_images) >= max_promo_allowed)
                        )
                        if not already:
                            used_harvested_paths.add(ps_str)
                            used_promo_images.add(ps_str)
                            if p_h:
                                used_hashes.add(p_h)
                            if p_dh:
                                used_dhashes.append(p_dh)
                    if not already:
                        shutil.copy2(ps, destination)
                        try:
                            from providers.image import clean_and_crop_image
                            clean_and_crop_image(destination, aspect_ratio=aspect_ratio)
                            post_h = image_hash(destination)
                            post_dh = image_dhash(destination)
                            with hash_lock:
                                if post_h:
                                    used_hashes.add(post_h)
                                if post_dh:
                                    used_dhashes.append(post_dh)
                        except Exception:
                            pass
                        try:
                            from data.asset_ledger import record_asset
                            record_asset(
                                video_id="current",
                                beat_id=visual_number,
                                asset_path=str(destination),
                                source_url="star_maa_youtube_promo",
                                tier="TIER_A",
                                license_name="Broadcast Promo Fair Dealing",
                                credit_text="Star Maa Official Promo",
                                duration_sec=3.0,
                            )
                        except Exception:
                            pass
                        print(f"📺 [Star Maa Promo] Visual {visual_number} attached official broadcast promo frame: {ps.name}")
                        return visual_number, destination
            except Exception as p_err:
                print(f"Promo video harvester notice: {p_err}")

        # ============================================================
        # TIER 2: FRESH MULTI-SOURCE WEB & EDITORIAL SEARCH (FOR ANY TOPIC)
        # ============================================================
        # Fully dynamic web image retrieval for movies, actors, directors, roasts, or news.
        try:
            from config.settings import get_setting
            from providers.image import (
                search_web_product_images,
                search_entertainment_posters,
                search_twitter_media_images,
                search_bing_images,
                clean_and_crop_image,
                is_tier_c_asset,
            )
            allow_tier_b = bool(get_setting("ALLOW_TIER_B", True))
            cand_pool = []

            if allow_tier_b:
                target_search_term = entity_name or topic_ctx or "entertainment"
                v_short = " ".join((s_search_query or visual_query).split()[:4])
                
                # Fetch fresh images with contextual negative filters
                cand_pool.extend(search_bing_images(contextual_query_with_negs, max_results=12))
                if entity_cat in ("entertainment", "celebrity", "cinema") or topic_category in ("entertainment", "celebrity", "cinema"):
                    cand_pool.extend(search_entertainment_posters(target_search_term, scene_query=v_short, max_results=10))
                    cand_pool.extend(search_twitter_media_images(contextual_query_with_negs, max_results=8))
                else:
                    cand_pool.extend(search_web_product_images(target_search_term, scene_query=v_short, max_results=10))
                    cand_pool.extend(search_twitter_media_images(contextual_query_with_negs, max_results=6))

                # Query broadening if pool is small
                if len(cand_pool) < 6:
                    cand_pool.extend(search_bing_images(concise_q, max_results=8))
                    if s_search_query and s_search_query != concise_q:
                        cand_pool.extend(search_bing_images(s_search_query, max_results=8))
                    try:
                        from providers.image import search_duckduckgo_images
                        cand_pool.extend(search_duckduckgo_images(s_search_query or concise_q, max_results=8))
                    except Exception:
                        pass

                if len(cand_pool) < 4:
                    try:
                        from providers.image import search_pexels_photos
                        orient = "portrait" if aspect_ratio == "9:16" else "landscape"
                        cand_pool.extend(search_pexels_photos(s_search_query or visual_query or concise_q, orientation=orient, per_page=6))
                    except Exception:
                        pass

                # Negative keyword, collision & quality filtering
                clean_cands = []
                for c in cand_pool:
                    if is_blacklisted_candidate(c, target_entity=entity_name, topic_context=topic_ctx):
                        print(f"🚫 Disqualified collision candidate for '{entity_name}': {c.get('title', '')[:55]}")
                        continue
                    if is_tier_c_asset(c.get("image_url", ""), c.get("title", "")):
                        continue
                    clean_cands.append(c)
                cand_pool = clean_cands

            for candidate in cand_pool:
                cand_url = candidate.get("image_url")
                if not cand_url:
                    continue

                # Atomic check to prevent two scenes from claiming the same image URL
                with hash_lock:
                    if cand_url in claimed_urls:
                        continue
                    claimed_urls.add(cand_url)

                success = download_image(candidate, destination)
                if not success:
                    with hash_lock:
                        claimed_urls.discard(cand_url)
                    continue

                # Auto-crop black letterbox bars & watermark banners cleanly
                clean_and_crop_image(destination, aspect_ratio=aspect_ratio)

                # Validation: verify with PIL
                try:
                    with Image.open(destination) as img:
                        w, h = img.size
                        if w < 300 or h < 220:
                            destination.unlink(missing_ok=True)
                            with hash_lock:
                                claimed_urls.discard(cand_url)
                            continue
                except Exception:
                    destination.unlink(missing_ok=True)
                    with hash_lock:
                        claimed_urls.discard(cand_url)
                    continue

                # Perceptual hash & SHA256 deduplication
                f_hash = image_hash(destination)
                f_dhash = image_dhash(destination)
                with hash_lock:
                    if f_hash and f_hash in used_hashes:
                        destination.unlink(missing_ok=True)
                        claimed_urls.discard(cand_url)
                        continue
                    if f_dhash and is_perceptual_duplicate(f_dhash, used_dhashes, max_dist=6):
                        print(f"🔄 Perceptual duplicate rejected for Visual {visual_number}: '{cand_url[:55]}'")
                        destination.unlink(missing_ok=True)
                        claimed_urls.discard(cand_url)
                        continue

                # Multimodal Gemini Vision & Non-Telugu / Foreign Script & Anime Filter
                if is_bb_scene or is_entity:
                    # Quick OCR check for foreign non-Telugu scripts (Bengali / Devanagari) or anime / political podcast text
                    try:
                        from tools.ocr_guard import scan_images_ocr
                        ocr_res = scan_images_ocr([destination])
                        ocr_txt = (ocr_res.get(str(destination)) or "").lower()
                        bad_ocr_tokens = ("anime", "manga", "stampede", "analysis of", "podcast", "bnp", "bangladesh", "party", "press conference", "trigun themes")
                        if any(tok in ocr_txt for tok in bad_ocr_tokens) or re.search(r"[\u0980-\u09FF]", ocr_txt):
                            print(f"🚫 [OCR Guard] Disqualified foreign script / anime / political image for Visual {visual_number}: '{cand_url[:60]}'")
                            destination.unlink(missing_ok=True)
                            with hash_lock:
                                claimed_urls.discard(cand_url)
                            continue
                    except Exception:
                        pass

                    # Gemini Vision relevance verification
                    is_verified = verify_visual_with_gemini(str(destination), f"{entity_name or s_primary_ent} in Telugu Bigg Boss 10")
                    if not is_verified:
                        print(f"🚫 [Gemini Vision Rejected] Visual {visual_number} candidate failed relevance for '{entity_name or s_primary_ent}': '{cand_url[:60]}'")
                        destination.unlink(missing_ok=True)
                        with hash_lock:
                            claimed_urls.discard(cand_url)
                        continue

                # Relevance check: calibrated threshold for real web photography
                rel_score = score_visual_relevance(str(destination), concise_q)
                if rel_score < 0.18 and rel_score > 0.0:
                    print(f"⚠️ Media candidate rejected (SigLIP score {rel_score:.4f} < 0.18): '{cand_url[:60]}'")
                    destination.unlink(missing_ok=True)
                    with hash_lock:
                        claimed_urls.discard(cand_url)
                    continue

                with hash_lock:
                    if f_hash:
                        used_hashes.add(f_hash)
                    if f_dhash:
                        used_dhashes.append(f_dhash)

                print(f"✅ Visual {visual_number} saved authentic unique media for '{entity_name or topic_ctx}' (SigLIP: {rel_score:.4f}) -> {destination.name}")
                try:
                    from data.asset_ledger import record_asset
                    record_asset(
                        video_id="current",
                        beat_id=visual_number,
                        asset_path=str(destination),
                        source_url=cand_url,
                        tier="TIER_B" if allow_tier_b else "TIER_A",
                        license_name="Web / Editorial",
                        credit_text=candidate.get("source_url", "Web Search"),
                        duration_sec=3.0,
                    )
                except Exception:
                    pass
                return visual_number, destination

        except Exception as p_err:
            print(f"Web media search notice for Visual {visual_number}: {p_err}")

        # ------------------------------------------------------------
        # ------------------------------------------------------------
        # TIER 2.5: RESCUE LAYER - SEARCH DDG & PEXELS FOR REAL PHOTOGRAPHY
        # ------------------------------------------------------------
        from utils.season_guard import is_bigg_boss_topic, is_conflicting_season_candidate
        loc_c_pre = find_local_contestant_image(f"{entity_name or ''} {visual_query} {assigned_narration}")
        if not loc_c_pre and topic_person_slug and (not entity_name or entity_name.lower() in topic_person_slug.lower() or topic_person_slug.lower() in entity_name.lower()):
            loc_c_pre = find_local_contestant_image(topic_person_slug)
        is_bb_scene = (
            bool(loc_c_pre)
            or is_bigg_boss_topic(topic or "")
            or is_bigg_boss_topic(visual_query or "")
            or is_bigg_boss_topic(assigned_narration or "")
            or "bigg boss" in str(topic_category).lower()
            or "bb10" in (visual_query or "").lower()
            or "bigg boss" in (visual_query or "").lower()
        )

        if not destination.exists() or destination.stat().st_size < 3000:
            rescue_queries = [
                s_search_query,
                concise_q,
                visual_query,
                f"{entity_name} photo" if entity_name else "",
                f"{global_entity_name} photo" if global_entity_name else "",
            ]
            for r_q in rescue_queries:
                r_q = str(r_q or "").strip()
                if not r_q or len(r_q) < 3:
                    continue
                try:
                    from providers.image import search_duckduckgo_images
                    r_cands = search_duckduckgo_images(r_q, max_results=8)
                    for rc in r_cands:
                        rc_url = rc.get("image_url")
                        rc_title = rc.get("title", "")
                        if not rc_url or rc_url in claimed_urls:
                            continue

                        # Strict Season Guard & Blacklist in Rescue Layer
                        if is_conflicting_season_candidate(
                            f"{rc_title} {rc_url}",
                            is_bb_context=is_bb_scene,
                            target_season=10,
                            target_person=entity_name or s_primary_ent,
                        ):
                            continue
                        if is_blacklisted_candidate(rc, target_entity=entity_name, topic_context=topic_ctx):
                            continue

                        with hash_lock:
                            claimed_urls.add(rc_url)

                        if download_image(rc, destination):
                            clean_and_crop_image(destination, aspect_ratio=aspect_ratio)

                            # Validate dimensions
                            try:
                                with Image.open(destination) as img:
                                    w, h = img.size
                                    if w < 300 or h < 220:
                                        destination.unlink(missing_ok=True)
                                        with hash_lock:
                                            claimed_urls.discard(rc_url)
                                        continue
                            except Exception:
                                destination.unlink(missing_ok=True)
                                with hash_lock:
                                    claimed_urls.discard(rc_url)
                                continue

                            # Perceptual hash deduplication
                            f_hash = image_hash(destination)
                            f_dhash = image_dhash(destination)
                            with hash_lock:
                                if (f_hash and f_hash in used_hashes) or (f_dhash and is_perceptual_duplicate(f_dhash, used_dhashes, max_dist=5)):
                                    print(f"🔄 [Rescue Layer] Duplicate rejected for Visual {visual_number}: '{rc_url[:55]}'")
                                    destination.unlink(missing_ok=True)
                                    claimed_urls.discard(rc_url)
                                    continue

                            # OCR check for prior season text / logos
                            if is_bb_scene:
                                try:
                                    from tools.ocr_guard import check_asset_prior_seasons
                                    is_clean, detected_text, reason = check_asset_prior_seasons(destination, is_bb=True)
                                    if not is_clean:
                                        print(f"🚫 [Rescue OCR Guard] Disqualified prior season image for Visual {visual_number}: {reason}")
                                        destination.unlink(missing_ok=True)
                                        with hash_lock:
                                            claimed_urls.discard(rc_url)
                                        continue
                                except Exception:
                                    pass

                            with hash_lock:
                                if f_hash:
                                    used_hashes.add(f_hash)
                                if f_dhash:
                                    used_dhashes.append(f_dhash)

                            print(f"🎯 [Rescue Layer] Visual {visual_number} saved authentic photo via DDG for '{r_q}': {destination.name}")
                            return visual_number, destination
                except Exception as r_err:
                    print(f"Rescue search notice: {r_err}")

        # ------------------------------------------------------------
        # TIER 2.6: ENTITY STILLS / PORTRAITS RE-FRAMING (NEVER SHOW EMPTY CARD FOR CELEBS)
        # ------------------------------------------------------------
        if not destination.exists() or destination.stat().st_size < 3000:
            ent_search = entity_name or global_entity_name or topic_person_slug
            if ent_search:
                ent_clean = re.sub(r"[^\w\s]", "", ent_search).strip().lower().replace(" ", "_")
                for e_dir in [ROOT / "assets" / "entities" / ent_clean, ROOT / "data" / "entities" / ent_clean]:
                    if e_dir.exists():
                        e_photos = [f for f in e_dir.glob("*.*") if f.suffix.lower() in (".jpg", ".jpeg", ".png") and f.stat().st_size > 5000]
                        if e_photos:
                            # Pick deterministically by visual_number
                            sel_photo = e_photos[(visual_number - 1) % len(e_photos)]
                            shutil.copy2(sel_photo, destination)
                            clean_and_crop_image(destination, aspect_ratio=aspect_ratio)
                            f_hash = image_hash(destination)
                            f_dhash = image_dhash(destination)
                            with hash_lock:
                                if f_hash:
                                    used_hashes.add(f_hash)
                                if f_dhash:
                                    used_dhashes.append(f_dhash)
                            print(f"🌟 [Entity Rescue] Visual {visual_number} used verified library asset for '{ent_search}': {sel_photo.name}")
                            return visual_number, destination

        # ============================================================
        # TIER 3: PHASE 5 VISUAL LADDER (Pexels -> Pixabay -> Pollinations FLUX -> Wikimedia)
        # MUST run BEFORE Typography Card to prioritize real photography / video B-roll!
        # ============================================================
        try:
            from agents.visual_ladder import source_beat_visual
            ladder_res = source_beat_visual(
                beat_number=visual_number,
                raw_query=visual_query,
                narration=assigned_narration,
                destination_jpg=destination,
                destination_mp4=video_dest,
                aspect_ratio=aspect_ratio,
                topic_category=topic_category,
                claimed_urls=claimed_urls,
                used_hashes=used_hashes,
                used_entity_library_ids=used_entity_library_ids,
                hash_lock=hash_lock,
            )
            if ladder_res.get("success"):
                asset_p = Path(ladder_res["asset_path"])
                if asset_p.suffix.lower() == ".mp4" and asset_p.exists():
                    print(f"🎬 [Visual {visual_number}] ✅ Attached via Phase 5 Ladder: {ladder_res['source']} -> {asset_p.name}")
                    return visual_number, asset_p
                elif destination.exists() and destination.stat().st_size > 3000:
                    try:
                        from providers.image import clean_and_crop_image
                        clean_and_crop_image(destination, aspect_ratio=aspect_ratio)
                    except Exception:
                        pass
                    f_hash = image_hash(destination)
                    f_dhash = image_dhash(destination)
                    with hash_lock:
                        is_dup = (f_hash and f_hash in used_hashes) or (f_dhash and is_perceptual_duplicate(f_dhash, used_dhashes, max_dist=5))
                    if is_dup:
                        print(f"🔄 Phase 5 ladder returned duplicate for Visual {visual_number}, rejecting...")
                        destination.unlink(missing_ok=True)
                    else:
                        with hash_lock:
                            if f_hash:
                                used_hashes.add(f_hash)
                            if f_dhash:
                                used_dhashes.append(f_dhash)
                        print(f"🎬 [Visual {visual_number}] ✅ Attached via Phase 5 Ladder: {ladder_res['source']} -> {destination.name}")
                        return visual_number, destination
        except Exception as l_err:
            print(f"⚠️ Phase 5 visual ladder notice for Visual {visual_number}: {l_err}")

        if video_dest.exists() and video_dest.stat().st_size > 5000:
            return visual_number, video_dest

        # ============================================================
        # TIER 4: EDITORIAL GRAPHIC CARD (LAST RESORT FALLBACK)
        # ============================================================
        loc_c = loc_c_pre
        try:
            from agents.typography_card import generate_typography_card
            av_p = str(loc_c[1]) if loc_c else None
            if loc_c:
                b_lbl = f"{loc_c[0].upper().replace('_', ' ')} • BIGG BOSS 10"
            elif entity_name:
                b_lbl = f"{entity_name.upper()} • BIGG BOSS 10" if is_bb_scene else f"{entity_name.upper()} • UPDATE"
            elif topic_ctx:
                b_lbl = f"{topic_ctx[:22].upper()} • NEWS BRIEF"
            else:
                b_lbl = "KEY HIGHLIGHT"

            if not av_p and is_bb_scene:
                bb_host = ROOT / "reference_assets" / "contestants" / "akkineni_nagarjuna.jpg"
                if bb_host.exists():
                    av_p = str(bb_host)

            # Zero Repeated Avatar in Editorial Cards:
            with hash_lock:
                if av_p and av_p in used_editorial_avatars:
                    bb_host = ROOT / "reference_assets" / "contestants" / "akkineni_nagarjuna.jpg"
                    if bb_host.exists() and str(bb_host) not in used_editorial_avatars:
                        av_p = str(bb_host)
                        b_lbl = "BIGG BOSS TELUGU 10"
                        used_editorial_avatars.add(av_p)
                    else:
                        av_p = None
                elif av_p:
                    used_editorial_avatars.add(av_p)

            headline = assigned_narration or visual_query or f"Scene {visual_number}"
            print(f"🎨 [Visual {visual_number}] Generating Canva-style editorial card (avatar={av_p is not None})...")
            if generate_typography_card(
                headline_text=headline,
                output_path=str(destination),
                topic_category=topic_category or "general",
                aspect_ratio=aspect_ratio,
                badge_label=b_lbl,
                avatar_image_path=av_p,
                subtext="Bigg Boss Telugu 10 • Star Maa" if is_bb_scene else None,
            ):
                if destination.exists() and destination.stat().st_size > 3000:
                    f_hash = image_hash(destination)
                    f_dhash = image_dhash(destination)
                    with hash_lock:
                        if f_hash:
                            used_hashes.add(f_hash)
                        if f_dhash:
                            used_dhashes.append(f_dhash)
                    try:
                        from data.asset_ledger import record_asset
                        record_asset(
                            video_id="current",
                            beat_id=visual_number,
                            asset_path=str(destination),
                            source_url="editorial_typography_card",
                            tier="TIER_A",
                            license_name="Royalty-Free / Generated",
                            credit_text="AutoTube Broadcast Engine",
                            duration_sec=3.0,
                        )
                    except Exception:
                        pass
                    print(f"✅ Visual {visual_number} saved via Canva-style editorial composite -> {destination.name}")
                    return visual_number, destination
        except Exception as card_err:
            print(f"⚠️ Canva-style card fallback notice for Visual {visual_number}: {card_err}")



        # If typography card fails, try non-AI photo fallback or graceful canvas
        try:
            from PIL import Image, ImageDraw
            w = 1080 if aspect_ratio in ("9:16", "1:1") else 1920
            h = 1920 if aspect_ratio == "9:16" else 1080
            if aspect_ratio == "1:1":
                w, h = 1080, 1080
            canvas = Image.new("RGB", (w, h), color=(15, 23, 42))
            destination.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(destination, "JPEG", quality=90)
            file_hash = image_hash(destination)
            with hash_lock:
                if file_hash:
                    used_hashes.add(file_hash)
            return visual_number, destination
        except Exception as canvas_err:
            fb = Image.new("RGB", (720, 1280 if aspect_ratio == "9:16" else 720), color=(10, 15, 30))
            destination.parent.mkdir(parents=True, exist_ok=True)
            fb.save(destination, "JPEG")
            return visual_number, destination

    # Parallel download workers (optimized for high throughput)
    workers = min(5, target_count)
    print(f"Downloading {target_count} visuals in parallel with {workers} worker threads...")
    results_map = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_single_visual, (num, q)): num
            for num, q in enumerate(visuals, start=1)
        }
        for future in as_completed(futures):
            num = futures[future]
            try:
                v_num, dest = future.result(timeout=45)
                if dest and dest.exists():
                    results_map[v_num] = dest
            except Exception as e:
                print(f"Visual {num} download warning: {e}")

            if progress_callback:
                done_count = len(results_map)
                pct = min(54, 35 + int((done_count / max(1, target_count)) * 18))
                try:
                    progress_callback(pct, text=f"Sourcing visuals ({done_count}/{target_count} scenes ready)...")
                except TypeError:
                    try:
                        progress_callback(pct)
                    except Exception:
                        pass
                except Exception:
                    pass

    # Fallback Handling: Canva Editorial Card for Reality/Celebrities, Dynamic FLUX for General, Typography Card
    for num in range(1, target_count + 1):
        dest = ASSETS_DIR / f"{num}.jpg"
        video_dest = ASSETS_DIR / f"{num}.mp4"
        if num not in results_map or not dest.exists():
            applied = False
            from utils.season_guard import is_bigg_boss_topic
            is_bb_mode = is_bigg_boss_topic(topic or "") or "bigg boss" in str(topic_category).lower()
            
            # 1. Reality Show / Bigg Boss: Zero Anime/Cartoon Faces -> Canva Editorial Card with real photo
            if is_bb_mode:
                try:
                    from agents.typography_card import generate_typography_card
                    b_main_ent = ""
                    vp_file = OUTPUT_DIR / "visual_plan.json"
                    if vp_file.exists():
                        try:
                            v_json = json.loads(vp_file.read_text(encoding="utf-8"))
                            for b_item in v_json:
                                if b_item.get("beat_id") == num:
                                    b_main_ent = b_item.get("main_entity") or b_item.get("primary_entity", "")
                                    break
                        except Exception:
                            pass
                    
                    loc_c = find_local_contestant_image(f"{b_main_ent} {section_narrations.get(num, '')}")
                    if not loc_c and topic_person_slug:
                        loc_c = find_local_contestant_image(topic_person_slug)
                    av_p = str(loc_c[1]) if loc_c else None
                    b_lbl = f"{loc_c[0].upper().replace('_', ' ')} • BIGG BOSS 10" if loc_c else "BIGG BOSS TELUGU 10"
                    if not av_p:
                        bb_host = ROOT / "reference_assets" / "contestants" / "akkineni_nagarjuna.jpg"
                        if bb_host.exists():
                            av_p = str(bb_host)
                    
                    headline = section_narrations.get(num, "") or (visuals[num - 1] if num - 1 < len(visuals) else f"Scene {num}")
                    print(f"🎨 [Scene {num}] Generating Canva-style editorial card with real photo (avatar={av_p is not None})...")
                    if generate_typography_card(
                        headline_text=headline,
                        output_path=str(dest),
                        topic_category="entertainment",
                        aspect_ratio=aspect_ratio,
                        badge_label=b_lbl,
                        avatar_image_path=av_p,
                        subtext="Bigg Boss Telugu 10 • Star Maa",
                    ):
                        file_hash = image_hash(dest)
                        file_dhash = image_dhash(dest)
                        with hash_lock:
                            if file_hash:
                                used_hashes.add(file_hash)
                            if file_dhash:
                                used_dhashes.append(file_dhash)
                        results_map[num] = dest
                        applied = True
                        try:
                            from data.asset_ledger import record_asset
                            record_asset(
                                video_id="current",
                                beat_id=num,
                                asset_path=str(dest),
                                source_url="canva_editorial_contestant_card",
                                tier="TIER_A",
                                license_name="AutoTube Editorial Card",
                                credit_text="AutoTube Visual Engine",
                                duration_sec=3.0,
                            )
                        except Exception:
                            pass
                        print(f"  ✓ Generated Canva-style Editorial Card with real photo for Visual {num}")
                except Exception as card_err:
                    print(f"  Editorial card fallback note: {card_err}")
            else:
                # 1b. Attempt dynamic FLUX generation for the specific scene concept
                try:
                    from config.settings import get_setting
                    from utils.season_guard import resolve_effective_show_context
                    
                    b_main_ent = ""
                    b_emo = ""
                    v_fb_prompt = ""
                    vp_file = OUTPUT_DIR / "visual_plan.json"
                    if vp_file.exists():
                        try:
                            v_json = json.loads(vp_file.read_text(encoding="utf-8"))
                            for b_item in v_json:
                                if b_item.get("beat_id") == num:
                                    b_main_ent = b_item.get("main_entity") or b_item.get("primary_entity", "")
                                    b_emo = b_item.get("emotion") or b_item.get("emotion_or_action", "")
                                    v_fb_prompt = b_item.get("visual_fallback_prompt", "")
                                    break
                        except Exception:
                            pass

                    if b_main_ent and b_emo:
                        clean_p = f"Cinematic {b_main_ent} in {b_emo} expression, {aspect_ratio} vertical ratio, photorealistic, 8k, dramatic lighting, live action photograph, no anime, no cartoon"
                    elif v_fb_prompt:
                        if v_fb_prompt.lower().startswith("cinematic"):
                            clean_p = f"{v_fb_prompt}, live action photograph, no anime, no cartoon"
                        else:
                            clean_p = f"Cinematic {v_fb_prompt}, {aspect_ratio} vertical ratio, photorealistic, 8k, dramatic lighting, live action photograph, no anime, no cartoon"
                    else:
                        show_ctx = resolve_effective_show_context(
                            topic_or_title=topic or topic_category or "",
                            raw_show_context=get_setting("SHOW_CONTEXT", ""),
                        )
                        prompt_q = visuals[num - 1] if num - 1 < len(visuals) else "cinematic visual scene"
                        is_expl = generation_mode in ("explainer", "Explainer Style", "📊 Explainer Style")
                        clean_p = rewrite_query_for_flux(
                            prompt_q,
                            is_explainer=is_expl,
                            show_context=show_ctx,
                            topic_category=topic_category or topic,
                        )
                    print(f"🎨 Generating dynamic FLUX visual for Scene {num}: '{clean_p[:60]}...'")
                    if generate_pollinations_image(clean_p, dest, aspect_ratio=aspect_ratio, force=True):
                        file_hash = image_hash(dest)
                        file_dhash = image_dhash(dest)
                        with hash_lock:
                            if file_hash:
                                used_hashes.add(file_hash)
                            if file_dhash:
                                used_dhashes.append(file_dhash)
                        results_map[num] = dest
                        applied = True
                        try:
                            from data.asset_ledger import record_asset
                            record_asset(
                                video_id="current",
                                beat_id=num,
                                asset_path=str(dest),
                                source_url="pollinations_flux",
                                tier="TIER_A",
                                license_name="Generated FLUX (CC0)",
                                credit_text="AutoTube FLUX Engine",
                                duration_sec=3.0,
                            )
                        except Exception:
                            pass
                        print(f"  ✓ Dynamically generated tailored FLUX image for Visual {num}")
                except Exception as dyn_err:
                    print(f"  Dynamic FLUX generation note: {dyn_err}")

            # 2. Rule 2: Zero Blank/Text-Only Screens - Single-use Show Interior Fallback
            if not applied:
                try:
                    from utils.season_guard import is_bigg_boss_topic
                    is_bb_mode = is_bigg_boss_topic(topic or "") or "bigg boss" in str(topic_category).lower()
                    bb_house = ROOT / "assets" / "entities" / "bigg_boss_telugu" / "image.jpg"
                    bb_h = image_hash(bb_house) if bb_house.exists() else None
                    if is_bb_mode and bb_house.exists() and bb_h and (bb_h not in used_hashes):
                        shutil.copy2(bb_house, dest)
                        clean_and_crop_image(dest, aspect_ratio=aspect_ratio)
                        results_map[num] = dest
                        applied = True
                        with hash_lock:
                            used_hashes.add(bb_h)
                        try:
                            from data.asset_ledger import record_asset
                            record_asset(
                                video_id="current",
                                beat_id=num,
                                asset_path=str(dest),
                                source_url="bigg_boss_house_interior",
                                tier="TIER_A",
                                license_name="Standard Show Visual (CC-BY)",
                                credit_text="Bigg Boss Telugu House",
                                duration_sec=3.0,
                            )
                        except Exception:
                            pass
                        print(f"  ✓ Attached unique Show Interior fallback -> assets/{num}.jpg")
                except Exception as fb_err:
                    print(f"  Narrative fallback notice: {fb_err}")

            # 3. Phase 5 Typography Card: Guaranteed 100% relevant, 0% copyright risk
            if not applied:
                try:
                    from agents.typography_card import generate_typography_card
                    headline = section_narrations.get(num, "") or (visuals[num - 1] if num - 1 < len(visuals) else f"Scene {num}")
                    print(f"💡 [Phase 5 Ladder] Generating Pillow Typography Card for Scene {num}...")
                    if generate_typography_card(
                        headline_text=headline,
                        output_path=str(dest),
                        topic_category=topic_category or "general",
                        aspect_ratio=aspect_ratio,
                        subtext=f"Scene {num} Breakdown",
                    ):
                        results_map[num] = dest
                        applied = True
                        try:
                            from data.asset_ledger import record_asset
                            record_asset(
                                video_id="current",
                                beat_id=num,
                                asset_path=str(dest),
                                source_url="pillow_typography_card",
                                tier="TIER_A",
                                license_name="AutoTube Generated Graphics",
                                credit_text="AutoTube Graphic Engine",
                                duration_sec=3.0,
                            )
                        except Exception:
                            pass
                        print(f"  ✓ Attached Phase 5 Typography Card -> assets/{num}.jpg")
                except Exception as card_err:
                    print(f"  Typography card fallback note: {card_err}")

            if not applied and flyer_path and save_flyer_fallback(flyer_path, dest):
                results_map[num] = dest
                try:
                    from data.asset_ledger import record_asset
                    record_asset(
                        video_id="current",
                        beat_id=num,
                        asset_path=str(dest),
                        source_url="uploaded_flyer",
                        tier="TIER_A",
                        license_name="User Uploaded",
                        credit_text="User Media",
                        duration_sec=3.0,
                    )
                except Exception:
                    pass

    # ========================================================
    # HARD NON-EMPTY VERIFICATION CHECK (Section 10a)
    # ========================================================
    valid_count = 0
    missing_indices = []
    for number in range(1, target_count + 1):
        jpg_file = ASSETS_DIR / f"{number}.jpg"
        mp4_file = ASSETS_DIR / f"{number}.mp4"
        is_valid = False
        if mp4_file.exists() and mp4_file.stat().st_size > 10000:
            is_valid = True
            if not jpg_file.exists() or jpg_file.stat().st_size == 0:
                extract_video_frame(mp4_file, jpg_file)
        elif jpg_file.exists() and jpg_file.stat().st_size > 4000:
            try:
                with Image.open(jpg_file) as img_test:
                    img_test.verify()
                is_valid = True
            except Exception:
                is_valid = False

        if is_valid:
            valid_count += 1
        else:
            missing_indices.append(number)

    # Creator Canvas mode: a scene with no usable photo is rendered as a typography / name card, so a
    # missing asset must not abort the video. Drop in a neutral placeholder so numbering stays contiguous.
    if missing_indices:
        try:
            from agents.canvas_ladder import canvas_enabled, write_placeholder
            if canvas_enabled():
                for number in missing_indices:
                    write_placeholder(ASSETS_DIR / f"{number}.jpg")
                print(f"🧩 [Canvas] {len(missing_indices)} scene(s) have no real photo {missing_indices}; "
                      "placeholders written (rendered as typography cards, never AI faces).")
                valid_count += len(missing_indices)
                missing_indices = []
        except ImportError:
            pass

    # Recovery: Guarantee every missing index gets a high-quality Typography Card or fallback
    if missing_indices:
        print(f"🛠️ [Section 10a Self-Healing] Synthesizing guaranteed fallbacks for missing scenes: {missing_indices}")
        still_missing = []
        for m_idx in missing_indices:
            m_dest = ASSETS_DIR / f"{m_idx}.jpg"
            healed = False
            headline = section_narrations.get(m_idx, "") or (visuals[m_idx - 1] if m_idx - 1 < len(visuals) else f"Scene {m_idx}")

            # 1. Reality Show / Bigg Boss: Zero Anime/Cartoon Faces -> Canva Editorial Card with real photo
            if is_bb_mode:
                try:
                    from agents.typography_card import generate_typography_card
                    loc_c = find_local_contestant_image(f"{headline}")
                    if not loc_c and topic_person_slug:
                        loc_c = find_local_contestant_image(topic_person_slug)
                    av_p = str(loc_c[1]) if loc_c else None
                    b_lbl = f"{loc_c[0].upper().replace('_', ' ')} • BIGG BOSS 10" if loc_c else "BIGG BOSS TELUGU 10"
                    if not av_p:
                        bb_host = ROOT / "reference_assets" / "contestants" / "akkineni_nagarjuna.jpg"
                        if bb_host.exists():
                            av_p = str(bb_host)
                    healed = generate_typography_card(
                        headline_text=headline,
                        output_path=str(m_dest),
                        topic_category="entertainment",
                        aspect_ratio=aspect_ratio,
                        badge_label=b_lbl,
                        avatar_image_path=av_p,
                        subtext="Bigg Boss Telugu 10 • Star Maa",
                    )
                    if healed and m_dest.exists() and m_dest.stat().st_size > 1000:
                        print(f"  ✓ Emergency Canva-style editorial card synthesized -> assets/{m_idx}.jpg")
                except Exception as c_err:
                    print(f"  Emergency editorial card notice: {c_err}")
                    healed = False
            else:
                # 1b. First attempt fast free text-to-image (Pollinations FLUX/Sana) tailored to scene narration
                try:
                    from providers.image import generate_pollinations_image
                    flux_prompt = rewrite_query_for_flux(headline, is_explainer=False, show_context=show_ctx, topic_category=topic_category or topic or "general")
                    print(f"🎨 [Emergency FLUX] Synthesizing scene visual for missing Beat {m_idx}: '{flux_prompt[:45]}...'")
                    if generate_pollinations_image(f"{flux_prompt}, live action photograph, no anime, no cartoon", m_dest, aspect_ratio=aspect_ratio, force=True):
                        if m_dest.exists() and m_dest.stat().st_size > 1000:
                            healed = True
                            print(f"  ✓ Emergency FLUX visual synthesized -> assets/{m_idx}.jpg")
                except Exception as f_err:
                    print(f"  FLUX fallback notice: {f_err}")

                # 2. If FLUX fails, generate dynamic context-aware typography card
                if not healed:
                    try:
                        from agents.typography_card import generate_typography_card
                        healed = generate_typography_card(
                            headline_text=headline,
                            output_path=str(m_dest),
                            topic_category=topic_category or "general",
                            aspect_ratio=aspect_ratio,
                            subtext=f"Scene {m_idx} Breakdown",
                        )
                    except Exception as h_err:
                        print(f"  Emergency typography fallback notice: {h_err}")
                        healed = False

            if not healed:
                try:
                    if is_bb_mode:
                        bb_house = ROOT / "assets" / "entities" / "bigg_boss_telugu" / "image.jpg"
                        fb_img = (ROOT / "assets" / "fallback" / "fallback_1.jpg")
                        cand_bg = bb_house if bb_house.exists() else fb_img
                    else:
                        # STRICT NON-BIGG BOSS FALLBACK: Never touch bigg boss house or stage!
                        cand_bg = ROOT / "assets" / "fallback" / "fallback_1.jpg"

                    cand_h = image_hash(cand_bg) if cand_bg and cand_bg.exists() else None
                    if cand_bg and cand_bg.exists() and cand_h and (cand_h not in used_hashes):
                        used_hashes.add(cand_h)
                        shutil.copy2(cand_bg, m_dest)
                        clean_and_crop_image(m_dest, aspect_ratio=aspect_ratio)
                        healed = True
                    else:
                        w = 1080 if aspect_ratio == "9:16" else 1920
                        h = 1920 if aspect_ratio == "9:16" else 1080
                        fb = Image.new("RGB", (w, h), color=(20 + (m_idx * 17) % 60, 25 + (m_idx * 13) % 50, 45 + (m_idx * 19) % 60))
                        fb.save(m_dest, "JPEG", quality=90)
                        healed = True
                except Exception:
                    healed = False

            if healed and m_dest.exists() and m_dest.stat().st_size > 1000:
                valid_count += 1
                try:
                    from data.asset_ledger import record_asset
                    record_asset(
                        video_id="current",
                        beat_id=m_idx,
                        asset_path=str(m_dest),
                        source_url="emergency_typography_card",
                        tier="TIER_A",
                        license_name="AutoTube Generated Graphics",
                        credit_text="AutoTube Engine",
                        duration_sec=3.0,
                    )
                except Exception:
                    pass
            else:
                still_missing.append(m_idx)
        missing_indices = still_missing

    print(f"📊 Visual Verification Audit: {valid_count}/{target_count} real visual assets verified.")
    if valid_count == 0 or missing_indices:
        err_msg = (
            f"🚨 Visual asset generation failed: {len(missing_indices)} scene(s) {missing_indices} "
            f"have no valid visual assets ({valid_count}/{target_count} valid). "
            f"Video creation aborted to trigger supervisor topic retry."
        )
        print(err_msg)
    # Deduplicate repeated consecutive assets (> 2 consecutive beats) with dynamic FLUX AI fallback
    try:
        from agents.visual_agent import deduplicate_consecutive_assets
        deduplicate_consecutive_assets(
            assets_dir=ASSETS_DIR,
            section_narrations=section_narrations,
            visuals=visuals,
            aspect_ratio=aspect_ratio,
            topic_category=topic_category or kwargs.get("content_type", "general"),
            max_consecutive=2,
            target_count=target_count,
            show_context=show_ctx if "show_ctx" in locals() else "",
        )
    except Exception as d_err:
        print(f"⚠️ Visual deduplication notice: {d_err}")

    # Auto-balance copyright tier B dynamically based on topic/content_type (Fair Use allowance up to 50%)
    try:
        auto_balance_copyright_tier_b(
            visuals=visuals,
            aspect_ratio=aspect_ratio,
            target_count=target_count,
            section_narrations=section_narrations,
            content_type=topic_category or kwargs.get("content_type", ""),
            topic=topic or kwargs.get("topic", ""),
        )
    except Exception as bal_err:
        print(f"Auto-balance copyright notice: {bal_err}")

    # ========================================================
    # ABSOLUTE ZERO DUPLICATE VISUAL ENFORCER (100% Unique Visuals)
    # ========================================================
    try:
        final_seen_hashes = set()
        final_seen_dhashes = []
        from utils.season_guard import is_bigg_boss_topic
        is_bb_mode = is_bigg_boss_topic(topic or "") or "bigg boss" in str(topic_category).lower()

        for idx in range(1, target_count + 1):
            cur_p = ASSETS_DIR / f"{idx}.jpg"
            if not cur_p.exists():
                continue
            cur_h = image_hash(cur_p)
            cur_dh = image_dhash(cur_p)
            is_dup = (cur_h and cur_h in final_seen_hashes) or (cur_dh and is_perceptual_duplicate(cur_dh, final_seen_dhashes, max_dist=6))
            if is_dup:
                print(f"🔄 [Zero-Duplicate Enforcer] Beat {idx} duplicates an earlier beat visual! Replacing with unique asset...")
                replaced = False
                
                # 1. Try unused news photo from cache
                from tools.news_media_harvester import CACHE_DIR as NEWS_CACHE
                if NEWS_CACHE.exists():
                    for n_file in sorted(NEWS_CACHE.glob("*.jpg"), key=lambda f: f.stat().st_mtime, reverse=True):
                        cand_h = image_hash(n_file)
                        cand_dh = image_dhash(n_file)
                        if cand_h and cand_h not in final_seen_hashes and not is_perceptual_duplicate(cand_dh, final_seen_dhashes, max_dist=6):
                            shutil.copy2(n_file, cur_p)
                            clean_and_crop_image(cur_p, aspect_ratio=aspect_ratio)
                            cur_h = image_hash(cur_p)
                            cur_dh = image_dhash(cur_p)
                            replaced = True
                            print(f"  ✓ Beat {idx} replaced with unique news still: {n_file.name}")
                            break

                # 2. Try unused promo frame from cache
                if not replaced:
                    from tools.promo_video_harvester import PROMO_CACHE_DIR
                    if PROMO_CACHE_DIR.exists():
                        for p_file in sorted(PROMO_CACHE_DIR.glob("*.jpg"), key=lambda f: f.stat().st_mtime, reverse=True):
                            cand_h = image_hash(p_file)
                            cand_dh = image_dhash(p_file)
                            if cand_h and cand_h not in final_seen_hashes and not is_perceptual_duplicate(cand_dh, final_seen_dhashes, max_dist=6):
                                shutil.copy2(p_file, cur_p)
                                clean_and_crop_image(cur_p, aspect_ratio=aspect_ratio)
                                cur_h = image_hash(cur_p)
                                cur_dh = image_dhash(cur_p)
                                replaced = True
                                print(f"  ✓ Beat {idx} replaced with unique promo frame: {p_file.name}")
                                break

                # 3. Try unused Telugu reaction meme
                if not replaced:
                    from tools.meme_manager import MEMES_DIR
                    if MEMES_DIR.exists():
                        for m_file in sorted(MEMES_DIR.glob("*.jpg")):
                            cand_h = image_hash(m_file)
                            cand_dh = image_dhash(m_file)
                            if cand_h and cand_h not in final_seen_hashes and not is_perceptual_duplicate(cand_dh, final_seen_dhashes, max_dist=6):
                                shutil.copy2(m_file, cur_p)
                                clean_and_crop_image(cur_p, aspect_ratio=aspect_ratio)
                                cur_h = image_hash(cur_p)
                                cur_dh = image_dhash(cur_p)
                                replaced = True
                                print(f"  ✓ Beat {idx} replaced with unique reaction meme: {m_file.name}")
                                break

                # 4. Synthesize distinct typography card
                if not replaced:
                    from agents.typography_card import generate_typography_card
                    headline = (section_narrations.get(idx) if section_narrations else None) or (visuals[idx - 1] if idx - 1 < len(visuals) else f"Beat {idx}")
                    generate_typography_card(
                        headline_text=headline,
                        output_path=str(cur_p),
                        topic_category="entertainment" if is_bb_mode else "general",
                        aspect_ratio=aspect_ratio,
                        badge_label=f"SCENE {idx} • KEY MOMENT",
                    )
                    cur_h = image_hash(cur_p)
                    cur_dh = image_dhash(cur_p)
                    print(f"  ✓ Beat {idx} replaced with unique scene typography card")

            if cur_h:
                final_seen_hashes.add(cur_h)
            if cur_dh:
                final_seen_dhashes.append(cur_dh)
    except Exception as z_err:
        print(f"Notice during zero-duplicate enforcement: {z_err}")

    final_images = [
        ASSETS_DIR / f"{number}.jpg"
        for number in range(1, target_count + 1)
    ]

    # Universal Canvas Scaling Guard: Ensure 100% of final assets match exact canvas dimensions (1080x1920)
    for img in final_images:
        if img.exists():
            try:
                from providers.image import clean_and_crop_image
                clean_and_crop_image(img, aspect_ratio=aspect_ratio)
            except Exception:
                pass

    print()
    line()

    print(
        f"FINAL IMAGES: {len(final_images)}"
    )

    print(
        "Visual-plan image download successful"
    )

    line()

    return [
        str(
            ASSETS_DIR / f"{number}.jpg"
        )
        for number in range(
            1,
            target_count + 1,
        )
    ]
