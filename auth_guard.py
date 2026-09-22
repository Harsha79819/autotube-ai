"""
AutoTube AI - Security Access Guard & Mobile Responsiveness (auth_guard.py)
Secures public Cloudflare tunnel sessions with PIN authentication and mobile CSS.
"""
import os
import time
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DEFAULT_PIN = "8501"

try:
    from agents.env_loader import get_app_pin
except ImportError:
    from env_loader import get_app_pin

def get_configured_pin() -> str:
    """Fetch configured PIN from env or Streamlit secrets, defaulting to 8501."""
    return get_app_pin(DEFAULT_PIN)

def is_authenticated() -> bool:
    """Check if current session has been validated."""
    return bool(st.session_state.get("authenticated", False))

def inject_mobile_responsive_css():
    """
    Injects touch-optimized, mobile-first responsive CSS for smartphones.
    Ensures columns collapse, touch targets are >= 48px, and video scales fluidly.
    """
    st.markdown(
        """
        <style>
        /* Mobile-First Responsive Styles */
        @media (max-width: 768px) {
            /* Container padding adjustments */
            .block-container {
                padding-top: 1.5rem !important;
                padding-bottom: 3rem !important;
                padding-left: 0.8rem !important;
                padding-right: 0.8rem !important;
                max-width: 100% !important;
            }

            /* Responsive stacking for columns */
            [data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 100% !important;
                margin-bottom: 0.75rem !important;
            }

            /* Touch-friendly buttons (minimum 48px height) */
            .stButton > button {
                width: 100% !important;
                min-height: 48px !important;
                font-size: 1.05rem !important;
                font-weight: 600 !important;
                border-radius: 12px !important;
                margin: 0.3rem 0 !important;
                touch-action: manipulation;
            }

            /* Fluid video scaling */
            video, .stVideo {
                width: 100% !important;
                max-width: 100% !important;
                height: auto !important;
                border-radius: 14px !important;
            }

            /* Touch inputs and selects */
            input, select, textarea {
                font-size: 16px !important; /* Prevents auto-zoom on iOS Safari */
                min-height: 44px !important;
            }

            /* Tabs styling on small screens */
            .stTabs [data-baseweb="tab-list"] {
                gap: 4px !important;
                overflow-x: auto !important;
                white-space: nowrap !important;
            }

            .stTabs [data-baseweb="tab"] {
                padding: 8px 12px !important;
                font-size: 0.9rem !important;
            }
        }

        /* PIN Lock Screen Card */
        .pin-lock-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: rgba(255, 255, 255, 0.04);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 20px;
            padding: 2.5rem 1.8rem;
            max-width: 440px;
            margin: 3rem auto 2rem auto;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
            text-align: center;
        }
        .pin-lock-icon {
            font-size: 3.2rem;
            margin-bottom: 0.5rem;
        }
        .pin-lock-title {
            font-size: 1.6rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            margin-bottom: 0.4rem;
        }
        .pin-lock-subtitle {
            font-size: 0.95rem;
            opacity: 0.75;
            margin-bottom: 1.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def is_custom_pin_set() -> bool:
    """Check if user explicitly configured an APP_PIN in env or secrets."""
    try:
        from agents.env_loader import get_secret
        val = get_secret("APP_PIN", "")
        return bool(val and val.strip() and val.strip().lower() not in ("none", "false", "0"))
    except Exception:
        return False

def require_pin_authentication() -> bool:
    """
    Enforces PIN authentication before allowing any dashboard controls to render.
    If no custom PIN is configured in secrets or env, auto-authenticates for seamless mobile access.
    """
    inject_mobile_responsive_css()

    if is_authenticated():
        return True

    # Auto-grant access if user hasn't explicitly configured a custom APP_PIN
    if not is_custom_pin_set():
        st.session_state["authenticated"] = True
        return True

    configured_pin = get_configured_pin()

    # Rate limiting / brute-force protection
    if "pin_attempts" not in st.session_state:
        st.session_state["pin_attempts"] = 0
    if "lockout_until" not in st.session_state:
        st.session_state["lockout_until"] = 0

    now = time.time()
    if now < st.session_state["lockout_until"]:
        remaining = int(st.session_state["lockout_until"] - now)
        st.error(f"🔒 Too many failed attempts. Temporary lockout for {remaining}s.")
        st.stop()

    st.markdown(
        """
        <div class="pin-lock-container">
            <div class="pin-lock-icon">🔐</div>
            <div class="pin-lock-title">AutoTube Remote Guard</div>
            <div class="pin-lock-subtitle">Enter your security PIN to unlock the mobile studio</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_l, col_m, col_r = st.columns([1, 2, 1])
    with col_m:
        pin_entered = st.text_input(
            "Security PIN",
            type="password",
            placeholder="••••",
            max_chars=12,
            help="Configure your custom PIN in .env via APP_PIN=...",
            label_visibility="collapsed",
            key="pin_guard_input_field",
        )
        submit_btn = st.button("Unlock Dashboard 🚀", key="pin_guard_submit_btn", use_container_width=True)

        if submit_btn or (pin_entered and len(pin_entered) >= 4 and pin_entered == configured_pin):
            if str(pin_entered).strip() == configured_pin:
                st.session_state["authenticated"] = True
                st.session_state["pin_attempts"] = 0
                st.session_state["lockout_until"] = 0
                st.success("✅ Access granted! Loading AutoTube Studio...")
                time.sleep(0.3)
                st.rerun()
            elif submit_btn:
                st.session_state["pin_attempts"] += 1
                attempts_left = 5 - st.session_state["pin_attempts"]
                if st.session_state["pin_attempts"] >= 5:
                    st.session_state["lockout_until"] = time.time() + 60
                    st.session_state["pin_attempts"] = 0
                    st.error("🚨 5 incorrect attempts. Locked out for 60 seconds.")
                else:
                    st.error(f"❌ Invalid PIN. {attempts_left} attempt(s) remaining.")

        st.caption("🔒 Secured via local Cloudflare Tunnel & PIN Access Guard.")

    # Halt execution so unauthenticated visitors cannot see video controls or triggers
    st.stop()
    return False

def render_logout_button():
    """Renders a clean logout option in the sidebar."""
    if is_authenticated():
        if st.sidebar.button("🔒 Lock Studio (Logout)", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()
