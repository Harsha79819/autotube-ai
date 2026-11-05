#!/usr/bin/env python3
"""
tools/meme_manager.py - Telugu Reaction Meme Manager

Manages iconic Telugu reaction cutaways (Brahmanandam, Sunil, Ali, MS Narayana)
for roast, comedy, shock, and overacting beats.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import List, Optional, Set

ROOT = Path(__file__).resolve().parent.parent
MEMES_DIR = ROOT / "reference_assets" / "memes"
if not MEMES_DIR.exists():
    MEMES_DIR = ROOT / "assets" / "memes"

DYNAMIC_MEMES_DIR = ROOT / "assets" / "memes" / "dynamic"
DYNAMIC_MEMES_DIR.mkdir(parents=True, exist_ok=True)

USED_MEMES_FILE = ROOT / "data" / "used_memes.json"


def load_persistent_used_memes(cooldown_runs: int = 15) -> List[str]:
    """Loads the history of memes used in recent runs to prevent repetition across runs."""
    if not USED_MEMES_FILE.exists():
        return []
    try:
        data = json.loads(USED_MEMES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(fn) for fn in data if isinstance(fn, str)]
    except Exception:
        pass
    return []


def record_used_meme(filename: str) -> None:
    """Records a selected meme into the persistent ledger."""
    if not filename:
        return
    try:
        USED_MEMES_FILE.parent.mkdir(parents=True, exist_ok=True)
        history: List[str] = []
        if USED_MEMES_FILE.exists():
            data = json.loads(USED_MEMES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                history = data
        history.append(filename)
        # Keep last 100 meme entries
        USED_MEMES_FILE.write_text(json.dumps(history[-100:], indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


TELUGU_COMEDY_ACTORS = {
    "brahmanandam": [r"బ్రహ్మానందం", r"బ్రహ్మి", r"brahmi", r"brahmanandam"],
    "sunil": [r"సునీల్", r"sunil"],
    "ali": [r"అలీ", r"ali"],
    "ms_narayana": [r"ఎంఎస్\s*నారాయణ", r"నారాయణ", r"ms\s*narayana"],
    "venu_madhav": [r"వేణు\s*మాధవ్", r"venu\s*madhav"],
    "dharmavarapu": [r"ధర్మవరపు", r"dharmavarapu"],
    "babu_mohan": [r"బాబు\s*మోహన్", r"babu\s*mohan"],
    "posani": [r"పోసాని", r"posani"],
    "vennela_kishore": [r"వెన్నెల\s*కిషోర్", r"vennela\s*kishore"],
    "raghu_babu": [r"రఘు\s*బాబు", r"raghu\s*babu"],
    "kota": [r"కోట", r"కోట\s*శ్రీనివాస", r"kota"],
}


def detect_actor_from_text(text: str) -> Optional[str]:
    """Detects iconic Telugu comedy actor referenced in the beat narration."""
    if not text:
        return None
    for actor_key, patterns in TELUGU_COMEDY_ACTORS.items():
        for pat in patterns:
            if re.search(pat, text, flags=re.IGNORECASE):
                return actor_key
    return None


EMOTION_MEME_MAP = {
    "shocked": [
        "babu_mohan_shock.jpg", "venu_madhav_shock.jpg", "sunil_shocked.jpg",
        "brahmi_shocked.jpg", "brahmi_aha.jpg", "brahmi_doubt.jpg"
    ],
    "shock": [
        "babu_mohan_shock.jpg", "venu_madhav_shock.jpg", "sunil_shocked.jpg",
        "brahmi_shocked.jpg", "brahmi_aha.jpg"
    ],
    "overacting": [
        "posani_shouting.jpg", "venky_frustrated.jpg", "brahmi_headache.jpg",
        "brahmi_crying.jpg", "jayaprakash_angry.jpg"
    ],
    "headache": [
        "brahmi_headache.jpg", "venky_frustrated.jpg", "ms_narayana_facepalm.jpg"
    ],
    "crying": [
        "brahmi_crying.jpg", "brahmi_weeping.jpg", "venky_frustrated.jpg"
    ],
    "laughing": [
        "sunil_laughing.jpg", "ali_funny.jpg", "brahmi_aha.jpg"
    ],
    "comedy": [
        "ali_dance.jpg", "sunil_laughing.jpg", "ali_funny.jpg",
        "dharmavarapu_sarcasm.jpg", "venky_namo.jpg"
    ],
    "roast": [
        "dharmavarapu_sarcasm.jpg", "posani_shouting.jpg", "kota_cunning.jpg",
        "sunil_sarcastic.jpg", "brahmi_pointing.jpg", "ms_narayana_facepalm.jpg"
    ],
    "confused": [
        "brahmi_doubt.jpg", "ali_questioning.jpg", "kota_thinking.jpg"
    ],
    "facepalm": [
        "ms_narayana_facepalm.jpg", "brahmi_headache.jpg", "venky_frustrated.jpg"
    ],
    "suspicious": [
        "kota_cunning.jpg", "brahmi_doubt.jpg", "kota_thinking.jpg", "ali_questioning.jpg"
    ],
    "angry": [
        "jayaprakash_angry.jpg", "posani_shouting.jpg", "venky_frustrated.jpg"
    ],
    "running": [
        "brahmi_running.jpg", "ali_dance.jpg"
    ],
    "salute": [
        "brahmi_salute.jpg", "venky_namo.jpg"
    ],
}

TELUGU_KEYWORD_MAP = {
    r"మైండ్|బ్లాంక్|బ్లాక్|షాక్|షాకై|ట్విస్ట్|ఎలిమినేషన్|గుండె|ఆశ్చర్యం|shock|twist|elimination|mind\s*block": "shocked",
    r"ఓవరాక్షన్|ఓవరాక్టింగ్|దరిద్రం|నాయనా|ఇదేంట్రా|టార్చర్|ఎర్రి|రోత|overaction|overacting": "overacting",
    r"నవ్వు|నవ్వుకోవాలి|కామెడీ|రచ్చ|జాతర|ఫన్నీ|comedy|funny|laugh": "comedy",
    r"ఏడుపు|కన్నీళ్లు|బాధ|రోదన|వెన్నుపోటు|ఎమోషనల్|crying|sad": "crying",
    r"తల\s*పట్టు|తలనొప్పి|ఫ్రస్ట్రేషన్|headache|frustrated": "headache",
    r"పీఆర్\s*స్ట్రాటజీ|కవరింగ్|ఫేక్|డబుల్\s*గేమ్|కుట్ర|గేమ్\s*ప్లాన్|suspicious": "suspicious",
    r"రోస్ట్|నుగ్గు|ఉతికి|తోలు\s*తీసి|కడిగి|చిత్తు|roast|savage": "roast",
    r"కోపం|అరిచి|దద్దరిల్లి|ఫైర్|గ్రిల్లింగ్|angry|fight": "angry",
}


def match_emotion_from_text(text: str) -> Optional[str]:
    """Extracts dominant meme emotion category from Telugu or English text."""
    if not text:
        return None
    t_lower = text.lower()
    for eng_cat in EMOTION_MEME_MAP:
        if eng_cat in t_lower:
            return eng_cat
    for pattern, cat in TELUGU_KEYWORD_MAP.items():
        if re.search(pattern, text):
            return cat
    return None


def fetch_dynamic_online_meme(
    emotion: str,
    actor: Optional[str] = None,
    used_memes: Optional[Set[str]] = None,
    recent_history: Optional[List[str]] = None,
) -> Optional[Path]:
    """
    Dynamically harvests a fresh, unwatermarked Telugu reaction meme from the web.
    Searches specifically for actor + emotion to guarantee script context match.
    """
    try:
        from providers.image import search_duckduckgo_images
        import requests
        from PIL import Image
        from io import BytesIO
        from tools.ocr_guard import scan_images_ocr

        recent_set = set(recent_history or [])

        # Formulate highly specific query
        if actor:
            actor_clean = actor.replace("_", " ")
            q = f"{actor_clean} {emotion} telugu comedy reaction meme template"
        else:
            q = f"telugu comedy reaction meme {emotion} clean hd template"

        print(f"🔍 [Dynamic Meme Search] Querying web: '{q}'...")
        hits = search_duckduckgo_images(q, max_results=8)
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

        for hit in hits:
            u = hit.get("image_url")
            if not u:
                continue
            try:
                r = requests.get(u, headers=headers, timeout=6)
                if r.status_code == 200 and len(r.content) > 10000:
                    h_name = hashlib.md5(r.content).hexdigest()[:10]
                    file_stem = f"{actor or 'telugu'}_{emotion}_{h_name}.jpg"
                    if used_memes and file_stem in used_memes:
                        continue
                    if file_stem in recent_set:
                        continue

                    with Image.open(BytesIO(r.content)) as im:
                        w, h = im.size
                        if w >= 320 and h >= 240:
                            out_path = DYNAMIC_MEMES_DIR / file_stem
                            rgb = im.convert("RGB")
                            rgb.save(out_path, "JPEG", quality=92)

                            # Watermark & branding check
                            ocr = scan_images_ocr([out_path])
                            txt = ocr.get(str(out_path), "").lower()
                            if any(b in txt for b in ["kulfy", "shutterstock", "getty", "alamy", "watermark"]):
                                out_path.unlink(missing_ok=True)
                                continue

                            print(f"✅ [Dynamic Meme Found] Fresh meme saved -> {out_path.name} ({w}x{h})")
                            return out_path
            except Exception:
                continue
    except Exception as e:
        print(f"Notice: Dynamic meme harvest exception: {e}")
    return None


def get_reaction_meme(
    emotion_or_text: str,
    used_memes: Optional[Set[str]] = None,
    cooldown_runs: int = 30,
) -> Optional[Path]:
    """
    Returns an authentic Telugu reaction meme Path matching the script beat.
    Priority:
      1. Dynamic web search matching the detected Actor + Emotion of the beat.
      2. If web search returns clean meme, save and return.
      3. Fallback to local curated meme pool with strict anti-repetition cooldown.
    """
    raw_text = str(emotion_or_text or "")
    matched_actor = detect_actor_from_text(raw_text)
    matched_cat = match_emotion_from_text(raw_text)
    if not matched_cat:
        matched_cat = raw_text.lower().strip() or "comedy"

    recent_history = load_persistent_used_memes(cooldown_runs=cooldown_runs)

    # 1. First Priority: Dynamic live web search tailored to this exact script beat!
    try:
        online_p = fetch_dynamic_online_meme(
            emotion=matched_cat,
            actor=matched_actor,
            used_memes=used_memes,
            recent_history=recent_history,
        )
        if online_p and online_p.exists() and online_p.stat().st_size > 5000:
            if used_memes is not None:
                used_memes.add(online_p.name)
            record_used_meme(online_p.name)
            return online_p
    except Exception as dyn_err:
        print(f"Dynamic meme search notice: {dyn_err}")

    # 2. Fallback to local curated pool with strict anti-repetition
    candidate_files = []
    if matched_actor:
        candidate_files = [p.name for p in MEMES_DIR.glob(f"*{matched_actor}*.jpg")]

    if not candidate_files:
        candidate_files = [fn for fn in EMOTION_MEME_MAP.get(matched_cat, []) if (MEMES_DIR / fn).exists()]

    if not candidate_files:
        candidate_files = [fn for fn in ["sunil_laughing.jpg", "babu_mohan_shock.jpg", "ali_funny.jpg", "brahmi_shocked.jpg", "venky_frustrated.jpg", "ms_narayana_facepalm.jpg"] if (MEMES_DIR / fn).exists()]

    if not candidate_files and MEMES_DIR.exists():
        candidate_files = [p.name for p in MEMES_DIR.glob("*.jpg")]

    # Filter out current run
    run_candidates = [
        fn for fn in candidate_files
        if used_memes is None or fn not in used_memes
    ]

    recent_set = set(recent_history[-cooldown_runs:] if len(recent_history) >= cooldown_runs else recent_history)
    fresh_candidates = [fn for fn in run_candidates if fn not in recent_set]

    selected_fn = None
    if fresh_candidates:
        selected_fn = fresh_candidates[0]
    elif run_candidates:
        def _last_used_index(fn: str) -> int:
            try:
                for idx in range(len(recent_history) - 1, -1, -1):
                    if recent_history[idx] == fn:
                        return idx
                return -1
            except Exception:
                return -1
        selected_fn = min(run_candidates, key=_last_used_index)

    if selected_fn:
        p = MEMES_DIR / selected_fn
        if p.exists() and p.stat().st_size > 5000:
            if used_memes is not None:
                used_memes.add(selected_fn)
            record_used_meme(selected_fn)
            return p

    return None


if __name__ == "__main__":
    test_phrases = [
        "అక్కడ చేస్తున్న ఓవరాక్షన్ చూసి ఆడియన్స్‌కి మైండ్ బ్లాంక్ అయిపోయింది అండి బాబు!",
        "ఇదేంట్రా నాయనా ఈ దరిద్రపు డ్రామా అంటూ తలలు పట్టుకున్నారు!",
        "చరణ్ మహాదేవ్ పట్టుకుని పీఆర్ స్ట్రాటజీని అందరి ముందు నగ్నంగా బయటపెట్టేశాడు!",
        "shocked reaction"
    ]
    used = set()
    for ph in test_phrases:
        m = get_reaction_meme(ph, used_memes=used)
        print(f"Phrase: '{ph[:40]}...' -> Meme: {m.name if m else 'None'}")
