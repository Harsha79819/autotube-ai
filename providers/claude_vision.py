"""
AutoTube AI - Claude Vision Image Verification Gateway (providers/claude_vision.py)

Implements Step 5 of the visual selection pipeline:
- Sends candidate images to Claude API (vision) along with the script line, entity, and event.
- Prompts Claude to evaluate which image accurately depicts the script line or return "none".
- Uses Anthropic API (claude-3-5-sonnet / claude-3-haiku) when ANTHROPIC_API_KEY is set.
- Gracefully falls back to Gemini Vision if ANTHROPIC_API_KEY is not configured in .env.
"""

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()


def _encode_image_b64(image_path: Path) -> Tuple[str, str]:
    ext = image_path.suffix.lower()
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, media_type


def call_claude_vision_anthropic(
    image_paths: List[Path],
    script_line: str,
    entity: str,
    event: str,
    api_key: str,
    candidates_meta: Optional[List[Dict[str, Any]]] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """Calls Anthropic Claude Vision API (claude-3-5-sonnet-20241022 or claude-3-haiku-20240307)."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key.strip(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    content_blocks = [
        {
            "type": "text",
            "text": (
                f"You are an expert visual director verifying real photos for a video.\n"
                f"Video Script Line: \"{script_line}\"\n"
                f"Target Entity/Person: \"{entity}\"\n"
                f"Target Event: \"{event}\"\n\n"
                f"Review the attached {len(image_paths)} images (labeled 0 to {len(image_paths)-1}).\n"
                f"Determine which image (if any) accurately portrays the entity and context described in the script line."
            ),
        }
    ]

    for idx, img_path in enumerate(image_paths):
        b64_data, media_type = _encode_image_b64(img_path)
        meta_desc = ""
        if candidates_meta and idx < len(candidates_meta):
            cm = candidates_meta[idx]
            tags_str = ", ".join(str(h) for h in cm.get("hashtags", [])) if cm.get("hashtags") else "none"
            meta_desc = (
                f"\nSource Post Metadata:"
                f"\n  • Username: @{cm.get('username', 'unknown')}"
                f"\n  • Platform: {cm.get('platform', 'social')}"
                f"\n  • Caption: \"{cm.get('caption', '')}\""
                f"\n  • Hashtags: {tags_str}"
            )
        content_blocks.append({"type": "text", "text": f"\n[Image {idx}]{meta_desc}"})
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64_data,
            },
        })

    content_blocks.append({
        "type": "text",
        "text": (
            "CRITICAL DECISION INSTRUCTIONS:\n"
            "1. You MUST decide using the caption, username, and hashtags, NOT by recognizing faces alone.\n"
            "2. CELEBRITY COLLISION RULES:\n"
            "   • For entity 'Charan': this refers strictly to the Bigg Boss Telugu contestant Charan Kumar, NOT movie actor Ram Charan (Konidela, RRR, Game Changer, Pushpa, Chiranjeevi).\n"
            "   • For entity 'Rohit': this refers strictly to contestant Rohit Sahni, NOT cricketer Rohit Sharma (Indian cricket team, jerseys, cricket pitch, BCCI, IPL, Mumbai Indians).\n"
            "   • For entity 'Arjun': this refers strictly to contestant Arjun Kalyan, NOT actor Allu Arjun (Pushpa, Bunny).\n"
            "3. Answer \"none\" when the post or image is about the unrelated celebrity.\n"
            "4. If NONE of the images match the target TV contestant and script line context, return \"none\".\n"
            "5. Never select an unrelated celebrity or random image.\n"
            "6. PAST SEASON LOGO / NUMERAL REJECTION: If an image features visible logos, numerals, or banners of older seasons (e.g., giant numeral 9, 8, 7, or Season 9/8 logo, BB9/BB8), reject it immediately and return \"none\" when evaluating Season 10 content.\n\n"
            "Return strictly valid JSON:\n"
            "{\n"
            '  "choice": <0, 1, 2, 3, 4, or "none">,\n'
            '  "reason": "<1-2 sentence explanation of why this image was chosen or why none matched>"\n'
            "}"
        ),
    })

    model_name = os.getenv("CLAUDE_VISION_MODEL", "claude-3-5-sonnet-20241022")
    payload = {
        "model": model_name,
        "max_tokens": 300,
        "messages": [{"role": "user", "content": content_blocks}],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code == 200:
        data = resp.json()
        text = ""
        for part in data.get("content", []):
            if part.get("type") == "text":
                text += part.get("text", "")
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            verdict = json.loads(m.group(0))
            return {
                "choice": verdict.get("choice", "none"),
                "reason": verdict.get("reason", "Verified by Claude Vision"),
                "model_used": model_name,
            }
    raise RuntimeError(f"Claude Vision HTTP {resp.status_code}: {resp.text[:180]}")


def call_claude_vision_gemini_fallback(
    image_paths: List[Path],
    script_line: str,
    entity: str,
    event: str,
    candidates_meta: Optional[List[Dict[str, Any]]] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Fallback vision verification using Gemini Flash Lite Vision."""
    from google import genai

    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=key)
    prompt_intro = (
        f"You are an expert visual director verifying real photos for a video.\n"
        f"Video Script Line: \"{script_line}\"\n"
        f"Target Entity/Person: \"{entity}\"\n"
        f"Target Event: \"{event}\"\n\n"
        f"Attached are {len(image_paths)} images labeled Index 0 to {len(image_paths)-1}.\n"
        f"Rules:\n"
        f"- You MUST decide using the caption, username, and hashtags, NOT by recognizing faces alone.\n"
        f"- CELEBRITY COLLISION RULES:\n"
        f"  • For 'Charan': refers strictly to Bigg Boss contestant Charan Kumar, NOT movie actor Ram Charan (RRR, Konidela, movies).\n"
        f"  • For 'Rohit': refers strictly to contestant Rohit Sahni, NOT cricketer Rohit Sharma (Indian cricket team, jersey, cricket pitch).\n"
        f"  • For 'Arjun': refers strictly to contestant Arjun Kalyan, NOT actor Allu Arjun (Pushpa).\n"
        f"- Answer \"none\" when the post or image is about the unrelated celebrity.\n"
        f"- If an image clearly portrays the TV show contestant and context, return its integer index (0 to {len(image_paths)-1}).\n"
        f"- If NONE of the images match the TV contestant and script line, return \"none\".\n"
        f"- Never select an unrelated celebrity or random image.\n"
        f"- If an image features visible logos, numerals, or banners of past seasons (e.g., giant numeral 9, 8, 7, or Season 9/8 logo, BB9/BB8), reject it immediately and return \"none\" when evaluating Season 10 content.\n\n"
        f"Return strictly valid JSON:\n"
        f"{{\n"
        f'  "choice": <0, 1, 2, 3, 4, or "none">,\n'
        f'  "reason": "<1-2 sentence explanation>"\n'
        f"}}"
    )

    contents: List[Any] = [prompt_intro]
    for idx, p in enumerate(image_paths):
        meta_desc = ""
        if candidates_meta and idx < len(candidates_meta):
            cm = candidates_meta[idx]
            tags_str = ", ".join(str(h) for h in cm.get("hashtags", [])) if cm.get("hashtags") else "none"
            meta_desc = (
                f"\nSource Post Metadata:"
                f"\n  • Username: @{cm.get('username', 'unknown')}"
                f"\n  • Platform: {cm.get('platform', 'social')}"
                f"\n  • Caption: \"{cm.get('caption', '')}\""
                f"\n  • Hashtags: {tags_str}"
            )
        contents.append(f"Image {idx}:{meta_desc}")
        try:
            im = Image.open(p)
            contents.append(im)
        except Exception:
            pass

    for m in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]:
        try:
            resp = client.models.generate_content(
                model=m,
                contents=contents,
            )
            raw_text = resp.text or ""
            break
        except Exception:
            continue
    m = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
    if m:
        try:
            verdict = json.loads(m.group(0))
            return {
                "choice": verdict.get("choice", "none"),
                "reason": verdict.get("reason", "Verified by Vision LLM"),
                "model_used": "gemini-flash-lite (vision fallback)",
            }
        except Exception:
            pass
    return {"choice": "none", "reason": "Could not parse vision verdict", "model_used": "gemini-flash-lite"}


