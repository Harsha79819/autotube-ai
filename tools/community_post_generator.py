#!/usr/bin/env python3
"""
tools/community_post_generator.py - High-CTR YouTube Community Tab Poll & Post Generator

Generates high-engagement community tab questions, polls (4 options), and viral post copies
directly from the video's script, topic, or metadata to build subscriber engagement and views.
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"


def generate_community_poll(
    topic: str,
    script_content: str = "",
    channel_name: str = "viral_talks_me&mine",
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Generates a viral YouTube Community Poll with 4 engaging options in Telugu & English.
    """
    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    is_bb = bool(re.search(r"bigg\s*boss|bb10|vamsi|thrigun|rohit|sudheer|aman|jhansi", topic.lower()))
    is_facts = bool(re.search(r"facts|science|tech|galaxy|space|history|ai|future", topic.lower()))

    # Deterministic fallback poll if AI call fails
    if is_bb:
        fallback_poll = {
            "poll_question": f"🔥 Bigg Boss 10 Today: ఈ వారం ఎలిమినేషన్ లో ఎవరు బయటకు వెళ్తారని మీరు అనుకుంటున్నారు?",
            "options": [
                "1. త్రిగుణ్ ఈశ్వరన్ (Thrigun)",
                "2. తెంపర్ వంశీ (Temper Vamsi)",
                "3. అమన్ మసూద్ (Aman)",
                "4. ఎవరూ కాదు (No Elimination)",
            ],
            "call_to_action": "మీ ఓటు వేసి, అసలు కారణం కింద కామెంట్ చేయండి! 👇 మరిన్ని అప్‌డేట్స్ కోసం సబ్‌స్క్రైబ్ చేసుకోండి!",
            "hashtags": ["#BiggBossTelugu10", "#BiggBossTelugu", "#BB10Updates", "#AutoTubeAI"],
        }
    elif is_facts:
        fallback_poll = {
            "poll_question": f"🧠 Daily Knowledge Quiz: {topic} గురించి మీకు ఈ విషయం ముందే తెలుసా?",
            "options": [
                "1. అవును, ముందే తెలుసు!",
                "2. ఇప్పుడే మొదటిసారి విన్నాను 😮",
                "3. షాకింగ్ గా ఉంది!",
                "4. పూర్తి వీడియో చూడాలి",
            ],
            "call_to_action": "ఫ్రెండ్స్, మీ అభిప్రాయాన్ని ఓటు వేసి తెలియజేయండి! 🚀 లైక్ & షేర్ చేయండి!",
            "hashtags": ["#TeluguFacts", "#DidYouKnowTelugu", "#KnowledgeInTelugu", "#ImaginaryFacts"],
        }
    else:
        fallback_poll = {
            "poll_question": f"📢 మీ అభిప్రాయం చెప్పండి: {topic} పై మీరేమనుకుంటున్నారు?",
            "options": [
                "1. ఖచ్చితంగా నిజం!",
                "2. అస్సలు నమ్మశక్యంగా లేదు",
                "3. పూర్తి నిజం బయటకు రావాలి",
                "4. మీరేమంటారో కామెంట్ చేస్తా",
            ],
            "call_to_action": "మీ సమాధానాన్ని ఓటు వేసి క్రింద కామెంట్ బాక్స్‌లో షేర్ చేయండి! 👇",
            "hashtags": ["#TeluguTrending", "#ViralTelugu", "#AutoTubeAI"],
        }

    # Attempt Gemini generation
    try:
        from agents.script_agent import get_client
        client = get_client()

        prompt = f"""
        You are an expert YouTube community manager specializing in viral engagement for a Telugu YouTube channel.
        Topic: "{topic}"
        Context: "{script_content[:600]}"
        
        Generate an engaging YouTube Community Tab Poll in Telugu (with English brackets for names).
        REQUIREMENTS:
        - Exactly 1 provocative or curious poll question (35-70 characters).
        - Exactly 4 distinct voting options (each 15-35 characters).
        - Engaging Call To Action (CTA).
        - 4 relevant viral hashtags.
        - Return valid JSON only with keys: "poll_question", "options", "call_to_action", "hashtags".
        """

        for model_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]:
            try:
                resp = client.models.generate_content(model=model_name, contents=prompt)
                txt = getattr(resp, "text", "").strip()
                if txt:
                    txt = txt.strip("`")
                    if txt.lower().startswith("json"):
                        txt = txt[4:].strip()
                    parsed = json.loads(txt)
                    if "poll_question" in parsed and "options" in parsed and len(parsed["options"]) == 4:
                        fallback_poll = parsed
                        break
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Community poll generator notice: {e}")

    out_file = out_dir / "community_poll.json"
    out_file.write_text(json.dumps(fallback_poll, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ [Community Tab] Generated viral poll: {out_file.name}")
    return fallback_poll


if __name__ == "__main__":
    poll = generate_community_poll("Bigg Boss Telugu 10 Double Elimination Twist")
    print("Generated Community Poll:")
    print(json.dumps(poll, indent=2, ensure_ascii=False))
