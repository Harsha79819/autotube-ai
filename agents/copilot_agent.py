"""
Re-export proxy for copilot_agent from project root
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from copilot_agent import (
    parse_pipeline_intent,
    start_background_pipeline,
    rewrite_script_hook_and_rerender,
    inspect_pipeline_state,
    inspect_last_failure,
    run_trend_scan,
    check_last_score,
    rerender_last_video,
    process_copilot_message,
    get_active_job,
    is_job_running,
    render_copilot_drawer,
    render_copilot_main_studio,
)

