"""
AutoTube AI - Provider Health & Quota Tracker (providers/tracker.py)
Monitors API latency, quotas, and failures across all external providers.
"""

import time
from collections import defaultdict

_PROVIDER_METRICS = defaultdict(lambda: {
    "requests": 0,
    "successes": 0,
    "failures": 0,
    "last_error": None,
    "last_used": 0,
})

def record_call(provider_name: str, success: bool, error: str = None):
    entry = _PROVIDER_METRICS[provider_name]
    entry["requests"] += 1
    entry["last_used"] = time.time()
    if success:
        entry["successes"] += 1
    else:
        entry["failures"] += 1
        entry["last_error"] = str(error)

def get_provider_status():
    return dict(_PROVIDER_METRICS)

