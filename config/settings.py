"""Configuration Settings Loader for AutoTube AI.
Reads runtime flags from config/settings.json with safe defaults.
"""

import json
from pathlib import Path
from typing import Any, Dict

SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "SHORTS_TARGET_SEC": 38,
    "SHORTS_MIN_SEC": 30,
    "SHORTS_MAX_SEC": 48,
    "TONE_DEFAULT": "roast",
    "SHOW_CONTEXT": "auto",
    "CURRENT_SHOW_HASHTAGS": ["#BiggBossTelugu10", "#BB10", "#BiggBossTelugu"],
    "GOOGLE_IMAGES_MODE": "tier_b",
    "ALLOW_TIER_B": True,
    "TIER_B_MAX_SHARE": 0.30,
    "GOOGLE_QUERIES_PER_DAY": 90,
    "FACE_CONSENSUS": True,
    "ROAST_SFX_MAX": 3,
    "HUMOR_MIN_SCORE": 7,
    "BROLL_VIDEO_SHARE": 0.35,
    "ON_SCREEN_TEXT": True,
    "DELIVERY_MARKUP": True,
    "ENTITY_LIBRARY": True,
    "QUOTA_GUARD": True,
    "USE_SOCIAL_VISUALS": False,
    "APIFY_SEARCH_LIMIT": 35,
    "CLIP_SIMILARITY_THRESHOLD": 0.25,
    "ENTITY_CAPTION_BOOST": 0.15,
    # Non-breaking Content Intelligence & Retention Upgrade Flags (Disabled by Default)
    "ENABLE_CONTENT_INTELLIGENCE": False,
    "ENABLE_HOOK_OPTIMIZER": False,
    "ENABLE_PACKAGING_INTELLIGENCE": False,
    "ENABLE_FACT_CHECK_REVIEW": False,
    "ENABLE_EXPERIMENT_LOGGING": False,
    "STRICT_FACT_CHECK_ENFORCEMENT": False,
    "CONTENT_PILLARS": ["tollywood_celebrity", "behind_the_scenes", "viral_entertainment_explainers"],
}


def load_settings() -> Dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULT_SETTINGS)


def get_setting(key: str, default: Any = None) -> Any:
    settings = load_settings()
    if key in settings:
        return settings[key]
    return default if default is not None else DEFAULT_SETTINGS.get(key)


def update_setting(key: str, value: Any) -> None:
    settings = load_settings()
    settings[key] = value
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass

