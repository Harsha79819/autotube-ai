"""
AutoTube AI - Pipeline Run Lock Manager (run_lock.py)
Provides mutual exclusion between manual dashboard video generations
and daily automated scheduler runs.
"""

import os
import json
import time
import threading
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent
LOCK_FILE = ROOT / "output" / ".pipeline.lock"
LOCK_TIMEOUT_SECONDS = 900  # 15 minutes max run duration before considering lock stale

# Thread-safe in-process state tracking for multi-user / multi-threaded environments
_PROCESS_LOCK = threading.RLock()
_ACTIVE_HOLDER = None  # Tuple of (thread_id, lock_instance)


def is_pid_alive(pid: int) -> bool:
    """Checks if a given process ID is actively running."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


class PipelineLock:
    """
    Mutual exclusion lock for video generation.
    Supports context manager (`with PipelineLock(...)`) or direct acquire/release.
    Thread-safe, re-entrant for the same thread, and cross-process safe via PID tracking.
    Stale locks (from killed or crashed PIDs, or timed-out runs) are automatically cleaned.
    """

    def __init__(self, source: str = "dashboard", topic: str = ""):
        self.source = source
        self.topic = topic
        self.acquired = False
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def force_unlock(cls) -> bool:
        """Force-clears the pipeline lock file and resets local generation state."""
        with _PROCESS_LOCK:
            global _ACTIVE_HOLDER
            _ACTIVE_HOLDER = None
            try:
                if LOCK_FILE.exists():
                    LOCK_FILE.unlink(missing_ok=True)
                return True
            except Exception:
                return False

    @classmethod
    def get_active_lock_info(cls) -> Optional[dict]:
        """Returns lock metadata dict if an active process holds the lock, else None."""
        with _PROCESS_LOCK:
            global _ACTIVE_HOLDER
            if not LOCK_FILE.exists():
                return None
            try:
                data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
                pid = data.get("pid")
                lock_time = data.get("timestamp", 0)

                # Check 1: Timeout expiration (older than 15 minutes)
                if time.time() - lock_time > LOCK_TIMEOUT_SECONDS:
                    cls.force_unlock()
                    return None

                # Check 2: If lock belongs to THIS process (same PID)
                if pid == os.getpid():
                    if _ACTIVE_HOLDER is None:
                        cls.force_unlock()
                        return None
                    return data

                # Check 3: Cross-process PID liveness
                if pid and is_pid_alive(pid):
                    return data

                # Stale lock: PID is dead
                cls.force_unlock()
                return None
            except Exception:
                cls.force_unlock()
                return None

    def acquire(self) -> Tuple[bool, Optional[str]]:
        """
        Attempts to acquire the run lock.
        Returns:
          (True, None) if lock acquired successfully.
          (False, reason_message) if another active process holds the lock.
        """
        with _PROCESS_LOCK:
            global _ACTIVE_HOLDER
            current_tid = threading.get_ident()

            # Re-entrancy check: if current thread already holds the lock, allow re-entry
            if _ACTIVE_HOLDER is not None and _ACTIVE_HOLDER[0] == current_tid:
                _ACTIVE_HOLDER[2] += 1
                self.acquired = True
                return True, None

            active_info = self.get_active_lock_info()
            if active_info:
                holder_source = active_info.get("source", "another process")
                holder_pid = active_info.get("pid", "unknown")
                holder_topic = active_info.get("topic", "")
                msg = f"Generation already in progress by {holder_source} (PID {holder_pid})"
                if holder_topic:
                    msg += f" for topic: '{holder_topic[:40]}'"
                return False, msg

            data = {
                "pid": os.getpid(),
                "source": self.source,
                "topic": self.topic,
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": time.time(),
            }
            try:
                LOCK_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
                self.acquired = True
                _ACTIVE_HOLDER = [current_tid, self, 1]
                return True, None
            except Exception as e:
                return False, f"Failed to write lock file: {e}"

    def release(self):
        """Releases the run lock."""
        with _PROCESS_LOCK:
            global _ACTIVE_HOLDER
            if not self.acquired:
                return
            current_tid = threading.get_ident()
            if _ACTIVE_HOLDER is not None and _ACTIVE_HOLDER[0] == current_tid:
                _ACTIVE_HOLDER[2] -= 1
                if _ACTIVE_HOLDER[2] <= 0:
                    _ACTIVE_HOLDER = None
                    try:
                        if LOCK_FILE.exists():
                            try:
                                data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
                                if data.get("pid") == os.getpid():
                                    LOCK_FILE.unlink(missing_ok=True)
                            except Exception:
                                LOCK_FILE.unlink(missing_ok=True)
                    except Exception:
                        pass
            self.acquired = False

    def __enter__(self):
        success, reason = self.acquire()
        if not success:
            raise RuntimeError(f"Could not acquire pipeline lock: {reason}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

