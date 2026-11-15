"""
AutoTube AI - Real-Time Pipeline Companion & Live Telemetry Agent (agents/companion_agent.py)

Maintains real-time execution state for the floating modern AI Butterfly Companion widget.
Guarantees zero-lag status streaming across Streamlit, WebSockets, and static client polling.
"""

import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "output"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STATUS_FILE_STATIC = STATIC_DIR / "pipeline_status.json"
STATUS_FILE_OUTPUT = OUTPUT_DIR / "pipeline_status.json"

_STATUS_LOCK = threading.Lock()
_PIPELINE_START_TIME = 0.0

DEFAULT_STATUS: Dict[str, Any] = {
    "is_running": False,
    "stage": "Studio Ready",
    "step_number": 0,
    "total_steps": 7,
    "percent": 100,
    "current_task": "Studio Ready: Choose a topic and create video!",
    "next_task": "Script generation with Groq AI",
    "details": "Ready to compose 4K high-retention video with natural voice.",
    "elapsed_sec": 0,
    "updated_at": time.time(),
    "last_run_result": "Success",
}


def update_companion_status(
    stage: str,
    percent: int,
    current_task: str,
    next_task: str = "",
    details: str = "",
    is_running: bool = True,
    step_number: int = 1,
    total_steps: int = 7,
) -> Dict[str, Any]:
    """
    Updates the live telemetry state written to both static/ and output/ directories.
    Thread-safe and non-blocking for high-throughput pipeline stages.
    """
    global _PIPELINE_START_TIME

    with _STATUS_LOCK:
        now = time.time()
        if is_running:
            if _PIPELINE_START_TIME <= 0:
                _PIPELINE_START_TIME = now
            elapsed = int(now - _PIPELINE_START_TIME)
        else:
            elapsed = int(now - _PIPELINE_START_TIME) if _PIPELINE_START_TIME > 0 else 0
            _PIPELINE_START_TIME = 0.0

        payload: Dict[str, Any] = {
            "is_running": is_running,
            "stage": stage,
            "step_number": step_number,
            "total_steps": total_steps,
            "percent": max(0, min(100, int(percent))),
            "current_task": current_task,
            "next_task": next_task,
            "details": details,
            "elapsed_sec": elapsed,
            "updated_at": now,
        }

        try:
            raw = json.dumps(payload, indent=2, ensure_ascii=False)
            STATUS_FILE_STATIC.write_text(raw, encoding="utf-8")
            STATUS_FILE_OUTPUT.write_text(raw, encoding="utf-8")
        except Exception as e:
            print(f"⚠️ Companion status write notice: {e}")

        return payload


def get_companion_status() -> Dict[str, Any]:
    """Reads current companion status payload safely."""
    with _STATUS_LOCK:
        if STATUS_FILE_STATIC.exists():
            try:
                return json.loads(STATUS_FILE_STATIC.read_text(encoding="utf-8"))
            except Exception:
                pass
        return dict(DEFAULT_STATUS)


def reset_companion_status(last_result: str = "Completed successfully") -> None:
    """Resets companion status to idle state after pipeline run completes."""
    global _PIPELINE_START_TIME
    with _STATUS_LOCK:
        _PIPELINE_START_TIME = 0.0
        payload = dict(DEFAULT_STATUS)
        payload["is_running"] = False
        payload["percent"] = 100
        payload["last_run_result"] = last_result
        payload["updated_at"] = time.time()
        try:
            raw = json.dumps(payload, indent=2, ensure_ascii=False)
            STATUS_FILE_STATIC.write_text(raw, encoding="utf-8")
            STATUS_FILE_OUTPUT.write_text(raw, encoding="utf-8")
        except Exception:
            pass
