"""
Container & Secrets Environment Loader for AutoTube AI
Seamlessly loads configuration across:
1. Standard container environment variables (Hugging Face Space Secrets, Docker os.environ)
2. Streamlit Secrets (st.secrets)
3. Local development .env file (if present, non-blocking if absent)
"""
import os
from pathlib import Path

# Non-blocking local .env load
ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

try:
    from dotenv import load_dotenv
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
    else:
        load_dotenv()
except Exception:
    pass


def get_secret(key: str, default: str = "") -> str:
    """
    Retrieves secret string with priority:
    1. os.environ (Hugging Face Space Secrets, system env)
    2. st.session_state (UI dynamic input)
    3. st.secrets (Streamlit Cloud / Space secrets)
    4. default value
    """
    # 1. Check OS Environment
    val = os.getenv(key)
    if val is not None and str(val).strip():
        return str(val).strip()

    # 2. Check Streamlit session_state or st.secrets
    try:
        import streamlit as st
        if hasattr(st, "session_state") and key in st.session_state:
            s_val = st.session_state[key]
            if s_val is not None and str(s_val).strip():
                return str(s_val).strip()

        if hasattr(st, "secrets") and key in st.secrets:
            s_val = st.secrets[key]
            if s_val is not None and str(s_val).strip():
                return str(s_val).strip()
    except Exception:
        pass

    return default


def sync_secrets_to_env():
    """Sync Streamlit secrets and session_state to os.environ so all sub-processes/agents have access."""
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            for k in st.secrets:
                try:
                    val = st.secrets[k]
                    if isinstance(val, (str, int, float, bool)) and k not in os.environ:
                        os.environ[k] = str(val).strip()
                except Exception:
                    pass
        if hasattr(st, "session_state"):
            for k in ("GEMINI_API_KEY", "PEXELS_API_KEY", "OPENAI_API_KEY", "APP_PIN"):
                if k in st.session_state and st.session_state[k]:
                    os.environ[k] = str(st.session_state[k]).strip()
    except Exception:
        pass


sync_secrets_to_env()


def get_gemini_api_key() -> str:
    """Returns GEMINI_API_KEY from environment, session state, or secrets."""
    sync_secrets_to_env()
    return get_secret("GEMINI_API_KEY", "")


def get_pexels_api_key() -> str:
    """Returns PEXELS_API_KEY from environment, session state, or secrets."""
    sync_secrets_to_env()
    return get_secret("PEXELS_API_KEY", "")


def get_app_pin(default_pin: str = "8501") -> str:
    """Returns APP_PIN from environment or secrets."""
    return get_secret("APP_PIN", default_pin)


def is_secret_configured(key: str) -> bool:
    """Returns True if a valid non-empty secret is configured."""
    return bool(get_secret(key, ""))
