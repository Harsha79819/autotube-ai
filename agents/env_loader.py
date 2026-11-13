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


def _has_secrets_file() -> bool:
    try:
        p1 = ROOT / ".streamlit" / "secrets.toml"
        p2 = Path.home() / ".streamlit" / "secrets.toml"
        return p1.exists() or p2.exists()
    except Exception:
        return False


def _auto_populate_secrets_toml():
    """Auto-populates .streamlit/secrets.toml from .env if missing for seamless local Streamlit compatibility."""
    try:
        dest = ROOT / ".streamlit" / "secrets.toml"
        if not dest.exists() and ENV_FILE.exists():
            from dotenv import dotenv_values
            env_vals = dotenv_values(ENV_FILE)
            if env_vals:
                dest.parent.mkdir(parents=True, exist_ok=True)
                lines = ['# Local Streamlit Secrets (Generated from .env, gitignored)\n']
                for k, v in env_vals.items():
                    if v is not None:
                        escaped_v = str(v).replace('\\', '\\\\').replace('"', '\\"')
                        lines.append(f'{k} = "{escaped_v}"\n')
                dest.write_text(''.join(lines), encoding='utf-8')
    except Exception:
        pass


_auto_populate_secrets_toml()


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

        if _has_secrets_file():
            try:
                if key in st.secrets:
                    s_val = st.secrets[key]
                    if s_val is not None and str(s_val).strip():
                        return str(s_val).strip()
            except Exception:
                pass
    except Exception:
        pass

    return default


def sync_secrets_to_env():
    """Sync Streamlit secrets and session_state to os.environ so all sub-processes/agents have access."""
    try:
        import streamlit as st
        if _has_secrets_file():
            try:
                for k in st.secrets:
                    try:
                        val = st.secrets[k]
                        if isinstance(val, (str, int, float, bool)) and k not in os.environ:
                            os.environ[k] = str(val).strip()
                    except Exception:
                        pass
            except Exception:
                pass
        if hasattr(st, "session_state"):
            for k in ("GEMINI_API_KEY", "PEXELS_API_KEY", "OPENAI_API_KEY", "APP_PIN"):
                if k in st.session_state and st.session_state[k]:
                    os.environ[k] = str(st.session_state[k]).strip()
    except Exception:
        pass


import re
import threading

sync_secrets_to_env()

_GEMINI_KEY_INDEX = 0
_KEY_LOCK = threading.Lock()


def get_all_gemini_api_keys() -> list:
    """
    Returns a deduplicated list of all configured Gemini API keys.
    Supports:
    1. Comma/newline/semicolon separated list in GEMINI_API_KEY
    2. GEMINI_API_KEYS variable
    3. Numbered keys GEMINI_API_KEY_1 through GEMINI_API_KEY_20
    """
    sync_secrets_to_env()
    keys = []

    def _add_parts(val: str):
        if not val:
            return
        for part in re.split(r"[,;\n\r\t ]+", val.strip()):
            part = part.strip()
            if part and len(part) >= 15 and part not in keys:
                keys.append(part)

    # 1. Main GEMINI_API_KEY (can be single or comma-separated)
    _add_parts(get_secret("GEMINI_API_KEY", ""))

    # 2. GEMINI_API_KEYS
    _add_parts(get_secret("GEMINI_API_KEYS", ""))

    # 3. Numbered keys GEMINI_API_KEY_1 .. GEMINI_API_KEY_20
    for i in range(1, 21):
        _add_parts(get_secret(f"GEMINI_API_KEY_{i}", ""))

    return keys


def get_gemini_api_key(rotate: bool = False) -> str:
    """Returns the current active Gemini API key from the pool, optionally rotating to the next."""
    global _GEMINI_KEY_INDEX
    keys = get_all_gemini_api_keys()
    if not keys:
        return ""
    with _KEY_LOCK:
        if rotate:
            _GEMINI_KEY_INDEX = (_GEMINI_KEY_INDEX + 1) % len(keys)
        idx = _GEMINI_KEY_INDEX % len(keys)
        return keys[idx]


def rotate_gemini_api_key() -> str:
    """Rotates to the next available Gemini API key in the pool and returns it."""
    return get_gemini_api_key(rotate=True)


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
