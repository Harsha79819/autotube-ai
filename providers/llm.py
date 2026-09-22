"""
AutoTube AI - Multi-Provider LLM Gateway (providers/llm.py)
Manages primary Google Gemini API with fallback cascade.
"""

import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

try:
    from agents.env_loader import get_gemini_api_key
except ImportError:
    try:
        from env_loader import get_gemini_api_key
    except ImportError:
        def get_gemini_api_key():
            return os.getenv("GEMINI_API_KEY", "")

ACTIVE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-lite-latest",
]

def generate_text_cascade(prompt: str, api_key: str = None) -> str:
    key = api_key or get_gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=key)
    last_err = None

    for model_name in ACTIVE_MODELS:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            text = getattr(resp, "text", "")
            if text and text.strip():
                return text.strip()
        except Exception as err:
            last_err = err
            continue

    raise RuntimeError(f"All LLM models in cascade failed. Last error: {last_err}")


def generate_multimodal_cascade(prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg", api_key: str = None) -> str:
    """Generate content from an image + text prompt using Gemini models in cascade."""
    key = api_key or get_gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=key)
    last_err = None

    image_part = genai.types.Part.from_bytes(
        data=image_bytes,
        mime_type=mime_type,
    )

    for model_name in ACTIVE_MODELS:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[prompt, image_part],
            )
            text = getattr(resp, "text", "")
            if text and text.strip():
                return text.strip()
        except Exception as err:
            last_err = err
            continue

    raise RuntimeError(f"All multimodal LLM models in cascade failed. Last error: {last_err}")


