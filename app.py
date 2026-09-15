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
CRASH_REPORT_FILE = LOGS_DIR / "crash_report.txt"

def run_app():
    import streamlit as st

    try:
        # Run dashboard within guarded execution context
        runpy.run_path(str(ROOT / "dashboard.py"), run_name="__main__")

    except Exception as fatal_error:
        tb_str = traceback.format_exc()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Persist traceback to logs/crash_report.txt
        crash_entry = (
            f"\n{'=' * 70}\n"
            f"CRASH REPORT - {timestamp}\n"
            f"ERROR TYPE : {type(fatal_error).__name__}\n"
            f"MESSAGE    : {fatal_error}\n"
            f"{'-' * 70}\n"
            f"{tb_str}\n"
            f"{'=' * 70}\n"
        )
        try:
            with open(CRASH_REPORT_FILE, "a", encoding="utf-8") as f:
                f.write(crash_entry)
        except Exception as log_err:
            print(f"⚠️ Failed to write to crash report file: {log_err}")

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
