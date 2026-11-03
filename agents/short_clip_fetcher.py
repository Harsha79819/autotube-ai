"""
agents/short_clip_fetcher.py - Dynamic Short Video Clip Fetcher

Fetches and prepares relevant 3-5 second short video clips for all scenes
in both YouTube Shorts (9:16) and Long-form (16:9) formats.

Hierarchy:
  1. Priority 1 (Contextual clips): Use X (Twitter) search queries via yt-dlp
     to scrape recent public 3-5s video clips tagged with contestant/show names.
  2. Priority 2 (Reaction/Stock): Use Pexels Video API / Pixabay Video API with
     vertical/portrait orientation for emotion-based scenes.
  3. Priority 3 (Memes): Fetch short reaction clips from Tenor/Meme archives
     for comedic/satirical lines.
  4. Resilient Fallback: Still photo with dynamic Ken Burns motion.

Specifications:
  - Duration: Strictly 3.0 to 5.0 seconds per clip (matching speech timestamps).
  - Aspect Ratio: 9:16 (1080x1920) or 16:9 (1920x1080), center-cropped, 30fps, -an.
  - Output: Saved sequentially as assets/1.mp4 ... assets/N.mp4 with matching 1.jpg keyframes.
"""

import os
import re
import json
import time
import shutil
import hashlib
import urllib.parse
import subprocess
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output"
ASSETS_DIR = ROOT_DIR / "assets"
CACHE_DIR = ROOT_DIR / "cache" / "video_clips"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


# ============================================================
# 1. SCENE SEGMENTATION & KEYWORD EXTRACTION (3-5 SECONDS)
# ============================================================

KNOWN_TELUGU_CONTESTANTS = {
    "చరణ్": "Charan",
    "నాగార్జున": "Nagarjuna",
    "అమాన్": "Aman",
    "ఆమన్": "Aman",
    "ఝాన్సీ": "Jhansi",
    "తాన్సీ": "Jhansi",
    "సుధీర్": "Sudheer",
    "రోహిత్": "Rohit",
    "అర్జున్ కళ్యాణ్": "Arjun Kalyan",
    "అర్జున్": "Arjun Kalyan",
    "అపూర్వ": "Apoorva",
    "త్రిగుణ్": "Thrigun",
    "శాలినీ": "Shalini",
}

EMOTION_KEYWORDS_MAP = [
    (r"మైండ్\s*బ్లాంక్|షాక్|షాకింగ్", "shocked face reaction", "mind blown reaction meme", "emotion"),
    (r"సర్కస్\s*కామెడీ|కామెడీ\s*షో|జోక్", "funny circus performance", "funny laughing meme reaction", "meme"),
    (r"కన్నీళ్లు|ఏడుపు|ఎమోషనల్", "crying man sad tears", "crying reaction meme", "emotion"),
    (r"స్నాక్స్|చిల్|హాయిగా", "eating snacks relaxed chill", "eating popcorn meme", "emotion"),
    (r"ఫేక్\s*వాకౌట్|వాకౌట్|బయటకు", "person walking away dramatic", "dramatic exit meme", "meme"),
    (r"ఓటింగ్\s*గ్రాఫ్|ఓటింగ్|పడిపోతే", "falling graph chart red", "shocked facepalm reaction", "emotion"),
    (r"సెలెక్టివ్\s*గ్రిల్లింగ్|గ్రిల్లింగ్|క్లాసులు", "serious host interrogating", "angry face intense reaction", "contextual"),
    (r"నామినేషన్\s*ఫ్లిప్|ఫ్లిప్|ట్విస్ట్", "shocked unexpected reveal", "plot twist reaction meme", "meme"),
    (r"బక్రా|మోసం|డ్రామా", "funny facepalm disbelief", "clown facepalm meme", "meme"),
    (r"కామెంట్|లైక్|షేర్|సబ్స్క్రైబ్", "youtube subscribe button animation", "thumbs up smiling happy", "emotion"),
]


def extract_keywords_from_scene_text(text: str, overall_context: str = "Bigg Boss Telugu") -> Dict[str, Any]:
    """
    Analyzes scene text and returns context keywords, emotion keywords, and meme keywords.
    MANDATORY RULE: Never query bare single contestant names alone.
    Always format as '{Contestant_Name} Bigg Boss Telugu' or '{Contestant_Name} Bigg Boss'.
    """
    clean_t = text.strip()

    # 1. Identify specific contestant / host (preventing clash celebrity false positives)
    found_person = None
    clean_low = clean_t.lower()
    if "రామ్ చరణ్" in clean_t or "ram charan" in clean_low:
        found_person = None
    elif "రోహిత్ శర్మ" in clean_t or "rohit sharma" in clean_low:
        found_person = None
    elif "అల్లు అర్జున్" in clean_t or "allu arjun" in clean_low:
        found_person = None
    else:
        for tel_name, eng_name in KNOWN_TELUGU_CONTESTANTS.items():
            if tel_name in clean_t:
                found_person = eng_name
                break

    # MANDATORY QUERY FORMAT: Append context tags strictly (e.g. 'Rohit Sahni Bigg Boss', 'Charan Bigg Boss Telugu')
    if found_person:
        try:
            from utils.season_guard import get_person_search_name
            context_query = get_person_search_name(found_person)
        except Exception:
            context_query = f"{found_person} Bigg Boss Telugu"
    else:
        context_query = f"{overall_context} highlights"

    # 2. Identify emotion & meme keywords
    emotion_query = "candid reaction shot"
    meme_query = "funny reaction meme"
    scene_type = "contextual" if found_person else "emotion"

    for pattern, emo, meme, stype in EMOTION_KEYWORDS_MAP:
        if re.search(pattern, clean_t, re.IGNORECASE):
            emotion_query = emo
            meme_query = meme
            if not found_person:
                scene_type = stype
            break

    return {
        "person_name": found_person,
        "context_query": context_query,
        "emotion_query": emotion_query,
        "meme_query": meme_query,
        "scene_type": scene_type,
    }


def segment_script_into_timed_scenes(
    script_text: str,
    audio_duration: float = 0.0,
    target_scene_dur: float = 4.0,
) -> List[Dict[str, Any]]:
    """
    Breaks down the script into 3 to 5 second visual scenes matching the audio timeline.
    """
    lines = [l.strip() for l in script_text.splitlines() if l.strip()]
    raw_sentences = []
    for l in lines:
        parts = re.split(r"(?<=[.!?।])\s+", l)
        for p in parts:
            p_clean = p.strip()
            if len(p_clean) >= 10:
                raw_sentences.append(p_clean)
            elif raw_sentences:
                raw_sentences[-1] += f" {p_clean}"
            elif p_clean:
                raw_sentences.append(p_clean)

    if not raw_sentences:
        raw_sentences = ["బిగ్ బాస్ తెలుగు లేటెస్ట్ హైలైట్స్"]

    if audio_duration <= 0.0:
        audio_duration = float(len(raw_sentences) * target_scene_dur)

    # Determine number of scenes so every scene is strictly bounded between 3.0s and 5.0s
    num_scenes = max(1, int(round(audio_duration / 4.0)))

    # If raw sentences count is less than needed scenes, split by commas/dashes
    if len(raw_sentences) < num_scenes:
        expanded = []
        for s in raw_sentences:
            sub = [p.strip() for p in re.split(r"[,—–\n]", s) if len(p.strip()) >= 8]
            if len(sub) > 1 and len(expanded) + len(sub) <= num_scenes + 3:
                expanded.extend(sub)
            else:
                expanded.append(s)
        raw_sentences = expanded

    # Re-evaluate final scene count bounded to audio length
    final_count = max(1, len(raw_sentences))
    step = audio_duration / final_count

    scenes = []
    for i in range(1, final_count + 1):
        s_text = raw_sentences[i - 1] if i <= len(raw_sentences) else raw_sentences[-1]
        start_t = round((i - 1) * step, 2)
        end_t = round(audio_duration if i == final_count else i * step, 2)
        dur = max(3.0, min(5.0, round(end_t - start_t, 2)))

        kw = extract_keywords_from_scene_text(s_text)
        scenes.append({
            "scene_id": i,
            "spoken_text": s_text,
            "start_time": start_t,
            "end_time": end_t,
            "duration": dur,
            "keywords": kw,
        })

    return scenes


# ============================================================
# 2. PRIORITY 1: X (TWITTER) VIDEO SCRAPING VIA YT-DLP
# ============================================================

