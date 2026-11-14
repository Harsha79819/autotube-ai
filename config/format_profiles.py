"""
AutoTube AI - Format Profiles & Dynamic Video Configuration (config/format_profiles.py)
Derived from target duration, aspect ratio, and format type (Short vs Long-Form).
"""
import re
import math
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List


@dataclass
class FormatProfile:
    # Core identity
    format_type: str            # "short" or "long-form"
    target_seconds: float       # Representative target duration in seconds (e.g. 75.0 for 60-90s)
    min_seconds: float          # Hard lower bound (tolerance -10% or explicit)
    max_seconds: float          # Hard upper bound (tolerance +10% or explicit)
    
    # Visual specs
    aspect_ratio: str           # "9:16" or "16:9" or "1:1"
    width: int                  # 1080 or 1920
    height: int                 # 1920 or 1080
    min_clip_duration: float    # 2.0s for shorts, 4.0s for long-form
    max_clip_duration: float    # 3.5s for shorts, 8.0s for long-form
    recommended_clips: int      # math.ceil(target_seconds / 3.0) for shorts
    
    # Script & Pacing specs
    words_per_second_min: float # 2.6 for shorts, 2.5 for long-form
    words_per_second_max: float # 2.8 for shorts, 2.7 for long-form
    min_words: int              # Target words lower bound (-10%)
    max_words: int              # Target words upper bound (+10%)
    target_words: int           # Nominal target words
    max_words_per_sentence: int # 10-12 for shorts, 20 for long-form
    hook_max_seconds: float     # 3.0s for shorts, 15.0s for long-form
    cta_duration_seconds: float # 3.0-4.0s at end
    has_chapters: bool          # True for long-form
    pattern_interrupt_interval: float # 90.0s for long-form, 0.0 for shorts
    
    # Audio specs
    voice_speed_rate: str       # "+8%" to "+10%" (1.05x-1.1x)
    max_pause_duration: float   # 0.3s
    music_ducking_db: float     # -18.0 to -22.0 dB
    target_lufs: float          # -14.0 LUFS
    
    # Captions & Safe Area
    caption_style: str          # "karaoke_highlight" (2-4 words) or "standard_multiline"
    safe_area_top_pct: float    # 0.15 (15% clear from top)
    safe_area_bottom_pct: float # 0.20 (20% clear from bottom)
    safe_area_center_pct: float # 0.80 (center 80% active width)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "format_type": self.format_type,
            "target_seconds": self.target_seconds,
            "min_seconds": self.min_seconds,
            "max_seconds": self.max_seconds,
            "aspect_ratio": self.aspect_ratio,
            "resolution": f"{self.width}x{self.height}",
            "min_words": self.min_words,
            "max_words": self.max_words,
            "target_words": self.target_words,
            "recommended_clips": self.recommended_clips,
            "max_words_per_sentence": self.max_words_per_sentence,
            "target_lufs": self.target_lufs,
        }


def parse_duration_to_seconds(raw_duration: Any) -> Tuple[float, float, float]:
    """
    Parses any duration string or number into (min_sec, target_sec, max_sec).
    Supports: "30-50s", "60-90s", "2-4m", "6-9m", 60, "75", etc.
    """
    if isinstance(raw_duration, (int, float)):
        val = float(raw_duration)
        return val * 0.9, val, val * 1.1

    s = str(raw_duration).lower().strip()
    s = s.replace("–", "-").replace("—", "-")

    # Range with minutes: "6-9m", "2-4 minutes", "6-9 minutes"
    m_min_range = re.search(r"(\d+)(?:\.(\d+))?\s*-\s*(\d+)(?:\.(\d+))?\s*(?:m|min)", s)
    if m_min_range:
        lo = float(m_min_range.group(1)) * 60.0
        hi = float(m_min_range.group(3)) * 60.0
        return lo, (lo + hi) / 2.0, hi

    # Single minute: "6m", "5 min"
    m_min_single = re.search(r"(\d+)(?:\.(\d+))?\s*(?:m|min)", s)
    if m_min_single:
        mid = float(m_min_single.group(1)) * 60.0
        return mid * 0.9, mid, mid * 1.1

    # Range with seconds: "60-90s", "30-50s", "45-55s"
    m_sec_range = re.search(r"(\d+)\s*-\s*(\d+)\s*(?:s|sec)?", s)
    if m_sec_range:
        lo = float(m_sec_range.group(1))
        hi = float(m_sec_range.group(2))
        return lo, (lo + hi) / 2.0, hi

    # Single seconds: "60s", "90", "45"
    m_sec_single = re.search(r"(\d+)\s*(?:s|sec)?", s)
    if m_sec_single:
        mid = float(m_sec_single.group(1))
        return mid * 0.9, mid, mid * 1.1

    # Defaults: 60-90s if explicitly specified or spotlight/full story, 120-150s, 6-9m if long-form
    if "120-150" in s or "120–150" in s or "120 to 150" in s or "2-2.5" in s:
        return 115.0, 135.0, 155.0
    if "spotlight" in s or "full" in s or "60-90" in s or "60" in s or "90" in s or "extended" in s:
        return 60.0, 75.0, 90.0
    if "6-9" in s or "long-form" in s or "history" in s:
        return 360.0, 450.0, 540.0
    if "2-4" in s:
        return 120.0, 180.0, 240.0

    # Default Shorts standard: 25-40s (Target: 35s, Hard Max: 45s)
    return 25.0, 35.0, 45.0


