"""
providers/timing_logger.py

Comprehensive stage timing profiler and free-tier quota monitor for AutoTube AI.
Logs stage durations to output/pipeline_timing.json and output/pipeline_timing.log.
Monitors API and LLM call counts against standard free-tier limits.
"""

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
TIMING_JSON_FILE = OUTPUT_DIR / "pipeline_timing.json"
TIMING_LOG_FILE = OUTPUT_DIR / "pipeline_timing.log"

_STAGE_TIMINGS: List[Dict[str, Any]] = []
_STAGE_START_TIMES: Dict[str, float] = {}

# Free tier reference limits
FREE_LIMITS = {
    "gemini": {"rpm": 15, "rpd": 1500, "desc": "Gemini Free Tier"},
    "groq": {"rpm": 30, "rpd": 14400, "desc": "Groq Free Tier (Llama 3.3 70B)"},
    "ollama": {"rpm": "unlimited", "rpd": "unlimited", "desc": "Local Ollama (100% Free)"},
    "edge_tts": {"rpm": "unlimited", "rpd": "unlimited", "desc": "Microsoft Edge Neural TTS (Free)"},
    "apify": {"monthly_usd": 5.0, "desc": "Apify Free Monthly Credit ($5)"},
}


def start_stage(stage_name: str) -> None:
    """Record start time of a pipeline stage."""
    _STAGE_START_TIMES[stage_name] = time.time()
    print(f"\n⏱️ [Stage Start] {stage_name}...")


def end_stage(stage_name: str, status: str = "success", error: Optional[str] = None) -> float:
    """Record end time and duration of a pipeline stage."""
    t_start = _STAGE_START_TIMES.pop(stage_name, None)
    if t_start is None:
        duration = 0.0
    else:
        duration = round(time.time() - t_start, 2)

    entry = {
        "stage": stage_name,
        "duration_seconds": duration,
        "status": status,
        "error": error,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _STAGE_TIMINGS.append(entry)
    print(f"⏱️ [Stage End] {stage_name} finished in {duration:.2f}s ({status})\n")
    return duration


@contextmanager
def time_stage(stage_name: str):
    """Context manager for timing pipeline stages."""
    start_stage(stage_name)
    err = None
    try:
        yield
    except Exception as e:
        err = str(e)
        end_stage(stage_name, status="failed", error=err)
        raise
    else:
        end_stage(stage_name, status="success")


def get_stage_timings() -> List[Dict[str, Any]]:
    return list(_STAGE_TIMINGS)


def clear_timings() -> None:
    global _STAGE_TIMINGS, _STAGE_START_TIMES
    _STAGE_TIMINGS = []
    _STAGE_START_TIMES = {}


def generate_pipeline_timing_report() -> Dict[str, Any]:
    """Compile stage timing metrics and free provider call counts, writing to disk."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from providers.tracker import get_provider_status
        provider_stats = get_provider_status()
    except Exception:
        provider_stats = {}

    total_pipeline_time = sum(s.get("duration_seconds", 0.0) for s in _STAGE_TIMINGS)

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_duration_seconds": round(total_pipeline_time, 2),
        "stages": _STAGE_TIMINGS,
        "provider_usage": provider_stats,
        "free_limits_reference": FREE_LIMITS,
    }

    try:
        TIMING_JSON_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as err:
        print(f"Notice: Could not write timing JSON: {err}")

    # Format human-readable table in log file
    lines = [
        "=" * 72,
        "               AUTOTUBE AI - PIPELINE TIMING & QUOTA REPORT             ",
        "=" * 72,
        f"Generated: {report['generated_at']}",
        f"Total Pipeline Execution Time: {total_pipeline_time:.2f}s ({total_pipeline_time/60:.2f} min)",
        "-" * 72,
        f"{'STAGE NAME':<40} {'DURATION':<12} {'STATUS':<10}",
        "-" * 72,
    ]

    for s in _STAGE_TIMINGS:
        stg = s.get("stage", "Unknown")[:38]
        dur = f"{s.get('duration_seconds', 0.0):.2f}s"
        stat = s.get("status", "ok")
        lines.append(f"{stg:<40} {dur:<12} {stat:<10}")

    lines.extend([
        "-" * 72,
        "                    API & FREE-TIER QUOTA USAGE                          ",
        "-" * 72,
        f"{'PROVIDER':<16} {'REQUESTS':<10} {'SUCCESS':<10} {'FAIL':<8} {'LIMIT / NOTES'}",
        "-" * 72,
    ])

    for prov, ref in FREE_LIMITS.items():
        stats = provider_stats.get(prov, {})
        reqs = stats.get("requests", 0)
        succ = stats.get("successes", 0)
        fails = stats.get("failures", 0)
        limit_note = ref.get("desc", "")
        lines.append(f"{prov:<16} {reqs:<10} {succ:<10} {fails:<8} {limit_note}")

    lines.append("=" * 72)
    log_text = "\n".join(lines) + "\n"

    try:
        TIMING_LOG_FILE.write_text(log_text, encoding="utf-8")
    except Exception:
        pass

    print(log_text)
    return report