def verify_candidates_with_claude_vision(
    image_paths: List[Path],
    script_line: str,
    entity: str,
    event: str,
    candidates_meta: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Step 5:
    Sends top candidates to Claude Vision API (or verified fallback) to pick best match index (0..4) or 'none'.
    Decides based on caption, username, and hashtags, not face recognition alone.
    """
    if not image_paths:
        return {"choice": "none", "reason": "No candidate images provided.", "model_used": "none"}

    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
    if anthropic_key and anthropic_key.strip():
        try:
            print(f"👁️ [Claude Vision] Verifying {len(image_paths)} images via Claude API for entity '{entity}'...")
            return call_claude_vision_anthropic(
                image_paths, script_line, entity, event, api_key=anthropic_key, candidates_meta=candidates_meta
            )
        except Exception as err:
            print(f"⚠️ Claude Vision API notice: {err}. Falling back to Vision gateway...")

    # Fallback to Gemini Vision if Anthropic key is not present or failed
    try:
        print(f"👁️ [Vision Gateway] Verifying {len(image_paths)} images via Vision model for entity '{entity}'...")
        return call_claude_vision_gemini_fallback(
            image_paths, script_line, entity, event, candidates_meta=candidates_meta
        )
    except Exception as err:
        print(f"⚠️ Vision verification exception: {err}. Defaulting to 'none' text card.")
        return {
            "choice": "none",
            "reason": f"Vision verification failed ({err}). Safe text card fallback.",
            "model_used": "error",
        }
