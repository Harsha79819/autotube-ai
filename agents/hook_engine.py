"""
AutoTube AI - Virality Hook Engine (agents/hook_engine.py)

Generates 5 distinct hook variants across 5 proven viral patterns:
  1. shocking_number: Startling metric, price, or statistic
  2. nobody_tells_you: Insider secret, unrevealed truth
  3. contradiction: Counter-intuitive twist flipping conventional wisdom
  4. curiosity_question: Urgent open loop question that demands an answer
  5. doing_it_wrong: Widespread mistake or misconception reality check

Evaluates all 5 candidates in a single LLM call against the virality rubric:
  - Curiosity Gap (1-10)
  - Specificity (1-10)
  - Emotional Urgency (1-10)
  - Length Compliance (<= 12 words) (1-10)
  - Opening Compliance (Zero greeting, zero channel intro, starts at 0.0s) (1-10)

Saves winning hook and all candidates to output/hook.json.
"""

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

HOOK_PATTERNS = [
    "shocking_number",
    "nobody_tells_you",
    "contradiction",
    "curiosity_question",
    "doing_it_wrong",
]

BANNED_OPENINGS = [
    "హాయ్ ఫ్రెండ్స్",
    "హలో ఫ్రెండ్స్",
    "నమస్కారం",
    "వెల్కమ్ బ్యాక్",
    "ఈ రోజు మనం",
    "ఈ వీడియోలో",
    "హాయ్ guys",
    "hi friends",
    "hi guys",
    "hello guys",
    "welcome back",
    "today we will talk about",
    "in this video",
    "today we are looking at",
    "let me tell you",
]


def _clean_banned_openings(text: str) -> str:
    """Strip any accidental greeting or intro pleasantry from hook text."""
    if not text:
        return ""
    cleaned = text.strip()
    for phrase in BANNED_OPENINGS:
        if cleaned.lower().startswith(phrase.lower()):
            cleaned = cleaned[len(phrase):].lstrip(" ,!-–—:;").strip()
    return cleaned


def generate_hook_candidates_fallback(topic: str, is_telugu: bool = True) -> list[dict]:
    """Offline heuristic fallback hook generator if LLM is unavailable."""
    topic_clean = topic.strip()
    t_low = topic_clean.lower()
    is_bb = any(k in t_low for k in ["bigg boss", "bb10", "nomination", "elimination", "wildcard"])
    is_cinema = any(k in t_low for k in ["movie", "cinema", "film", "teaser", "trailer", "box office", "review"])

    if is_telugu:
        if is_bb:
            return [
                {
                    "pattern": "curiosity_question",
                    "hook_text": f"హౌస్ లో ఉన్న వాళ్లకే దిక్కు లేదు, అసలు ఈ ట్విస్ట్ ఏంటి?!",
                    "score": 49,
                },
                {
                    "pattern": "contradiction",
                    "hook_text": f"{topic_clean} గురించి అందరూ ఊహించింది ఒకటి, కానీ అసలు నిజం వేరే!",
                    "score": 47,
                },
                {
                    "pattern": "nobody_tells_you",
                    "hook_text": f"బిగ్ బాస్ హౌస్ లో రాత్రి జరిగిన ఈ షాకింగ్ సీక్రెట్ ఎవరికీ తెలియదు!",
                    "score": 48,
                },
                {
                    "pattern": "shocking_number",
                    "hook_text": f"ఓటింగ్ లో ఈ ఒక్క కంటెస్టెంట్ కి వచ్చిన ఓట్లు చూస్తే మైండ్ బ్లాక్!",
                    "score": 46,
                },
                {
                    "pattern": "doing_it_wrong",
                    "hook_text": f"ఈ నామినేషన్స్ లో వీళ్ళు చేసిన బిగ్గెస్ట్ బ్లండర్ ఇదే!",
                    "score": 45,
                },
            ]
        elif is_cinema:
            return [
                {
                    "pattern": "curiosity_question",
                    "hook_text": f"{topic_clean} నిజంగా హిట్ ఆ లేక కేవలం హైప్ మాత్రమేనా?!",
                    "score": 49,
                },
                {
                    "pattern": "contradiction",
                    "hook_text": f"ఈ సినిమా గురించి అంతా అనుకుంటున్నది అబద్ధం, అసలు ట్విస్ట్ ఇదీ!",
                    "score": 47,
                },
                {
                    "pattern": "shocking_number",
                    "hook_text": f"బాక్సాఫీస్ దగ్గర జరిగిన ఈ రికార్డ్ కలెక్షన్ మైండ్ బ్లోయింగ్!",
                    "score": 46,
                },
                {
                    "pattern": "nobody_tells_you",
                    "hook_text": f"{topic_clean} వెనుక దాచిన అసలు స్టోరీ ఎవరికీ తెలియదు!",
                    "score": 46,
                },
                {
                    "pattern": "doing_it_wrong",
                    "hook_text": f"ఈ సినిమాలో డైరెక్టర్ చేసిన బిగ్గెస్ట్ మిస్టేక్ ఏంటో తెలుసా?",
                    "score": 45,
                },
            ]
        else:
            return [
                {
                    "pattern": "shocking_number",
                    "hook_text": f"{topic_clean} గురించి ఎవరికీ తెలియని ఈ ఒక్క నంబర్ మైండ్ బ్లాక్ చేస్తుంది!",
                    "score": 46,
                },
                {
                    "pattern": "nobody_tells_you",
                    "hook_text": f"{topic_clean} వెనుక దాచిన అసలు నిజం ఎవరూ చెప్పడం లేదు!",
                    "score": 48,
                },
                {
                    "pattern": "contradiction",
                    "hook_text": f"{topic_clean} గురించి మీరు విన్నదంతా అబద్ధం, అసలు ట్విస్ట్ ఇదీ!",
                    "score": 47,
                },
                {
                    "pattern": "curiosity_question",
                    "hook_text": f"{topic_clean} నిజంగా అంత వర్త్ ఆ, లేక ప్యూర్ హైపా?!",
                    "score": 49,
                },
                {
                    "pattern": "doing_it_wrong",
                    "hook_text": f"{topic_clean} విషయంలో అందరూ చేస్తున్న బిగ్గెస్ట్ మిస్టేక్ ఇదే!",
                    "score": 45,
                },
            ]
    else:
        return [
            {
                "pattern": "shocking_number",
                "hook_text": f"This shocking number about {topic_clean} will break your brain!",
                "score": 45,
            },
            {
                "pattern": "nobody_tells_you",
                "hook_text": f"Nobody is telling you the real truth behind {topic_clean}!",
                "score": 48,
            },
            {
                "pattern": "contradiction",
                "hook_text": f"Everything you think you know about {topic_clean} is totally backwards!",
                "score": 47,
            },
            {
                "pattern": "curiosity_question",
                "hook_text": f"Did {topic_clean} just fix the single biggest flaw nobody could solve?",
                "score": 49,
            },
            {
                "pattern": "doing_it_wrong",
                "hook_text": f"You are seeing {topic_clean} completely wrong and here is why!",
                "score": 44,
            },
        ]


