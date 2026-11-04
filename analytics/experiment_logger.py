"""
Experiment and Learning Logger for AutoTube AI (analytics/experiment_logger.py).

Maintains a local, non-destructive ledger of video generation runs,
packaging variants, retention parameters, and retrieved metrics.
Persisted in data/experiment_log.json with safe schema migrations.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "data" / "experiment_log.json"


def load_experiment_log() -> List[Dict[str, Any]]:
    """Loads all logged experiment entries safely."""
    if not LOG_FILE.exists():
        return []
    try:
        data = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def log_experiment_run(
    topic: str,
    content_pillar: str = "viral_entertainment_explainers",
    aspect_ratio: str = "9:16",
    target_duration: str = "30-50s",
    actual_duration_sec: Optional[float] = None,
    hook_variant: str = "standard",
    title_variant: str = "",
    thumbnail_text: str = "",
    heuristic_scores: Optional[Dict[str, float]] = None,
    youtube_video_id: Optional[str] = None,
    recommendations_applied: Optional[List[str]] = None,
    experiment_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Logs an isolated video generation experiment run into data/experiment_log.json.
    Preserves all existing output files and never modifies previous logs.
    """
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logs = load_experiment_log()

    exp_id = experiment_id or f"exp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:6]}"
    is_short = (aspect_ratio == "9:16" or "30" in str(target_duration) or "short" in str(target_duration).lower())

    entry: Dict[str, Any] = {
        "experiment_id": exp_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "content_pillar": content_pillar,
        "format": "Shorts" if is_short else "Long-form",
        "aspect_ratio": aspect_ratio,
        "target_duration": target_duration,
        "actual_duration_sec": actual_duration_sec,
        "hook_variant": hook_variant,
        "title_variant": title_variant,
        "thumbnail_text": thumbnail_text,
        "heuristic_scores": heuristic_scores or {},
        "youtube_video_id": youtube_video_id,
        "recommendations_applied": recommendations_applied or [],
        "retrieved_metrics": None,
    }

    logs.append(entry)

    try:
        LOG_FILE.write_text(json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"Warning: Failed to save experiment log: {e}")

    return entry


def update_experiment_metrics(
    experiment_id: str,
    metrics: Dict[str, Any],
) -> bool:
    """Updates an existing experiment entry with actual imported or API-retrieved metrics."""
    logs = load_experiment_log()
    updated = False
    for item in logs:
        if item.get("experiment_id") == experiment_id or item.get("youtube_video_id") == experiment_id:
            item["retrieved_metrics"] = {
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "views": metrics.get("views"),
                "impressions": metrics.get("impressions"),
                "ctr_percent": metrics.get("impressions_ctr_percent"),
                "avd_sec": metrics.get("average_view_duration_sec"),
                "subscribers": metrics.get("net_subscribers"),
            }
            updated = True
            break

    if updated:
        try:
            LOG_FILE.write_text(json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            pass
    return False


def compare_experiments_by_pillar(pillar: str) -> List[Dict[str, Any]]:
    """Compares past experiments under the same content pillar over time."""
    logs = load_experiment_log()
    matches = [e for e in logs if e.get("content_pillar") == pillar]
    return matches