def get_format_profile(
    target_duration: Any = "30-50s",
    aspect_ratio: str = "9:16",
    format_type: Optional[str] = None,
    language: str = "english",
    **kwargs,
) -> FormatProfile:
    """
    Derives the complete FormatProfile given target duration, aspect ratio, format, and language.
    YouTube Studio Virality Calibration: Defaults Shorts to 30-50s (Target: 35-42s, hard max 45s, 65-90 words).
    """
    min_s, target_s, max_s = parse_duration_to_seconds(target_duration)

    # Determine format_type if not explicitly supplied
    if not format_type:
        if aspect_ratio == "16:9" or target_s >= 300.0 or "long" in str(target_duration).lower():
            format_type = "long-form"
        else:
            format_type = "short"
    else:
        format_type = format_type.lower().strip()

    lang_str = str(language or "").lower()
    is_indic = any(ind in lang_str for ind in ("telugu", "hindi", "tamil", "kannada", "malayalam", "bengali", "marathi"))

    if format_type == "long-form" or target_s >= 300.0:
        # LONG-FORM PROFILE (6+ minutes, default 16:9 1920x1080)
        w, h = (1920, 1080) if aspect_ratio != "9:16" else (1080, 1920)
        wps_min = 2.0 if is_indic else 2.5
        wps_max = 2.3 if is_indic else 2.7
        nominal_wps = 2.1 if is_indic else 2.6
        if target_s >= 300.0:
            # 6-9 minute target: strictly enforce 900-1200+ words
            min_words = max(900, int(min_s * wps_min))
            nominal_words = max(1050, int(target_s * nominal_wps))
            max_words = max(1350, int(max_s * wps_max * 1.10))
            clips = max(35, math.ceil(target_s / 10.0))
        else:
            nominal_words = int(target_s * nominal_wps)
            min_words = int(min_s * wps_min * 0.90)  # -10% tolerance
            max_words = int(max_s * wps_max * 1.10)  # +10% tolerance
            clips = max(20, math.ceil(target_s / 6.0))

        return FormatProfile(
            format_type="long-form",
            target_seconds=round(target_s, 1),
            min_seconds=round(min_s * 0.90, 1),
            max_seconds=round(max_s * 1.10, 1),
            aspect_ratio=aspect_ratio,
            width=w,
            height=h,
            min_clip_duration=4.0,
            max_clip_duration=8.0,
            recommended_clips=clips,
            words_per_second_min=wps_min,
            words_per_second_max=wps_max,
            min_words=min_words,
            max_words=max_words,
            target_words=nominal_words,
            max_words_per_sentence=20,
            hook_max_seconds=15.0,
            cta_duration_seconds=5.0,
            has_chapters=True,
            pattern_interrupt_interval=90.0,
            voice_speed_rate="+0%",
            max_pause_duration=0.5,
            music_ducking_db=-20.0,
            target_lufs=-14.0,
            caption_style="standard_multiline",
            safe_area_top_pct=0.10,
            safe_area_bottom_pct=0.15,
            safe_area_center_pct=0.85,
        )
    else:
        # SHORT PROFILE (YouTube Studio Retention: 30-50s, 60-90s, or Extended 120-150s)
        w, h = (1080, 1920) if aspect_ratio != "16:9" else (1920, 1080)
        wps_min = 1.8 if is_indic else 2.4
        wps_max = 2.1 if is_indic else 2.8
        nominal_wps = 1.95 if is_indic else 2.6
        nominal_words = int(target_s * nominal_wps)

        if target_s <= 52.0:
            # High-retention viral window: 25-50s (Target: 35-42s, Spoken ~30-44s)
            min_words = max(55, int(min_s * wps_min))
            max_words = min(92, int(max_s * wps_max))
            clips = max(8, math.ceil(min(target_s, 42.0) / 2.0))
        elif target_s <= 95.0:
            # 60-90s Shorts Profile (Strictly 60-88s duration envelope)
            min_words = max(120, int(min_s * wps_min))
            max_words = min(160 if is_indic else 185, int(max_s * wps_max))
            clips = max(12, min(16, math.ceil(target_s / 5.0)))
        elif target_s <= 165.0:
            # 120-150s Extended Shorts (YouTube Shorts now officially supports up to 3 mins / 180s)
            min_words = max(230, int(min_s * wps_min))
            max_words = min(360, int(max_s * wps_max))
            clips = max(20, math.ceil(target_s / 5.5))
        else:
            # Extended Shorts
            min_words = int(min_s * wps_min * 0.90)
            max_words = int(max_s * wps_max * 1.10)
            clips = max(22, math.ceil(target_s / 4.0))

        return FormatProfile(
            format_type="short",
            target_seconds=round(target_s, 1),
            min_seconds=round(min_s, 1),
            max_seconds=round(max_s, 1),
            aspect_ratio=aspect_ratio,
            width=w,
            height=h,
            min_clip_duration=1.5,
            max_clip_duration=2.5,
            recommended_clips=clips,
            words_per_second_min=wps_min,
            words_per_second_max=wps_max,
            min_words=min_words,
            max_words=max_words,
            target_words=nominal_words,
            max_words_per_sentence=10,
            hook_max_seconds=2.5,
            cta_duration_seconds=3.0,
            has_chapters=False,
            pattern_interrupt_interval=0.0,
            voice_speed_rate="+8%",
            max_pause_duration=0.25,
            music_ducking_db=-20.0,
            target_lufs=-14.0,
            caption_style="karaoke_highlight",
            safe_area_top_pct=0.15,
            safe_area_bottom_pct=0.20,
            safe_area_center_pct=0.80,
        )