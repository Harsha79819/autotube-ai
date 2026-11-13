"""
Visual ladder: decides WHAT each scene shows and renders it with the Creator Canvas.

Rungs, top to bottom (first that applies wins):

  1. solo / split   entity has an emotion-matched cutout in data/entities/<slug>/
  2. name_card      a person is named but we have no cutout -> big name on a reaction
                    burst. We show NO face rather than a wrong or invented one.
  3. photo_card     no person in the scene and a REAL downloaded photo exists
                    (fallback-pool images, duplicates and AI images are excluded)
  4. typography     the punchline itself, big, on stage-blur / bokeh

Text-to-image (Pollinations/FLUX) is not a rung. In canvas mode it is switched off
for the whole pipeline (see ai_images_blocked), because diffusion models do not know
regional Telugu contestants and produce confident fake faces.

Modes (env AUTOTUBE_CANVAS): "1" force on, "0" force off, unset/"auto" = on only when
data/entities/ contains at least one entity. Tech-explainer videos therefore keep the
legacy path untouched.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw

from agents.entity_bank import get_bank
from agents.scene_planner import Scene, describe, plan_scenes

ROOT = Path(__file__).resolve().parent.parent
MOTIONS = ["push", "pull", "push", "pull"]  # background drift only; foreground layers never scale


# --------------------------------------------------------------------------- #
# Mode / policy
# --------------------------------------------------------------------------- #
def canvas_enabled() -> bool:
    mode = os.environ.get("AUTOTUBE_CANVAS", "auto").strip().lower()
    if mode in ("1", "true", "on", "yes"):
        return True
    if mode in ("0", "false", "off", "no"):
        return False
    return bool(get_bank().entities)


def ai_images_blocked() -> bool:
    """Zero-distortion policy: no text-to-image in canvas mode unless explicitly re-enabled."""
    if os.environ.get("AUTOTUBE_ALLOW_AI_IMAGES", "0") == "1":
        return False
    return canvas_enabled()


def write_placeholder(path: Path) -> None:
    """Neutral dark tile so asset-verification passes; canvas scenes never show it as-is."""
    img = Image.new("RGB", (1080, 1920), (14, 14, 26))
    ImageDraw.Draw(img).rectangle((0, 0, 1079, 1919), outline=(40, 40, 60), width=6)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=85)


# --------------------------------------------------------------------------- #
# Real-photo filter for the photo_card rung
# --------------------------------------------------------------------------- #
def _md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fallback_hashes(assets_dir: Path) -> set:
    fb = assets_dir / "fallback"
    return {_md5(p) for p in fb.glob("*") if p.is_file()} if fb.exists() else set()


def _frame_from_video(video: Path, dest: Path) -> Optional[Path]:
    import subprocess
    r = subprocess.run(["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(video), "-vframes", "1", "-q:v", "2", str(dest)],
                       capture_output=True, text=True)
    return dest if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0 else None


def _pick_photo(scene: Scene, images: List[Path], work: Path, banned: set, used: set) -> Optional[Path]:
    """First real, not-yet-used image among the visuals this scene covers, or any unused image in pool."""
    for vid in scene.visual_ids:
        if not (1 <= vid <= len(images)):
            continue
        p = images[vid - 1]
        if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
            p = _frame_from_video(p, work / f"frame_{vid}.jpg") or p
            if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
                continue
        try:
            digest = _md5(p)
            if digest in banned or digest in used:
                continue
            with Image.open(p) as im:
                if min(im.size) < 400:
                    continue
        except Exception:
            continue
        used.add(digest)
        return p

    # Pass 2: Look across any unused real photo in the entire images pool
    for p in images:
        if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
            continue
        try:
            digest = _md5(p)
            if digest in banned or digest in used:
                continue
            with Image.open(p) as im:
                if min(im.size) < 400:
                    continue
            used.add(digest)
            return p
        except Exception:
            continue

    return None


# --------------------------------------------------------------------------- #
# Public entry point used by video_agent.create_video
# --------------------------------------------------------------------------- #
def build_scene_clips(
    timed_sections: List[dict],
    images: List[Path],
    scene_clips_dir: Path,
    width: int,
    height: int,
    fps: int,
    transition_dur: float,
    assets_dir: Optional[Path] = None,
    overrides_path: Optional[Path] = None,
) -> Tuple[List[str], List[float], List[Scene]]:
    # 16:9 Long-Form Safety Guard: Creator Canvas is strictly for vertical 9:16 Shorts
    if width > height:
        raise ValueError(
            f"Creator Canvas is strictly for vertical 9:16 Shorts ({width}x{height} detected). "
            "Horizontal 16:9 Long-Form videos must use the cinematic documentary visual engine."
        )

    from agents.canvas_engine import compose_scene, render_scene_clip

    assets_dir = assets_dir or (ROOT / "assets")
    scenes = plan_scenes(timed_sections, get_bank(), overrides_path)
    print(describe(scenes))

    work = scene_clips_dir / "_layers"
    work.mkdir(parents=True, exist_ok=True)
    banned = _fallback_hashes(assets_dir)
    used: set = set()
    allow_photos = os.environ.get("AUTOTUBE_PHOTO_CARDS", "1") != "0"

    clips: List[str] = []
    durations: List[float] = []
    used_meme_count = 0
    for i, scene in enumerate(scenes):
        photo = None
        force = None
        if scene.layout == "broll":
            from utils.season_guard import is_bigg_boss_topic
            is_bb_scene = is_bigg_boss_topic(scene.narration) or bool(scene.entities)
            if is_bb_scene:
                from tools.meme_manager import get_reaction_meme, match_emotion_from_text
                emo_cat = match_emotion_from_text(scene.narration) or scene.emotion
                meme_p = None
                # Memes should only be used for punchy reaction moments (max 2 per video), never for serious/neutral narrative beats
                punchy_meme_cats = ("shocked", "overacting", "comedy", "roast", "crying", "headache", "suspicious", "angry")
                if emo_cat in punchy_meme_cats and used_meme_count < 2:
                    meme_p = get_reaction_meme(emo_cat, used_memes=used)
                if meme_p and meme_p.exists():
                    photo = meme_p
                    force = "broll"
                    used_meme_count += 1
                else:
                    photo = _pick_photo(scene, images, work, banned, used)
                    if photo:
                        force = "broll"
                    elif scene.entities:
                        force = "solo"
                    else:
                        force = "typography"
            else:
                photo = _pick_photo(scene, images, work, banned, used) if allow_photos else None
                if photo:
                    force = "broll"
                elif scene.entities:
                    force = "solo"
                else:
                    force = "typography"
        layers = compose_scene(scene, work, width, height, photo_path=photo, force=force)

        is_last = i == len(scenes) - 1
        is_hook = i == 0
        motion = "hook" if is_hook else MOTIONS[i % len(MOTIONS)]
        render_dur = scene.duration + (0 if is_last else transition_dur)
        out = scene_clips_dir / f"scene_{i:03d}_canvas_{layers.kind}.mp4"
        print(f"[{i + 1}/{len(scenes)}] {layers.kind:<16} {scene.duration:4.1f}s  {motion}"
              f"{'  [hook]' if is_hook else ''}")
        render_scene_clip(layers, out, render_dur, motion=motion, fps=fps,
                          width=width, height=height, is_hook=is_hook)
        clips.append(str(out))
        durations.append(scene.duration)
    return clips, durations, scenes
