"""
AutoTube AI - Provider Health & Quota Tracker (providers/tracker.py)
Monitors API latency, quotas, fallbacks, and step executions across all external providers.
"""

import time
from collections import defaultdict

_PROVIDER_METRICS = defaultdict(lambda: {
    "requests": 0,
    "successes": 0,
    "failures": 0,
    "last_error": None,
    "last_used": 0,
    "last_latency_ms": 0,
})

_STEP_AUDIT_LOG = []
_LATEST_STEP_PROVIDERS = {}


def record_call(provider_name: str, success: bool, error: str = None, duration_ms: float = 0.0):
    entry = _PROVIDER_METRICS[provider_name]
    entry["requests"] += 1
    entry["last_used"] = time.time()
    entry["last_latency_ms"] = round(duration_ms, 1)
    if success:
        entry["successes"] += 1
    else:
        entry["failures"] += 1
        entry["last_error"] = str(error)


def record_step_provider(step_name: str, provider_name: str, duration_ms: float = 0.0, is_fallback: bool = False, note: str = ""):
    """Record which provider successfully served a given pipeline step."""
    event = {
        "step": step_name,
        "provider": provider_name,
        "duration_ms": round(duration_ms, 1),
        "is_fallback": is_fallback,
        "note": note,
        "timestamp": time.time(),
    }
    _STEP_AUDIT_LOG.append(event)
    _LATEST_STEP_PROVIDERS[step_name] = event
    if len(_STEP_AUDIT_LOG) > 50:
        _STEP_AUDIT_LOG.pop(0)


def get_latest_step_providers():
    """Return dictionary of the most recent provider used for each step."""
    return dict(_LATEST_STEP_PROVIDERS)


def get_step_audit_log():
    """Return list of recent step execution audit events."""
    return list(_STEP_AUDIT_LOG)


def get_provider_status():
    return dict(_PROVIDER_METRICS)


def clear_audit_log():
    global _STEP_AUDIT_LOG, _LATEST_STEP_PROVIDERS
    _STEP_AUDIT_LOG = []
    _LATEST_STEP_PROVIDERS = {}