def search_twitter_video_urls(query: str, max_candidates: int = 4) -> List[str]:
    """
    Searches web indices for recent public X (Twitter) status URLs related to the query.
    """
    clean_q = re.sub(r"[^\w\s-]", " ", query).strip()
    search_queries = [
        f"{clean_q} twitter status",
        f"{clean_q} x.com video",
        f"Bigg Boss Telugu {clean_q} twitter",
    ]

    urls = []
    headers = {"User-Agent": USER_AGENT}

    for sq in search_queries:
        if len(urls) >= max_candidates:
            break
        try:
            p = urllib.parse.quote(sq)
            resp = requests.get(f"https://search.yahoo.com/search?p={p}", headers=headers, timeout=6)
            if resp.status_code == 200:
                ru_matches = re.findall(r"RU=(https?%3a%2f%2f[^/]+%2f[^/]+%2fstatus%2f\d+)", resp.text, re.IGNORECASE)
                for ru in ru_matches:
                    dec = urllib.parse.unquote(ru)
                    dec = re.sub(r"https?://(?:www\.)?twitter\.com", "https://x.com", dec)
                    if dec not in urls:
                        urls.append(dec)
                        if len(urls) >= max_candidates:
                            break
        except Exception:
            pass

    return urls


def download_and_trim_ytdlp(
    media_url: str,
    output_path: Path,
    duration: float = 4.0,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> bool:
    """
    Downloads a video from a tweet or video platform URL via yt-dlp,
    trims strictly between 3-5 seconds, center-crops to target resolution,
    and strips audio (-an).
    """
    ytdlp_bin = shutil.which("yt-dlp") or str(ROOT_DIR / ".venv" / "bin" / "yt-dlp")
    if not os.path.exists(ytdlp_bin):
        return False

    url_hash = hashlib.md5(media_url.encode("utf-8")).hexdigest()[:10]
    raw_tmp = CACHE_DIR / f"raw_tw_{url_hash}.mp4"

    # 1. Download short section via yt-dlp
    if not raw_tmp.exists() or raw_tmp.stat().st_size < 10000:
        dur_ceil = int(round(duration)) + 2
        sec_spec = f"*00:00:01-00:00:{max(4, dur_ceil):02d}"
        cmd_dl = [
            ytdlp_bin,
            "--no-warnings",
            "--quiet",
            "--download-sections", sec_spec,
            "--force-keyframes-at-cuts",
            "-f", "bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best",
            "-o", str(raw_tmp),
            media_url,
        ]
        try:
            r = subprocess.run(cmd_dl, capture_output=True, text=True, timeout=20)
            if r.returncode != 0 or not raw_tmp.exists() or raw_tmp.stat().st_size < 10000:
                cmd_full = [
                    ytdlp_bin,
                    "--no-warnings",
                    "--quiet",
                    "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]/best",
                    "-o", str(raw_tmp),
                    media_url,
                ]
                subprocess.run(cmd_full, capture_output=True, text=True, timeout=18)
        except Exception:
            pass

    if not raw_tmp.exists() or raw_tmp.stat().st_size < 10000:
        return False

    # 2. Normalize aspect ratio & trim using FFmpeg
    vf_filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
        f"fps={fps}",
        "setsar=1",
        "format=yuv420p",
    ]
    cmd_ff = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(raw_tmp),
        "-vf", ",".join(vf_filters),
        "-t", str(duration),
        "-an",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "18",
        str(output_path),
    ]

    try:
        res = subprocess.run(cmd_ff, capture_output=True, text=True, timeout=20)
        return bool(res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 10000)
    except Exception:
        return False


