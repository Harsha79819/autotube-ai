"""
AutoTube AI - Resilient Streamlit Application Entrypoint (app.py)
Embeds the interactive AI Copilot, Cloudflare/Ngrok mobile tunnel guard,
and top-level fatal crash recovery saving to logs/crash_report.txt.
"""
import os
import sys
import runpy
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CRASH_REPORT_FILE = LOGS_DIR / "crash_report.txt"

# Robust stdout/stderr protector against macOS/Linux revoked tty (OSError: [Errno 5] EIO)
class RobustStreamWrapper:
    def __init__(self, stream, log_path=None):
        # Unwrap any previously nested wrappers to reach the pristine underlying stream
        curr = stream
        visited = set()
        while hasattr(curr, "stream") and curr.stream is not None and id(curr) not in visited:
            visited.add(id(curr))
            curr = curr.stream
        self.stream = curr
        self.log_path = log_path
        self._fallback = None
        self._is_robust_wrapper = True

    def _get_fallback(self):
        if self._fallback is None and self.log_path:
            try:
                self._fallback = open(self.log_path, "a", encoding="utf-8")
            except Exception:
                pass
        return self._fallback

    def write(self, text):
        try:
            if self.stream and self.stream is not self and not getattr(self.stream, "_is_robust_wrapper", False):
                self.stream.write(text)
                return
        except OSError:
            pass
        except Exception:
            pass
        fb = self._get_fallback()
        if fb:
            try:
                fb.write(text)
                fb.flush()
            except Exception:
                pass

    def flush(self):
        try:
            if self.stream and self.stream is not self and not getattr(self.stream, "_is_robust_wrapper", False):
                self.stream.flush()
                return
        except OSError:
            pass
        except Exception:
            pass
        fb = self._get_fallback()
        if fb:
            try:
                fb.flush()
            except Exception:
                pass

    def isatty(self):
        try:
            return self.stream.isatty() if self.stream else False
        except Exception:
            return False

# Protect standard streams immediately without recursive chaining
_raw_stdout = getattr(sys, "__stdout__", None) or sys.stdout
while hasattr(_raw_stdout, "stream") and _raw_stdout.stream is not None:
    _raw_stdout = _raw_stdout.stream

_raw_stderr = getattr(sys, "__stderr__", None) or sys.stderr
while hasattr(_raw_stderr, "stream") and _raw_stderr.stream is not None:
    _raw_stderr = _raw_stderr.stream

if not getattr(sys.stdout, "_is_robust_wrapper", False):
    sys.stdout = RobustStreamWrapper(_raw_stdout, LOGS_DIR / "stdout.log")
else:
    # If already wrapped, ensure its inner stream is unwrapped to the pristine stream
    sys.stdout.stream = _raw_stdout

if not getattr(sys.stderr, "_is_robust_wrapper", False):
    sys.stderr = RobustStreamWrapper(_raw_stderr, LOGS_DIR / "stderr.log")
else:
    # If already wrapped, ensure its inner stream is unwrapped to the pristine stream
    sys.stderr.stream = _raw_stderr

def run_app():
    import streamlit as st

    try:
        from agents.env_loader import sync_secrets_to_env
        sync_secrets_to_env()
    except Exception:
        pass

    try:
        # Ensure fresh code reload for modified agent modules
        for mod in list(sys.modules.keys()):
            if mod.startswith("agents.") or mod in ("telugu_phonetic_normalizer", "pipeline", "supervisor", "liquid_ui"):
                sys.modules.pop(mod, None)

        # Run dashboard within guarded execution context
        runpy.run_path(str(ROOT / "dashboard.py"), run_name="__main__")

    except BaseException as fatal_error:
        # Streamlit control-flow exceptions MUST NOT be intercepted
        err_type = type(fatal_error).__name__
        if err_type in ("StopException", "RerunException", "ScriptControlException"):
            raise fatal_error

        tb_str = traceback.format_exc()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Always print to stderr safely
        try:
            print(
                f"❌ [AutoTube Fatal Crash] {err_type}: {fatal_error}\n{tb_str}",
                file=sys.stderr,
                flush=True,
            )
        except Exception:
            pass

        # 1. Persist traceback to logs/crash_report.txt
        crash_entry = (
            f"\n{'=' * 70}\n"
            f"CRASH REPORT - {timestamp}\n"
            f"ERROR TYPE : {err_type}\n"
            f"MESSAGE    : {fatal_error}\n"
            f"{'-' * 70}\n"
            f"{tb_str}\n"
            f"{'=' * 70}\n"
        )
        try:
            with open(CRASH_REPORT_FILE, "a", encoding="utf-8") as f:
                f.write(crash_entry)
        except Exception:
            pass

        # 2. Render user-facing error recovery card instead of killing session
        st.markdown(
            """
            <div style="
                background: rgba(239, 68, 68, 0.08);
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 16px;
                padding: 1.5rem;
                margin: 2rem 0;
            ">
                <h3 style="color: #F87171; margin-top: 0;">🛡️ Session Protected: Unhandled Error Caught</h3>
                <p style="color: #FCA5A5; font-size: 0.95rem;">
                    AutoTube's top-level crash guard intercepted an unhandled runtime error.
                    Your mobile session is preserved and full diagnostic logs have been saved to <code>logs/crash_report.txt</code>.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.error(f"**{type(fatal_error).__name__}**: {fatal_error}")

        with st.expander("📋 View Copyable Error Traceback", expanded=False):
            st.code(tb_str, language="python")

        try:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Reset Session & Reload Studio", key="err_reset_btn", use_container_width=True):
                    st.session_state.clear()
                    st.rerun()
            with col2:
                if st.button("🩹 Inspect Self-Healing Logs", key="err_logs_btn", use_container_width=True):
                    from supervisor import get_healing_logs
                    logs = get_healing_logs()
                    st.json(logs if logs else {"status": "No supervisor incidents recorded"})
        except Exception:
            st.markdown(
                '<div style="text-align: center; margin-top: 1rem;">'
                '<a href="." target="_self" style="display:inline-block; padding:10px 20px; background:#38BDF8; color:#0F172A; font-weight:700; border-radius:8px; text-decoration:none;">'
                '🔄 Reload Application Session'
                '</a></div>',
                unsafe_allow_html=True,
            )

if __name__ == "__main__" or "streamlit" in sys.modules:
    run_app()