def generate_and_score_hooks(
    topic: str,
    content_type: str = "News",
    language_style: str = "Telugu",
    source_context: str = "",
) -> dict:
    """
    Generates 5 distinct hook variants and scores them with a single LLM call.
    Returns dictionary with chosen_hook, pattern, score, and all_variants.
    """
    lang_str = str(language_style).lower()
    is_telugu = (
        "telugu" in lang_str
        or "తెలుగు" in str(language_style)
        or bool(re.search(r"[\u0C00-\u0C7F]", str(topic)))
    )

    prompt = f"""You are the world's top YouTube Shorts retention director.
Target: Viral YouTube Shorts / Instagram Reels (first 2-3 seconds, strictly 0.0s start).
Topic: {topic}
Content Type: {content_type}
Language: {"Telugu (తెలుగు లిపి) strictly" if is_telugu else "English"}
Context: {source_context[:400] if source_context else "None"}

TASK:
1. Generate 5 DISTINCT hook candidates for this topic, exactly one for each proven pattern:
   - shocking_number: Bold startling metric, spec, price, or statistic.
   - nobody_tells_you: Hidden insider secret or unrevealed truth.
   - contradiction: Counter-intuitive twist that flips conventional wisdom.
   - curiosity_question: Urgent mystery question that demands immediate answer.
   - doing_it_wrong: Pointing out a widespread mistake or misconception.

STRICT HOOK RULES (YOUTUBE RETENTION BENCHMARK):
- LENGTH: Maximum 10-12 words strictly! Short, punchy, high-impact (first 2-3 seconds).
- ZERO GREETING / ZERO DEAD AIR: Spoken audio hook MUST start delivering at 0.0s! BANNED: NO greetings ("హాయ్ ఫ్రెండ్స్", "Namaskaram", "Hi guys"), NO channel intros.
- SPOKEN LANGUAGE: {"Write in authentic natural conversational spoken Telugu (తెలుగు లిపి)" if is_telugu else "Write in punchy spoken English"}.
- PROVEN HIGH-RETENTION STYLES:
  * Burning question / Disbelief: "హౌస్ లో ఉన్న వాళ్లకే దిక్కు లేదు, అసలు ఈ ట్విస్ట్ ఏంటి?!"
  * Shock revelation: "నాగార్జున ఇచ్చిన ఈ వార్నింగ్ తో హౌస్ మొత్తం షేక్!"
  * Contradiction: "అందరూ ఊహించింది ఒకటి, కానీ ఇక్కడ జరిగింది వేరే!"

2. Score each candidate (1 to 10 scale) on:
   - curiosity_gap: How strong is the urge to keep watching? (1-10)
   - specificity: Concrete facts/numbers vs vague generic hype? (1-10)
   - emotional_urgency: Does it trigger shock, surprise, or intrigue? (1-10)
   - length_compliance: Is it <= 12 words? (1-10)
   - zero_greeting: Is it 100% free of greetings and pleasantries? (1-10)
   - total_score: Sum of all 5 criteria (max 50).

Output strictly valid JSON in this exact structure:
{{
  "candidates": [
    {{
      "pattern": "shocking_number",
      "hook_text": "...",
      "word_count": 8,
      "curiosity_gap": 9,
      "specificity": 10,
      "emotional_urgency": 9,
      "length_compliance": 10,
      "zero_greeting": 10,
      "total_score": 48
    }},
    ...
  ],
  "chosen_index": 0,
  "rationale": "Why the chosen hook has the strongest curiosity gap"
}}
"""

    raw_response = ""
    try:
        from providers.llm import generate_text_cascade
        raw_response = generate_text_cascade(prompt, step_name="hook", per_provider_timeout=15.0)
    except Exception as e:
        print(f"⚠️ LLM Hook Engine notice: {e}. Using rule-based hook generation.")

    parsed = None
    if raw_response:
        clean = re.sub(r"^```json\s*", "", raw_response.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"^```\s*", "", clean)
        clean = re.sub(r"```\s*$", "", clean).strip()
        try:
            parsed = json.loads(clean)
        except Exception:
            m = re.search(r"\{.*\}", clean, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except Exception:
                    pass

    candidates = []
    chosen_hook = ""
    chosen_pattern = "curiosity_question"
    chosen_score = 45

    if parsed and isinstance(parsed.get("candidates"), list) and len(parsed["candidates"]) > 0:
        candidates = parsed["candidates"]
        for c in candidates:
            c["hook_text"] = _clean_banned_openings(c.get("hook_text", ""))
            if "total_score" not in c:
                c["total_score"] = (
                    c.get("curiosity_gap", 8)
                    + c.get("specificity", 8)
                    + c.get("emotional_urgency", 8)
                    + c.get("length_compliance", 10)
                    + c.get("zero_greeting", 10)
                )

        candidates.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        top = candidates[0]
        chosen_hook = top.get("hook_text", "")
        chosen_pattern = top.get("pattern", "curiosity_question")
        chosen_score = top.get("total_score", 45)
    else:
        candidates = generate_hook_candidates_fallback(topic, is_telugu=is_telugu)
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        top = candidates[0]
        chosen_hook = _clean_banned_openings(top.get("hook_text", ""))
        chosen_pattern = top.get("pattern", "curiosity_question")
        chosen_score = top.get("score", 45)

    chosen_hook = _clean_banned_openings(chosen_hook)

    result = {
        "topic": topic,
        "chosen_hook": chosen_hook,
        "pattern": chosen_pattern,
        "score": chosen_score,
        "word_count": len(chosen_hook.split()),
        "all_variants": candidates,
    }

    hook_file = OUTPUT_DIR / "hook.json"
    try:
        hook_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as save_err:
        print(f"⚠️ Warning saving hook.json: {save_err}")

    print()
    print("=" * 60)
    print("⚡ VIRALITY HOOK ENGINE RESULTS")
    print("=" * 60)
    print(f"Pattern: {chosen_pattern}")
    print(f"Score:   {chosen_score}/50")
    print(f"Words:   {result['word_count']} words (target <= 12)")
    print(f"Hook:    {chosen_hook}")
    print(f"Audit:   {len(candidates)} variants scored and saved to output/hook.json")
    print("=" * 60)
    print()

    return result


if __name__ == "__main__":
    import sys
    topic_arg = sys.argv[1] if len(sys.argv) > 1 else "Samsung Galaxy S27 Ultra 6000mAh Battery"
    res = generate_and_score_hooks(topic_arg, language_style="Telugu")
    print(json.dumps(res, ensure_ascii=False, indent=2))