def fetch_priority1_twitter_clip(
    query: str,
    output_path: Path,
    duration: float = 4.0,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """Attempts to find and download a contextual video clip from X (Twitter) using yt-dlp."""
    urls = search_twitter_video_urls(query, max_candidates=3)
    for u in urls:
        if download_and_trim_ytdlp(u, output_path, duration=duration, width=width, height=height):
            print(f"🎬 [Priority 1: X Clip] Downloaded: {u} -> {output_path.name} ({duration}s)")
            return True
    return False


# ============================================================
# 3. PRIORITY 2: PEXELS / PIXABAY VERTICAL STOCK VIDEO API
# ============================================================

def fetch_priority2_pexels_clip(
    query: str,
    output_path: Path,
    duration: float = 4.0,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """Fetches high-definition portrait stock video from Pexels Video API."""
    try:
        from providers.image import search_pexels_videos
        orientation = "portrait" if height > width else "landscape"
        res = search_pexels_videos(query, orientation=orientation, per_page=4)
        if not res or not res.get("video_url"):
            return False

        v_url = res["video_url"]
        vf_filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
            "fps=30",
            "setsar=1",
            "format=yuv420p",
        ]
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", v_url,
            "-vf", ",".join(vf_filters),
            "-t", str(duration),
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "18",
            str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if r.returncode == 0 and output_path.exists() and output_path.stat().st_size > 10000:
            print(f"🎬 [Priority 2: Pexels Video] Sourced '{query}': {output_path.name} ({duration}s)")
            return True
    except Exception as err:
        print(f"⚠️ Pexels video notice ({query}): {err}")
    return False


# ============================================================
# 4. PRIORITY 3: REACTION MEMES / GIFS (TENOR MP4)
# ============================================================

def fetch_priority3_meme_clip(
    query: str,
    output_path: Path,
    duration: float = 4.0,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """Fetches comedic reaction meme MP4s from Tenor or public reaction archives."""
    clean_q = re.sub(r"[^\w\s-]", "", query).strip().replace(" ", "-")
    url = f"https://tenor.com/search/{clean_q}-gifs"
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            mp4_urls = list(dict.fromkeys(re.findall(r"https?://media\.tenor\.com/[^\" \x27]+\.mp4", resp.text)))
            for mp4_url in mp4_urls[:3]:
                vf_filters = [
                    f"scale={width}:{height}:force_original_aspect_ratio=increase",
                    f"crop={width}:{height}",
                    "fps=30",
                    "setsar=1",
                    "format=yuv420p",
                ]
                cmd = [
                    "ffmpeg", "-y",
                    "-stream_loop", "-1",
                    "-i", mp4_url,
                    "-vf", ",".join(vf_filters),
                    "-t", str(duration),
                    "-an",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "18",
                    str(output_path),
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                if r.returncode == 0 and output_path.exists() and output_path.stat().st_size > 10000:
                    print(f"🎬 [Priority 3: Meme Reaction] Sourced '{query}': {output_path.name} ({duration}s)")
                    return True
    except Exception as err:
        print(f"⚠️ Tenor meme notice ({query}): {err}")
    return False


# ============================================================
# 5. RESILIENT FALLBACK: STILL PHOTO + KEN BURNS MOTION
# ============================================================

def make_fallback_motion_clip(
    scene_idx: int,
    output_path: Path,
    duration: float = 4.0,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """Converts existing still asset (assets/{i}.jpg or fallback) into a motion MP4."""
    src_jpg = ASSETS_DIR / f"{scene_idx}.jpg"
    if not src_jpg.exists() or src_jpg.stat().st_size < 1000:
        fallback_pool = sorted((ASSETS_DIR / "fallback").glob("*.jpg"))
        if fallback_pool:
            src_jpg = fallback_pool[(scene_idx - 1) % len(fallback_pool)]

    if not src_jpg.exists():
        return False

    try:
        from ken_burns import prepare_scene_clip
        prepare_scene_clip(
            media_path=src_jpg,
            output_path=output_path,
            duration_seconds=duration,
            direction="zoom_in",
            width=width,
            height=height,
            fps=30,
            is_hook=(scene_idx == 1),
        )
        return bool(output_path.exists() and output_path.stat().st_size > 10000)
    except Exception:
        return False


# ============================================================
# 6. UNIVERSAL ORCHESTRATOR WITH CONCURRENCY
# ============================================================

def _process_single_scene(
    scene: Dict[str, Any],
    width: int,
    height: int,
) -> Dict[str, Any]:
    """Worker function for fetching and processing a single scene's video clip."""
    idx = scene["scene_id"]
    dur = scene["duration"]
    kw = scene["keywords"]
    s_text = scene["spoken_text"]
    out_clip = ASSETS_DIR / f"{idx}.mp4"
    out_jpg = ASSETS_DIR / f"{idx}.jpg"

    fetched = False
    chosen_source = "none"

    if kw["scene_type"] == "contextual":
        if fetch_priority1_twitter_clip(kw["context_query"], out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "twitter_x_ytdlp"
        elif fetch_priority2_pexels_clip(kw["emotion_query"], out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "pexels_stock_video"
        elif fetch_priority3_meme_clip(kw["meme_query"], out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "tenor_meme_clip"
    elif kw["scene_type"] == "meme":
        if fetch_priority3_meme_clip(kw["meme_query"], out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "tenor_meme_clip"
        elif fetch_priority2_pexels_clip(kw["emotion_query"], out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "pexels_stock_video"
        elif fetch_priority1_twitter_clip(kw["context_query"], out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "twitter_x_ytdlp"
    else:
        if fetch_priority2_pexels_clip(kw["emotion_query"], out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "pexels_stock_video"
        elif fetch_priority3_meme_clip(kw["meme_query"], out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "tenor_meme_clip"
        elif fetch_priority1_twitter_clip(kw["context_query"], out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "twitter_x_ytdlp"

    if not fetched:
        if make_fallback_motion_clip(idx, out_clip, duration=dur, width=width, height=height):
            fetched = True
            chosen_source = "still_photo_motion"
        else:
            cmd_gen = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=0x111827:s={width}x{height}:d={dur}:r=30",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
                str(out_clip)
            ]
            subprocess.run(cmd_gen, capture_output=True, check=False)
            chosen_source = "color_canvas"

    # Extract high-res keyframe jpg for preview & downstream tools
    if out_clip.exists() and out_clip.stat().st_size > 0:
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(out_clip), "-vframes", "1", "-q:v", "2", str(out_jpg)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
            )
        except Exception:
            pass

    return {
        "scene_id": idx,
        "spoken_text": s_text,
        "start_time": scene["start_time"],
        "end_time": scene["end_time"],
        "duration": dur,
        "clip_source": chosen_source,
        "file_path": str(out_clip),
        "keyframe_path": str(out_jpg),
        "keywords": kw,
    }


def fetch_and_prepare_all_scene_clips(
    script_path: str = "output/script.txt",
    audio_path: str = "output/voice.mp3",
    aspect_ratio: str = "9:16",
    topic: str = "Bigg Boss Telugu",
    max_workers: int = 4,
    script_text: Optional[str] = None,
    voice_audio_path: Optional[str] = None,
    *args,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Parallel End-to-End Orchestrator:
    Downloads and prepares video clips for every scene in parallel.
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    if voice_audio_path and not audio_path:
        audio_path = voice_audio_path
    elif voice_audio_path and audio_path == "output/voice.mp3":
        audio_path = voice_audio_path

    if aspect_ratio == "9:16":
        width, height = 1080, 1920
    elif aspect_ratio == "16:9":
        width, height = 1920, 1080
    else:
        width, height = 1080, 1080

    if not script_text:
        candidate_paths = [Path(script_path), OUTPUT_DIR / "script.txt", OUTPUT_DIR / "clean_script.txt"]
        for cp in candidate_paths:
            if cp.exists() and cp.read_text(encoding="utf-8").strip():
                script_text = cp.read_text(encoding="utf-8").strip()
                break

    if not script_text:
        script_text = f"{topic} లేటెస్ట్ అప్‌డేట్స్ మరియు రియాక్షన్స్"

    audio_dur = 0.0
    if audio_path and os.path.exists(str(audio_path)):
        try:
            p_res = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio_path)],
                capture_output=True, text=True, timeout=8
            )
            audio_dur = float(p_res.stdout.strip())
        except Exception:
            pass

    scenes = segment_script_into_timed_scenes(script_text, audio_duration=audio_dur, target_scene_dur=4.0)
    print("=" * 70)
    print(f"🎬 [Short Video Clip Fetcher] Processing {len(scenes)} scenes ({audio_dur:.1f}s audio, {aspect_ratio}, {max_workers} workers)")
    print("=" * 70)

    # Process scenes in parallel
    results_map = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_single_scene, sc, width, height): sc["scene_id"] for sc in scenes}
        for future in concurrent.futures.as_completed(futures):
            s_id = futures[future]
            try:
                rec = future.result()
                results_map[s_id] = rec
                print(f"✅ Scene {s_id}/{len(scenes)} complete -> [{rec['clip_source']}] {Path(rec['file_path']).name}")
            except Exception as e:
                print(f"⚠️ Scene {s_id} error: {e}")

    manifest = [results_map[sc["scene_id"]] for sc in scenes if sc["scene_id"] in results_map]

    # Build section_map and visual_plan strings
    section_map_entries = []
    visual_plan_entries = []
    for rec in manifest:
        idx = rec["scene_id"]
        s_text = rec["spoken_text"]
        chosen_source = rec["clip_source"]
        kw = rec["keywords"]
        section_map_entries.append(f"SECTION {idx} | VISUAL {idx}\n{s_text}\n")
        visual_plan_entries.append(f"Visual {idx}: [{chosen_source.upper()}] {kw['context_query']} / {kw['emotion_query']}")

    (OUTPUT_DIR / "section_map.txt").write_text("\n".join(section_map_entries), encoding="utf-8")
    (OUTPUT_DIR / "visual_plan.txt").write_text("\n".join(visual_plan_entries), encoding="utf-8")
    (OUTPUT_DIR / "video_clips_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"✨ [Short Video Clip Fetcher Complete] Saved {len(manifest)} clips to assets/ matching audio timeline.")
    print("=" * 70)
    return manifest


if __name__ == "__main__":
    fetch_and_prepare_all_scene_clips()
