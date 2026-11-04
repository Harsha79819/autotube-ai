#!/usr/bin/env python3
"""
tools/meme_manager.py - Telugu Reaction Meme Manager

Manages iconic Telugu reaction cutaways (Brahmanandam, Sunil, Ali, MS Narayana)
for roast, comedy, shock, and overacting beats.
"""

import json
import re
from pathlib import Path
from typing import List, Optional, Set

ROOT = Path(__file__).resolve().parent.parent
MEMES_DIR = ROOT / "reference_assets" / "memes"
if not MEMES_DIR.exists():
    MEMES_DIR = ROOT / "assets" / "memes"

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


def fetch_dynamic_online_meme(emotion: str) -> Optional[Path]:
    """Dynamically harvests a fresh, unwatermarked Telugu reaction meme from the web."""
    try:
        from providers.image import search_duckduckgo_images
        import requests
        from PIL import Image
        from io import BytesIO
        from tools.ocr_guard import scan_images_ocr

        q = f"telugu comedy reaction meme {emotion} clean hd"
        hits = search_duckduckgo_images(q, max_results=6)
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

        for hit in hits:
            u = hit.get("image_url")
            if not u:
                continue
            try:
                r = requests.get(u, headers=headers, timeout=6)
                if r.status_code == 200 and len(r.content) > 10000:
                    with Image.open(BytesIO(r.content)) as im:
                        w, h = im.size
                        if w >= 320 and h >= 250:
                            h_name = hashlib.md5(r.content).hexdigest()[:8]
                            out_path = MEMES_DIR / f"online_{emotion}_{h_name}.jpg"
                            rgb = im.convert("RGB")
                            rgb.save(out_path, "JPEG", quality=92)
                            ocr = scan_images_ocr([out_path])
                            txt = ocr.get(str(out_path), "").lower()
                            if any(b in txt for b in ["kulfy", "shutterstock", "getty", "alamy", "watermark"]):
                                out_path.unlink(missing_ok=True)
                                continue
                            return out_path
            except Exception:
                continue
    except Exception as e:
        print(f"Notice: Dynamic meme harvest failed: {e}")
    return None


def get_reaction_meme(
    emotion_or_text: str,
    used_memes: Optional[Set[str]] = None,
    cooldown_runs: int = 30,
) -> Optional[Path]:
    """
    Returns an authentic Telugu reaction meme Path matching the emotion.
    Respects:
      1. Single-use deduplication per run if used_memes set is provided.
      2. Multi-run persistent deduplication via data/used_memes.json with FIFO rotation.
      3. Fallback to fresh dynamic online meme search if all candidates are on cooldown.
    """
    if not MEMES_DIR.exists():
        return None

    if not emotion_or_text:
        matched_cat = "comedy"
    else:
        matched_cat = match_emotion_from_text(str(emotion_or_text))
        if not matched_cat:
            matched_cat = str(emotion_or_text).lower().strip()

    candidate_files = [fn for fn in EMOTION_MEME_MAP.get(matched_cat, []) if (MEMES_DIR / fn).exists()]
    if not candidate_files:
        candidate_files = [fn for fn in ["sunil_laughing.jpg", "babu_mohan_shock.jpg", "ali_funny.jpg", "brahmi_shocked.jpg", "venky_frustrated.jpg", "ms_narayana_facepalm.jpg"] if (MEMES_DIR / fn).exists()]
    if not candidate_files:
        candidate_files = [p.name for p in MEMES_DIR.glob("*.jpg")]

    # 1. Filter out candidates already used in the current run
    run_candidates = [
        fn for fn in candidate_files
        if used_memes is None or fn not in used_memes
    ]

    # 2. Check persistent cross-run history for anti-repetition rotation
    recent_history = load_persistent_used_memes(cooldown_runs=cooldown_runs)
    recent_set = set(recent_history[-cooldown_runs:] if len(recent_history) >= cooldown_runs else recent_history)

    # Prioritize candidates not used recently across past runs
    fresh_candidates = [fn for fn in run_candidates if fn not in recent_set]
    
    selected_fn = None
    if fresh_candidates:
        selected_fn = fresh_candidates[0]
    elif run_candidates:
        # Check stalest candidate
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

    # 3. Dynamic online search fallback if all local candidates are exhausted
    online_p = fetch_dynamic_online_meme(matched_cat)
    if online_p and online_p.exists():
        if used_memes is not None:
            used_memes.add(online_p.name)
        record_used_meme(online_p.name)
        return online_p

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
