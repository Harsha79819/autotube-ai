"""
GitHub Actions Quota Tracker (utils/github_quota.py)
Monitors 2,000 monthly free compute minutes for AutoTube AI.
"""

import os
import json
import calendar
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"
USAGE_FILE = LOGS_DIR / "github_actions_usage.json"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_days_until_reset() -> int:
    """Computes days remaining until the 1st of next month."""
    today = date.today()
    _, num_days = calendar.monthrange(today.year, today.month)
    return max(1, num_days - today.day + 1)


def load_local_usage() -> Dict[str, Any]:
    """Loads local month usage from JSON."""
    month_key = datetime.now().strftime("%Y-%m")
    default_data = {
        "month": month_key,
        "included_minutes": 2000,
        "minutes_used": 0,
        "runs": [],
    }

    if USAGE_FILE.exists():
        try:
            data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
            if data.get("month") == month_key:
                return data
        except Exception:
            pass

    return default_data


def save_local_usage(data: Dict[str, Any]):
    """Saves local month usage."""
    try:
        USAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def record_workflow_execution(slot_id: str, duration_seconds: float):
    """Records an executed workflow run and accumulates minutes."""
    data = load_local_usage()
    mins = max(1, int(round(duration_seconds / 60.0)))
    data["minutes_used"] = data.get("minutes_used", 0) + mins
    data.setdefault("runs", []).append({
        "timestamp": datetime.now().isoformat(),
        "slot_id": slot_id,
        "duration_seconds": round(duration_seconds, 1),
        "billed_minutes": mins,
    })
    save_local_usage(data)


def get_github_quota_status() -> Dict[str, Any]:
    """
    Returns unified quota metrics:
      - included_minutes (2000)
      - minutes_used
      - minutes_remaining
      - pct_used
      - days_until_reset
    """
    usage = load_local_usage()
    included = usage.get("included_minutes", 2000)
    used = usage.get("minutes_used", 0)

    # If GitHub PAT is set, attempt live API query
    token = os.getenv("GITHUB_TOKEN")
    user = os.getenv("GITHUB_USER")
    if token and user:
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }
            res = requests.get(
                f"https://api.github.com/users/{user}/settings/billing/actions",
                headers=headers,
                timeout=5,
            )
            if res.status_code == 200:
                gh_d = res.json()
                used = gh_d.get("total_minutes_used", used)
                included = gh_d.get("included_minutes", included)
        except Exception:
            pass

    rem = max(0, included - used)
    pct = round((used / included * 100.0) if included > 0 else 0.0, 1)

    return {
        "included_minutes": included,
        "minutes_used": used,
        "minutes_remaining": rem,
        "pct_used": pct,
        "days_until_reset": get_days_until_reset(),
    }
