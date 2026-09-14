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
    2. st.secrets (Streamlit Cloud / Space secrets)
    3. default value
    """
    # 1. Check OS Environment
    val = os.getenv(key)
    if val is not None and str(val).strip():
        return str(val).strip()

    # 2. Check Streamlit Secrets if available
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            if key in st.secrets:
                s_val = st.secrets[key]
                if s_val is not None and str(s_val).strip():
                    return str(s_val).strip()
    except Exception:
        pass

    return default


def get_gemini_api_key() -> str:
    """Returns GEMINI_API_KEY from environment or secrets."""
    return get_secret("GEMINI_API_KEY", "")


def get_pexels_api_key() -> str:
    """Returns PEXELS_API_KEY from environment or secrets."""
    return get_secret("PEXELS_API_KEY", "")


def get_app_pin(default_pin: str = "8501") -> str:
    """Returns APP_PIN from environment or secrets."""
    return get_secret("APP_PIN", default_pin)


def is_secret_configured(key: str) -> bool:
    """Returns True if a valid non-empty secret is configured."""
    return bool(get_secret(key, ""))
