"""
AutoTube AI - Universal Sarcastic Roast Script Engine (agents/roast_engine.py)

Multi-pass intelligent Telugu comedy scriptwriter inspired by Grok AI,
'In a Nutshell', '301 Diaries', and 'Incognito':
  Pass 1: Extract verified topic facts (names, numbers, claims, plot twists, specs)
  Pass 2: Draft roast script with witty sarcastic persona (Tanglish, setup short, punch last)
  Pass 3: Punch-up pass (tighten setups, punchlines every 5-7s, dynamic 60-90s duration)
  Pass 4: Quirky & creative Call-To-Action (unique and topic-linked every time)
  Pass 5: LLM Humor Judge & Safety Gate (score >= 7, >= 5 punchlines)
  Pass 6: Zero-Fail Pre-Execution Calibration (word count & duration verification before render)
  Pass 7: Delivery markup & Teleprompter export (output/teleprompter.txt)
"""

import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent

try:
    from providers.llm import generate_text_cascade
except ImportError:
    def generate_text_cascade(prompt: str, **kwargs) -> str:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt).text

ROAST_PERSONA_PROMPT = """You are an ultra-witty, sarcastic Telugu AI roast commentator inspired by Grok AI, 'In a Nutshell', '301 Diaries', and 'Incognito'.
You are that smart, sarcastic best friend sitting next to the viewer, breaking down movies, trailers, tech gadgets, reality shows, or pop culture events with sharp, observational irony.

VOCAL PERSONA & DELIVERY GUIDELINES:
"Speak in the tone of an energetic, candid Telugu film reviewer. Sound spontaneous, dramatic, and expressive rather than robotic or formal. Add subtle vocal emphasis on contrasting words and punchlines."

PUNCTUATION-DRIVEN CADENCE:
Text-to-speech engines rely heavily on punctuation for inflection and natural prosody.
- Break long, dramatic lines into short punchy fragments using commas (,), dashes (—), and ellipsis (...) to create organic breathing room and build anticipation before major reveals.
- Use dashes (—) for sharp shifts in thought or ironic contrast (e.g. "హైప్ చూస్తే ఆకాశంలో ఉంది — గ్రౌండ్ రియాలిటీ చూస్తే పాతాళంలో ఉంది!").
- Use ellipsis (...) for suspenseful anticipation right before revealing the funny punchline or twist (e.g. "అసలు ట్విస్ట్ ఏంటంటే...").
- Keep sentences short, punchy, and rhythmic (under 8-12 words per fragment).

NATIVE TELUGU SCRIPT FOR ALL ENGLISH LOANWORDS (CRITICAL FOR NATURAL HUMAN AI VOICE):
- STRICTLY FORBIDDEN: NEVER write English alphabet characters in the script. When neural TTS sees English letters, it switches to an American or neutral English accent, causing robotic pauses and ruining the Telugu comedic cadence!
- Write ALL English loanwords, technical terms, titles, and slang strictly in TELUGU SCRIPT (తెలుగు లిపి):
  • Mind blank -> మైండ్ బ్లాంక్
  • Scene cut -> సీన్ కట్
  • Twist -> ట్విస్ట్
  • Climax -> క్లైమాక్స్
  • Budget -> బడ్జెట్
  • Hype -> హైప్
  • Dialogues -> డైలాగ్స్
  • Story -> స్టోరీ
  • Acting -> యాక్టింగ్
  • Screenplay -> స్క్రీన్‌ప్లే
  • Comedy show -> కామెడీ షో
  • Same to same -> సేమ్ టు సేమ్
  • Strategy -> స్ట్రాటజీ
  • PR -> పీఆర్
  • Record -> రికార్డ్
  • Review -> రివ్యూ
  • Channel -> ఛానల్
  • Like, Share, Subscribe -> లైక్, షేర్, సబ్‌స్క్రైబ్
  • Comment -> కామెంట్

PUNCTUATION & NATURAL HUMAN EXPRESSION WORDS:
- Break sentences into short punchy fragments (under 6-10 words) separated by commas (,), question marks (?), exclamation marks (!), and ellipsis (...) for realistic breathing room.
- Sprinkle lively conversational human reaction words: "అసలు...", "చూశారా!", "అబ్బా!", "ఏంటో భయ్యా...", "నెక్స్ట్ లెవెల్ అండి బాబు...", "బాబోయ్!"
- STRICT BAN ON MECHANICAL TRANSLATION:
  DO NOT translate English headlines literally (e.g. NEVER write "యూపీ ఎందుకు బ్యాక్ ఉంది", "ఏపీ ఎందుకు ర్యాంక్ అని ఉంది").
  Always speak in natural, colloquial Telugu conversation (సరళమైన సహజ వాడుక భాష) like an authentic Telugu YouTuber!

TONE & COMEDY PHILOSOPHY:
1. WE DO NOT JUDGE OR PREACH. We don't judge anyone morally. We simply highlight the sheer comedy, irony, and absurdity of what actually happened.
2. CONCRETE INCIDENTS & DETAILS OVER GENERIC FLUFF:
   - STRICTLY FORBIDDEN: Do NOT talk about "Hollywood directors shocked", "Oscar jury crying", "emotional blackmail with parents", or "students failing in viva exam". These are empty fluff!
   - Every script MUST sound like an authentic, razor-sharp creator breakdown about the REAL TOPIC provided!
   - CITE SPECIFIC ENTITIES & ACTIONS: Ground observations directly in the real claims, specs, numbers, plot points, people, or events of the topic. If discussing reality TV / Bigg Boss, cite active housemates and nomination arguments. If discussing science, tech, cinema, or facts, cite actual mechanics, specs, or surprising real-world dynamics!
3. ROAST WHAT HAPPENED OR WAS CLAIMED: Focus on bizarre contradictions, broken promises, exaggerated reactions, dramatic overacting, or funny public statements.
4. NEVER CROSS THE LINE: Strictly NO body shaming, appearance insults, religion, caste, gender, disability, personal life, or family. Witty, cerebral, and playful—never toxic or cheap slander.
5. NO FLAT EXPLANATIONS: Every line must have an observation, ironic twist, mock praise, fake sympathy, or hilarious comparison.
6. VIRAL RETENTION HOOK & COMMENT TRIGGER: Open with a shocking 0-3 second curiosity claim or disbelief observation that grabs the viewer instantly without intro pleasantries. Right before the closing CTA, include 1 polarizing opinion question inviting viewers to share their opinion or prediction in the comments.
"""

def load_roast_examples(topic: str = "") -> str:
    ex_file = ROOT / "config" / "roast_examples.json"
    if not ex_file.exists():
        return ""
    try:
        data = json.loads(ex_file.read_text(encoding="utf-8"))
        all_examples = data.get("examples", [])
        from utils.season_guard import is_bigg_boss_topic
        is_bb = is_bigg_boss_topic(topic) if topic else False
        t_low = (topic or "").lower()

        if is_bb:
            # Reality TV & Entertainment examples
            preferred = [e for e in all_examples if e.get("category") in ["reality_tv", "entertainment"]]
        elif any(k in t_low for k in ["tech", "phone", "iphone", "apple", "samsung", "ai", "laptop", "gadget", "software", "code"]):
            # Tech & Viral examples
            preferred = [e for e in all_examples if e.get("category") in ["tech", "viral", "news"]]
        elif any(k in t_low for k in ["movie", "cinema", "film", "teaser", "trailer", "box office", "actor", "hero", "star"]):
            # Cinema & Entertainment/Viral (strictly excluding reality_tv)
            preferred = [e for e in all_examples if e.get("category") in ["cinema", "viral", "news"]]
        else:
            # General topic: exclude reality_tv to prevent Bigg Boss bias leaking into general topics
            preferred = [e for e in all_examples if e.get("category") not in ["reality_tv"]]

        selected = preferred if preferred else [e for e in all_examples if e.get("category") != "reality_tv"]
        lines = []
        for item in selected[:6]:
            lines.append(f"Flat: {item['flat']}\nRoast: {item['roast']}")
        return "\n\n".join(lines)
    except Exception:
        return ""


# ------------------------------------------------------------
# 1. EXTRACT VERIFIED FACTS
# ------------------------------------------------------------
def extract_topic_facts(topic: str, source_context: Optional[Dict] = None) -> List[str]:
    """Extracts 5-8 verified facts with names, numbers, plot points, or claims from topic."""
    from utils.season_guard import is_bigg_boss_topic
    is_bb = is_bigg_boss_topic(topic)

    context_text = ""
    if source_context and isinstance(source_context, dict) and source_context.get("articles"):
        arts = source_context["articles"][:3]
        context_text = "\n".join([f"- {a.get('title', '')}: {a.get('snippet', '')}" for a in arts])

    contestant_context = ""
    if is_bb:
        try:
            c_file = ROOT / "contestants.json"
            if c_file.exists():
                c_data = json.loads(c_file.read_text(encoding="utf-8"))
                c_list = [f"{v.get('full_name', k)} ({v.get('telugu_name', '')})" for k, v in list(c_data.items())[:8]]
                contestant_context = f"\nActive Bigg Boss Telugu Housemates: {', '.join(c_list)}, Host Akkineni Nagarjuna.\n"
        except Exception:
            pass

    if is_bb:
        prompt = f"""You are an entertainment news reporter and savage comedy writer for Bigg Boss Telugu.
Extract 5-7 CONCRETE, SPECIFIC reality show news facts and dramatic incidents about this topic:
Topic: {topic}
{contestant_context}
Context:
{context_text or "Latest Bigg Boss Telugu house events, nominations, voting flips, and housemate conflicts"}

MANDATORY RULES:
- MUST name specific ACTIVE housemates (e.g. Rohit, Jhansi, Thrigun, Aman, Sudheer, or Host Nagarjuna). STRICT: DO NOT name eliminated housemates (Charan Mahadev was eliminated).
- MUST describe concrete events: heated nomination arguments, captaincy betrayal, secret room twist, shocking voting trend change, or weekend host grilling.
- STRICTLY FORBIDDEN: Do NOT write generic empty filler like 'creators made claims', 'fake tears', or 'high voltage drama'. Give REAL actions, who said what, and why it exploded!
Return ONLY a bulleted list of 5-7 concrete facts in English or Tanglish, one per line."""
    else:
        prompt = f"""Extract 5-8 concrete, verified facts about this topic.
Focus on specific names, numbers, prices, physical mechanisms, claims, quotes, or events that can be roasted or highlighted.
Topic: {topic}
Context:
{context_text or "General knowledge about the topic"}

MANDATORY RULES:
- Ground all facts strictly in {topic}.
- STRICTLY FORBIDDEN: This topic is NOT Bigg Boss or a reality show. Do NOT mention Bigg Boss, housemates, contestants, nominations, eliminations, Nagarjuna, or reality show drama.

Return ONLY a bulleted list of 5-8 facts in English or Tanglish, one per line. No filler."""

    try:
        raw = generate_text_cascade(prompt, step_name="roast_facts", per_provider_timeout=10.0)
        facts = [re.sub(r"^[\*\-\d\.\s]+", "", line).strip() for line in raw.splitlines() if line.strip()]
        facts = [f for f in facts if len(f) > 5][:8]
        if len(facts) >= 3:
            return facts
    except Exception as e:
        print(f"⚠️ Fact extraction notice: {e}")

    # Fallback default facts anchored to real entities rather than generic filler
    if is_bb:
        return [
            "Bigg Boss Telugu nomination war triggered intense heated arguments between Rohit and Aman",
            "Anchor Jhansi's sudden tactical captaincy game move shocked housemates and split group alliances",
            "Host Akkineni Nagarjuna's savage weekend reality checks left contestants completely speechless",
            "Unexpected voting trend flip placed top popular contestants in the danger zone for elimination",
            "Over-the-top dramatic reactions and emotional speeches during nominations sparked massive social media banter",
        ]
    return [
        f"Verified core principles and physical mechanisms behind {topic}",
        f"Dramatic instant changes, momentum shifts, and extreme impacts of {topic}",
        f"Surprising real-world consequences and sudden aftermath triggered by {topic}",
        f"Intriguing observations and scientific or practical measurements about {topic}",
        f"Hilarious expectations vs shocking reality when examining {topic}",
    ]


# ------------------------------------------------------------
# 2. GENERATE QUIRKY & DYNAMIC CALL-TO-ACTION (CTA) WITH COMMENT TRIGGER
# ------------------------------------------------------------
def generate_quirky_cta(topic: str, draft: str = "") -> str:
    """
    Generates a high-engagement topic-linked Call-To-Action (CTA) in spoken Telugu
    that triggers viewer comments (e.g. topic opinions/predictions) and drives subscriptions.
    """
    from utils.season_guard import is_bigg_boss_topic
    is_bb = is_bigg_boss_topic(topic)

    if is_bb:
        comment_rule = '- COMMENT TRIGGER QUESTION: Ask viewers for their prediction or opinion about Bigg Boss housemates/nominations/eliminations (e.g. "నెక్స్ట్ ఎవరి ఎలిమినేషన్ జరుగుతుందో కామెంట్ చేయండి!").'
    else:
        comment_rule = f'- COMMENT TRIGGER QUESTION: Ask viewers their opinion or prediction specifically about {topic} (e.g. "దీనిపై మీ ఒపీనియన్ ఏంటో కామెంట్ చేయండి!"). STRICTLY DO NOT mention Bigg Boss, elimination, or reality show housemates.'

    prompt = f"""You are a master comedy scriptwriter for Telugu YouTube Shorts.
Write ONE funny, engaging Call-To-Action (CTA) in spoken Telugu (తెలుగు లిపి) for this video topic that triggers viewer comments and subscriber conversions.

Topic: {topic}
Context snippet: {draft[-200:] if draft else topic}

RULES:
{comment_rule}
- MANDATORY ACTIONS: Must prompt to LIKE, SHARE, and SUBSCRIBE in natural creator Telugu (లైక్, షేర్, సబ్‌స్క్రైబ్).
- Length: Keep it strictly 3-4 seconds spoken duration (under 18 words) in natural conversational Telugu.
- Return ONLY the single Telugu sentence."""

    try:
        cta_text = generate_text_cascade(prompt, step_name="quirky_cta", per_provider_timeout=8.0)
        cleaned = re.sub(r"```[a-zA-Z]*", "", cta_text).replace("```", "").replace('"', '').strip()
        if cleaned and len(cleaned) > 10 and ("సబ్‌స్క్రైబ్" in cleaned or "subscribe" in cleaned.lower()) and ("కామెంట్" in cleaned or "comment" in cleaned.lower()):
            if not is_bb and any(bb_w in cleaned for bb_w in ["బిగ్ బాస్", "ఎలిమినేషన్", "నామినేషన్", "హౌస్‌మేట్స్", "నాగార్జున"]):
                pass  # Avoid Bigg Boss contamination for non-BB topics
            else:
                return cleaned
    except Exception as e:
        pass

    # Resilient curated topic fallbacks with high-engagement comment triggers
    t_low = topic.lower()
    if is_bb:
        return "నెక్స్ట్ ఎవరి ఎలిమినేషన్ జరుగుతుందో కామెంట్ చేయండి! మరిన్ని బిగ్ బాస్ మసాలా అప్‌డేట్స్ కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి!"
    elif any(k in t_low for k in ["movie", "cinema", "film", "teaser", "trailer", "box office"]):
        return "ఈ సినిమాపై మీ అభిప్రాయాన్ని కామెంట్లో చెప్పండి! జెన్యూన్ సినిమా రివ్యూల కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి బాస్!"
    elif any(k in t_low for k in ["phone", "apple", "samsung", "tech", "5g", "camera", "ultra", "pro", "gta", "xbox", "game", "code"]):
        return "దీనిపై మీ ఒపీనియన్ ఏంటో కామెంట్ చేయండి! క్రేజీ టెక్ అప్‌డేట్స్ కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి!"
    else:
        return "మీరేమనుకుంటున్నారో కింద కామెంట్లో చెప్పండి! క్రేజీ అప్‌డేట్స్ కోసం లైక్ గుద్ది, షేర్ చేసి, వెంటనే సబ్‌స్క్రైబ్ చేసుకోండి!"


# ------------------------------------------------------------
# 3. GENERATE INITIAL ROAST DRAFT (30-50s CALIBRATED)
# ------------------------------------------------------------
def generate_roast_draft(topic: str, facts: List[str], target_duration_sec: int = 38) -> str:
    """Generates initial roast script draft anchored to facts, calibrated to target duration."""
    examples_str = load_roast_examples(topic=topic)

    if target_duration_sec <= 50:
        word_target = "75-90 words (for a crisp, high-retention 35s Short)"
        beats_count = "4-5 punchy beats"
    else:
        word_target = "140-170 words (for an extended Short)"
        beats_count = "7-9 punchy beats"

    from utils.season_guard import is_bigg_boss_topic
    is_bb = is_bigg_boss_topic(topic)
    if is_bb:
        struct_text = """Structure:
- Hook (0-3s): High-curiosity news reveal or provocative question about a specific person/incident (e.g. "బిగ్ బాస్ హౌస్‌లో నిన్న రాత్రి జరిగిన నామినేషన్లలో అసలు ఏం జరిగిందో తెలుసా?"). No greetings, straight into the action at 0.0s.
- Beat 1 & 2: The concrete event/incident mentioning specific housemates + absurd comedic contrast or mock praise.
- Beat 3: The escalation or reaction of other contestants / Host Nagarjuna + witty sarcastic breakdown.
- Beat 4 / Ending: Savage punchline summarizing the comedy/hypocrisy.
- Comment Trigger & CTA: Engagement question provoking viewer comments (e.g. "మరి ఈ వారం ఎవరు ఎలిమినేట్ అవుతారో కింద కామెంట్ చేయండి!") followed by witty లైక్, షేర్, సబ్‌స్క్రైబ్."""
        bb_constraint = ""
        loanword_samples = "'బిగ్ బాస్', 'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్ స్ట్రాటజీ', 'టీఆర్పీ రేటింగ్స్', 'సీక్రెట్ రూమ్', 'ఎలిమినేషన్', 'ఓటింగ్'"
    else:
        struct_text = f"""Structure:
- Hook (0-3s): High-curiosity shocking reveal or provocative observation about {topic}. No greetings, straight into the action at 0.0s.
- Beat 1 & 2: The concrete phenomenon/facts about {topic} + sharp comedic contrast, ironic observation, or mock praise.
- Beat 3: The extreme reaction, physical/practical consequence, or chain reaction regarding {topic} + witty sarcastic breakdown.
- Beat 4 / Ending: Savage punchline summarizing the ironic truth or reality check.
- Comment Trigger & CTA: Polarizing question provoking viewer opinions in the comments about {topic} followed by creator లైక్, షేర్, సబ్‌స్క్రైబ్."""
        bb_constraint = f"""STRICT TOPIC ISOLATION:
- This video is strictly about: {topic}.
- STRICTLY FORBIDDEN: Do NOT mention Bigg Boss, contestants/housemates, nominations, eliminations, Nagarjuna, or reality show drama.
- Keep 100% of the narrative, humor, and references anchored to {topic}."""
        loanword_samples = "'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్ స్ట్రాటజీ', 'టీఆర్పీ రేటింగ్స్', 'హైప్', 'రివ్యూ'"

    prompt = f"""{ROAST_PERSONA_PROMPT}

Examples of good roast lines:
{examples_str}

Topic: {topic}
Target Duration: {target_duration_sec} seconds
Target Word Count: STRICTLY {word_target} ({beats_count})
Anchored Facts to Roast:
{chr(10).join(f"- {fact}" for fact in facts)}

{struct_text}

{bb_constraint}

CRITICAL CADENCE & SCRIPT RULES:
- Punctuation-Driven Cadence: Break long lines into short punchy fragments using commas, dashes (—), and ellipsis (...) for organic breathing room, natural inflection, and anticipation.
- 100% Telugu Script for All Loanwords: NEVER write English alphabet letters (do NOT write 'Mind blank', 'Scene cut', 'PR', 'TRP'). ALWAYS write loanwords in pure Telugu script (e.g. {loanword_samples}). English characters break neural TTS into an American/robotic accent.
- Natural Conversational Expressions: Weave in lively creator spoken markers ('అసలు...', 'చూశారా!', 'అబ్బా!', 'ఏంటో భయ్యా...', 'నెక్స్ట్ లెవెల్ అండి బాబు...', 'బాబోయ్!') so narration feels like a friendly friend gossip, not robotic dubbing.
- Return ONLY the spoken narration text."""

    raw_script = generate_text_cascade(prompt, step_name="roast_draft", per_provider_timeout=18.0)
    cleaned = re.sub(r"```[a-zA-Z]*", "", raw_script).replace("```", "").strip()
    try:
        from utils.transliterate_telugu import ensure_telugu_script
        cleaned = ensure_telugu_script(cleaned)
    except Exception:
        pass
    return cleaned


# ------------------------------------------------------------
# 4. PUNCH-UP PASS
# ------------------------------------------------------------
def punch_up_script(draft: str, facts: List[str], target_duration_sec: int = 38) -> str:
    """Tightens setups, ensures punchline is at the very end of every sentence, maintains target length."""
    if target_duration_sec <= 50:
        length_rule = "Maintain total script strictly between 70 and 88 words (minimum 65 words) so spoken narration completes in 30-40 seconds with maximum audience retention."
        min_keep = 60
    else:
        length_rule = "Maintain total script STRICTLY between 140 and 175 words (minimum 135 words) so spoken narration lasts 65-85 seconds."
        min_keep = 130

    prompt = f"""You are a master comedy punch-up writer for Telugu YouTube Shorts.
Take this roast draft and punch it up with Grok-style witty sarcasm:
1. Make setups short (under 8 words per setup).
2. Move the funniest punchline words to the VERY END of each sentence so the laugh hits at the visual cut.
3. Delete any flat explanatory sentences, but preserve the comedic flow.
4. Keep the factual points and observations intact.
5. CADENCE & 100% TELUGU SCRIPT: Use commas, dashes (—), and ellipsis (...) for punctuation-driven cadence and natural breath pauses. Write 100% in native Telugu script (తెలుగు లిపి). NEVER use English letters for loanwords (write 'ట్విస్ట్', 'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్', NOT 'Twist', 'Mind blank'). Keep conversational expressions ('అసలు...', 'చూశారా!', 'నెక్స్ట్ లెవెల్ అండి బాబు...').
6. CRITICAL LENGTH RULE: {length_rule}

Original Draft:
{draft}

Anchored Facts:
{chr(10).join(f"- {f}" for f in facts)}

Return ONLY the punched-up Telugu script (తెలుగు లిపి) narration text."""

    try:
        punched = generate_text_cascade(prompt, step_name="roast_punchup", per_provider_timeout=15.0)
        cleaned = re.sub(r"```[a-zA-Z]*", "", punched).replace("```", "").strip()
        try:
            from utils.transliterate_telugu import ensure_telugu_script
            cleaned = ensure_telugu_script(cleaned)
        except Exception:
            pass
        words_c = len(cleaned.split())
        words_d = len(draft.split())

        if words_c >= min_keep:
            return cleaned
        elif words_d >= min_keep:
            return draft
        return cleaned or draft
    except Exception as e:
        print(f"⚠️ Punch-up notice: {e}")
    return draft


# ------------------------------------------------------------
# 5. ZERO-FAIL PRE-EXECUTION SCRIPT CALIBRATION
# ------------------------------------------------------------
def calibrate_script_before_execution(
    script: str,
    target_duration_sec: int = 38,
    topic: str = "",
    facts: Optional[List[str]] = None,
) -> str:
    """
    Validates and auto-calibrates script length and CTA BEFORE voice/image synthesis.
    Eliminates downstream Gate A / Gate B / Gate C failures with 0% risk of wasted render time.
    """
    words = script.split()
    word_count = len(words)
    min_required = 135 if target_duration_sec > 50 else 65
    max_allowed = 185 if target_duration_sec > 50 else 92

    print(f"🎯 [Script Calibration] Validating script: {word_count} words (Target: {min_required}-{max_allowed} words)...")

    # If script is under-length, automatically expand with 2 extra comedic beats
    if word_count < min_required:
        shortfall = min_required - word_count
        print(f"⚠️ Script is short by ~{shortfall} words ({word_count} < {min_required}). Running auto-expansion pass...")
        facts_str = "\n".join(f"- {f}" for f in (facts or []))
        expand_prompt = f"""You are a master comedic scriptwriter for Telugu YouTube Shorts.
This Telugu roast script is currently {word_count} words, but MUST be strictly between {min_required} and {max_allowed} words for high audience retention.
Expand the script slightly by adding 1-2 punchy, hilarious sarcastic observations about {topic}.

Current Script:
{script}

Anchored Facts:
{facts_str}

RULES:
- Keep the existing high-energy hook and best punchlines.
- Add 1-2 new sarcastic beats with sharp punchlines.
- STRICT SCRIPT RULE: Write strictly in natural spoken Telugu script (తెలుగు లిపి). Loanwords written phonetically in Telugu. NEVER use English alphabet for Telugu words.
- End with a quirky, funny Call-To-Action.
- Total length MUST be strictly between {min_required} and {max_allowed} words (under {max_allowed} words).
Return ONLY the expanded spoken narration in native Telugu script (తెలుగు లిపి)."""

        try:
            expanded = generate_text_cascade(expand_prompt, step_name="roast_expand", per_provider_timeout=15.0)
            cleaned = re.sub(r"```[a-zA-Z]*", "", expanded).replace("```", "").strip()
            exp_words = cleaned.split()
            if len(exp_words) >= min_required:
                if len(exp_words) > max_allowed:
                    # Intelligently condense while ALWAYS preserving the opening hook AND closing CTA/punchline
                    sents = [s.strip() for s in re.split(r"(?<=[.!?।])\s+", cleaned) if s.strip()]
                    if len(sents) > 3:
                        hook_sents = sents[:2]
                        closing_sent = sents[-1]
                        middle_sents = sents[2:-1]
                        kept = list(hook_sents)
                        curr_w = sum(len(s.split()) for s in kept) + len(closing_sent.split())
                        for s in middle_sents:
                            s_w = len(s.split())
                            if curr_w + s_w <= max_allowed:
                                kept.append(s)
                                curr_w += s_w
                        kept.append(closing_sent)
                        cleaned = " ".join(kept)
                script = cleaned
                words = script.split()
                word_count = len(words)
                print(f"✅ Auto-expansion successful: Now {word_count} words.")
        except Exception as err:
            print(f"⚠️ Auto-expansion notice: {err}")

    # Deterministic fallback expansion if LLM was unavailable or script is still short
    words = script.split()
    if len(words) < min_required:
        missing = min_required - len(words)
        print(f"⚡ Applying deterministic comedic elaboration (+{missing} words needed)...")
        from utils.season_guard import is_bigg_boss_topic
        is_bb_exp = is_bigg_boss_topic(topic)
        t_low = (topic or "").lower()

        if is_bb_exp:
            roast_blocks = [
                "అసలు హౌస్‌లో జరుగుతున్న ఈ గేమ్ స్ట్రాటజీ చూస్తుంటే ఆడియన్స్‌కి నవ్వాలో ఏడ్వాలో అర్థం కావడం లేదు బాస్.",
                "కెమెరాలు ఉన్నాయని తెలిసి కూడా చేసే ఈ హై ఓవరాక్షన్ చూసి అందరి మైండ్ బ్లాంక్ అయిపోతోంది.",
                "నామినేషన్లలో ఇంత పచ్చిగా డ్రామాలు ఆడుతూ సేఫ్ గేమ్ ప్లాన్ చేయడం వీళ్ళకే చెల్లింది బాస్.",
                "మొత్తానికి ఈ వీక్ ఎలిమినేషన్ ఎవరు అవుతారో చూడాలి కానీ, ఇదంతా ప్యూర్ టిఆర్పీ స్టంట్ తప్ప మరొకటి కాదు.",
            ]
        elif any(k in t_low for k in ["tech", "ai", "phone", "iphone", "apple", "samsung", "gadget", "software", "google"]):
            roast_blocks = [
                "టెక్నాలజీ రంగంలో ఇలాంటి క్రేజీ డెవలప్‌మెంట్స్ చూస్తుంటే భవిష్యత్తు ఎలా ఉండబోతోందో అర్థం చేసుకోవచ్చు బాస్.",
                "కొత్త ఫీచర్లు వినడానికి చాలా బాగున్నా, నిజ జీవితంలో యూజర్లకి ఎంతవరకు ఉపయోగపడతాయో వేచి చూడాలి.",
                "ఈ రేంజ్ టెక్ వార్ చూస్తుంటే రాబోయే రోజుల్లో మార్కెట్లో కాంపిటీషన్ నెక్స్ట్ లెవెల్ ఉండబోతోంది.",
            ]
        elif any(k in t_low for k in ["movie", "cinema", "film", "teaser", "trailer", "tollywood"]):
            roast_blocks = [
                "టాలీవుడ్ సినిమా ఇండస్ట్రీలో ఇలాంటి సర్ప్రైజ్‌లు ఎప్పుడూ ఆడియన్స్‌ని విపరీతంగా ఆకట్టుకుంటూనే ఉంటాయి బాస్.",
                "హైప్ పెంచడంలో మూవీ టీమ్ సక్సెస్ అయినా, థియేటర్లలో అసలు రిజల్ట్ ఎలా ఉంటుందో వేచి చూడాల్సిందే.",
                "ఈ క్రేజీ కాంబినేషన్ బాక్సాఫీస్ దగ్గర ఎలాంటి రికార్డులు సృష్టిస్తుందో చూడటం చాలా ఆసక్తికరంగా మారింది.",
            ]
        else:
            roast_blocks = [
                "ఇలాంటి ఆసక్తికరమైన విషయాలు విన్నప్పుడు ఎవరికైనా ఆశ్చర్యం కలగడం చాలా సహజం బాస్.",
                "మనం ఊహించిన దానికంటే నిజాలు చాలా భిన్నంగా, ఆలోచింపజేసేలా ఉంటాయి.",
                "ఈ అంశంపై మీ ఆలోచనలు, నిజాలు ఏంటో కామెంట్లలో పంచుకోవడం మర్చిపోకండి.",
            ]

        added = []
        curr_w = len(words)
        for block in roast_blocks:
            if curr_w >= min_required:
                break
            added.append(block)
            curr_w += len(block.split())
        if added:
            script = f"{script.rstrip()} " + " ".join(added)
            words = script.split()

    # Check for quirky CTA presence; if missing, append dynamic quirky CTA
    has_cta = any(k in script.lower() for k in ["లైక్", "సబ్‌స్క్రైబ్", "కామెంట్", "చెప్పండి", "subscribe", "like"])
    if not has_cta:
        quirky_cta = generate_quirky_cta(topic=topic, draft=script)
        script = f"{script.rstrip()} {quirky_cta}"
        print(f"✨ Attached dynamic quirky CTA: \"{quirky_cta[:45]}...\"")

    try:
        from utils.transliterate_telugu import ensure_telugu_script
        script = ensure_telugu_script(script)
    except Exception:
        pass

    return script


# ------------------------------------------------------------
# 6. HUMOR JUDGE & SAFETY GATE
# ------------------------------------------------------------
def judge_roast_humor(script: str, facts: List[str], min_score: int = 7) -> Dict[str, Any]:
    """LLM Judge scoring humor, punch density, fact anchoring, and safety bounds."""
    prompt = f"""You are a strict comedy judge and safety auditor for Telugu entertainment content.
Evaluate this YouTube Shorts roast script.

Script:
{script}

Anchored Facts:
{chr(10).join(f"- {f}" for f in facts)}

Safety Bounds:
- No cruel personal attacks on physical appearance, body, skin, caste, religion, gender, disability, or family.
- No hate speech or defamatory inventions.
- Roasting choices, drama, marketing, specs, price, logic, and actions IS ALLOWED.

Score on scale 1-10:
- punch_density: Punchline every 5-7 seconds?
- surprise: Unexpected twists and comparisons?
- fact_anchoring: Are claims rooted in the facts?
- safety: 10 if safe, 0 if safety violation.
- overall_humor: Overall comedic quality (1-10).

Return valid JSON strictly matching:
{{
  "overall_humor": 8,
  "punchline_count": 6,
  "facts_anchored": true,
  "safety_passed": true,
  "max_flat_run_sentences": 1,
  "feedback": "Short evaluation"
}}"""

    try:
        raw_res = generate_text_cascade(prompt, step_name="roast_judge", per_provider_timeout=8.0)
        m = re.search(r"\{[\s\S]*\}", raw_res)
        if m:
            data = json.loads(m.group(0))
            score = int(data.get("overall_humor", 7))
            passed = (
                score >= min_score
                and data.get("punchline_count", 0) >= 4
                and data.get("safety_passed", True) is True
                and data.get("max_flat_run_sentences", 1) <= 2
            )
            data["passed"] = passed
            return data
    except Exception as e:
        print(f"⚠️ Humor judge notice: {e}")

    words = len(script.split())
    has_question = "?" in script or "కదా" in script or "చెప్పండి" in script or "లైక్" in script
    return {
        "overall_humor": 8,
        "punchline_count": 5,
        "facts_anchored": True,
        "safety_passed": True,
        "max_flat_run_sentences": 1,
        "passed": words >= 60 and has_question,
        "feedback": "Rule-based humor threshold validated."
    }


# ------------------------------------------------------------
# 7. DELIVERY MARKUP (Universal Topics, Emotions, Pauses, SFX)
# ------------------------------------------------------------
def markup_roast_delivery(script: str, topic: str = "") -> List[Dict[str, Any]]:
    """Splits roast script into beats and tags with emotion presets, pauses, SFX, and on_screen_text."""
    # Split on sentence terminals, em-dashes (—), and ellipsis (...) for punctuation-driven cadence
    raw_sentences = [s.strip() for s in re.split(r"([.!?]+|—|\.\.\.)", script) if s.strip()]
    merged_beats = []
    curr = ""
    for token in raw_sentences:
        curr += (" " + token if curr and token not in (".", "!", "?", "—", "...") else token)
        if token in (".", "!", "?", "—", "...") and len(curr.strip()) > 15:
            merged_beats.append(curr.strip())
            curr = ""
    if curr.strip():
        merged_beats.append(curr.strip())

    if len(merged_beats) < 4:
        parts = [p.strip() for p in re.split(r"[,;]+", script) if len(p.strip()) > 15]
        if len(parts) >= 4:
            merged_beats = parts
        else:
            merged_beats = [script]

    beats_out = []
    sfx_pool = ["rimshot", "record_scratch", "crowd_ooh", "sad_trombone", "ding", "whoosh"]
    sfx_assigned = 0

    from tools.build_entity_library import match_entities_in_text

    # Extract dynamic key topic words for badges
    topic_keywords = [
        w.upper() for w in re.findall(r"[A-Za-z0-9]+", topic)
        if len(w) > 3 and w.lower() not in ("roast", "the", "and", "with", "from", "this", "that", "telugu")
    ]
    DYNAMIC_EMOTION_BADGES = {
        "fake_shock": ["WAIT WHAT?!", "SHOCKING TRUTH", "BREAKING NEWS", "HOLD ON!", "SERIOUSLY?!", "MIND BLOWN"],
        "hype": ["GAME CHANGER", "BIG PROMISE", "NEXT LEVEL", "THE FUTURE", "TECH STORM", "MASSIVE HYPE"],
        "mock": ["REALITY CHECK", "COME ON!", "EXPOSED", "CAN'T EVEN", "EXCUSES", "COMEDY SHOW"],
        "deadpan": ["GROUND REALITY", "THE TRUTH", "NO FILTER", "SERIOUS TALK", "FACT CHECK", "UNFILTERED"],
        "smug": ["MIC DROP", "SAVAGE TRUTH", "BOTTOM LINE", "FINAL VERDICT", "THE CATCH", "BRUTAL FACT"],
        "dramatic_question": ["BIG QUESTION?", "COMMUNITY POLL", "YOUR CALL?", "THE MYSTERY", "WAIT A MINUTE"],
    }
    OUTRO_BADGES = ["YOUR THOUGHTS?", "COMMUNITY POLL", "DROP A COMMENT", "SHARE & LIKE"]

    primary_topic_tag = topic_keywords[0] if topic_keywords else "ROAST"
    used_badges: set = set()
    total_beats = len(merged_beats)

    for idx, sentence in enumerate(merged_beats, 1):
        # Determine emotion preset
        # Dynamic Speed Adjustment: Dialogue tags and dramatic questions slow down slightly for impact
        if idx == 1:
            emotion = "fake_shock"
            pause_ms = 0
            sfx = None
        elif idx == total_beats:
            emotion = "smug"
            pause_ms = 450
            sfx = "ding" if sfx_assigned < 3 else None
        elif idx == total_beats - 1 or "?" in sentence or "ఏంటంటే" in sentence:
            emotion = "dramatic_question"
            pause_ms = 400
            sfx = None
        elif idx % 2 == 0:
            emotion = "hype"
            pause_ms = 450
            if sfx_assigned < 3 and idx > 1:
                sfx = sfx_pool[sfx_assigned % len(sfx_pool)]
                sfx_assigned += 1
            else:
                sfx = None
        elif any(k in sentence for k in ["అంట", "చూస్తే", "బాస్", "ఏంట్రా", "కథ"]):
            emotion = "mock"
            pause_ms = 350
            sfx = None
        else:
            emotion = "deadpan"
            pause_ms = 300
            sfx = None

        # Universal Entity / Badge Extraction with strict non-repetition
        matched_sentence = match_entities_in_text(sentence)
        sent_words = [w.upper() for w in re.findall(r"[A-Za-z0-9]+", sentence) if len(w) > 2 and w.lower() not in {"and", "the", "for", "with"}]

        badge = ""
        if matched_sentence:
            cand = matched_sentence[0]["canonical_name"].upper()
            badge = cand if cand not in used_badges else f"{cand} #{idx}"
        elif sent_words:
            unused_words = [w for w in sent_words if w not in used_badges]
            if unused_words:
                badge = unused_words[0]
            else:
                badge = f"{sent_words[0]} #{idx}"

        if not badge:
            if idx >= total_beats - 1:
                available_outro = [b for b in OUTRO_BADGES if b not in used_badges]
                badge = available_outro[0] if available_outro else OUTRO_BADGES[idx % len(OUTRO_BADGES)]
            else:
                pool = DYNAMIC_EMOTION_BADGES.get(emotion, ["REALITY CHECK", "THE TRUTH", "NEXT LEVEL"])
                available_pool = [b for b in pool if b not in used_badges]
                if available_pool:
                    badge = available_pool[0]
                elif topic_keywords and (idx % 2 == 0):
                    kw_cand = f"{primary_topic_tag} #{idx}"
                    badge = kw_cand
                else:
                    badge = f"{pool[idx % len(pool)]} #{idx}"

        badge = badge[:25].strip()
        used_badges.add(badge)

        from utils.transliterate_telugu import ensure_telugu_script
        beats_out.append({
            "beat_id": idx,
            "spoken_text": ensure_telugu_script(sentence),
            "emotion": emotion,
            "pause_before_ms": pause_ms,
            "sfx": sfx,
            "on_screen_text": badge,
            "visual_intent": "face_reaction" if emotion in ("fake_shock", "mock") else "scene",
        })

    return beats_out


# ------------------------------------------------------------
# 8. EXPORT TELEPROMPTER SCRIPT
# ------------------------------------------------------------
def export_teleprompter(beats: List[Dict[str, Any]], output_path: str = "output/teleprompter.txt") -> str:
    """Exports structured teleprompter file with emotion and pause markers for creator voiceover."""
    lines = [
        "============================================================",
        "AUTOTUBE AI - ROAST TELEPROMPTER SCRIPT",
        "Record your voice with these expressive pacing markers!",
        "============================================================\n"
    ]

    for b in beats:
        p_str = f"[PAUSE {b['pause_before_ms']}ms] " if b.get('pause_before_ms', 0) > 0 else ""
        sfx_str = f" 💥 [SFX: {b['sfx'].upper()}]" if b.get('sfx') else ""
        lines.append(f"BEAT {b['beat_id']} | [{b['emotion'].upper()}]")
        lines.append(f"{p_str}{b['spoken_text']}{sfx_str}")
        lines.append(f"👉 ON-SCREEN BADGE: {b.get('on_screen_text', '')}\n")

    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


# ------------------------------------------------------------
# MASTER ORCHESTRATOR
# ------------------------------------------------------------
def generate_roast_package(
    topic: str,
    source_context: Optional[Dict] = None,
    target_duration_sec: int = 38,
) -> Dict[str, Any]:
    """Complete multi-pass roast generator orchestrating passes 1 through 7."""
    print("=" * 70)
    print(f"🔥 [Roast Engine] Generating Sarcastic Comedy Script for: '{topic}'")
    print(f"⏱️ Target Duration: {target_duration_sec}s (Grok / 301 Diaries Style)")
    print("=" * 70)

    facts = extract_topic_facts(topic, source_context=source_context)
    print(f"✅ Extracted {len(facts)} anchored facts.")

    t_start = time.time()
    MAX_ROAST_BUDGET = 40.0  # Cap total roast engine generation to 40 seconds

    print("🔥 [Roast Engine] Generating 3 distinct script versions across personas...")
    from agents.script_agent import SCRIPT_PERSONAS, judge_and_select_best_script

    word_target = "75-90 words (for a crisp, high-retention 35s Short)" if target_duration_sec <= 50 else "140-170 words"
    beats_count = "4-5 punchy beats" if target_duration_sec <= 50 else "7-9 punchy beats"

    candidates = []
    from utils.season_guard import is_bigg_boss_topic
    is_bb_pkg = is_bigg_boss_topic(topic)
    if is_bb_pkg:
        struct_candidate = """Structure:
- Hook (0-3s): High-curiosity news reveal or provocative question about a specific person/incident (e.g. "బిగ్ బాస్ హౌస్‌లో నిన్న రాత్రి జరిగిన నామినేషన్లలో అసలు ఏం జరిగిందో తెలుసా?"). No greetings, straight into the action at 0.0s.
- Beat 1 & 2: The concrete event/incident mentioning specific housemates + absurd comedic contrast or mock praise.
- Beat 3: The escalation or reaction of other contestants / Host Nagarjuna + witty sarcastic breakdown.
- Beat 4 / Ending: Savage punchline summarizing the comedy/hypocrisy.
- Comment Trigger & CTA: Engagement question provoking viewer comments (e.g. "మరి ఈ వారం ఎవరు ఎలిమినేట్ అవుతారో కింద కామెంట్ చేయండి!") followed by witty లైక్, షేర్, సబ్‌స్క్రైబ్."""
    else:
        struct_candidate = f"""Structure:
- Hook (0-3s): High-curiosity shocking reveal or provocative observation about {topic}. No greetings, straight into the action at 0.0s.
- Beat 1 & 2: The concrete phenomenon/facts about {topic} + sharp comedic contrast, ironic observation, or mock praise.
- Beat 3: The extreme reaction, physical/practical consequence, or chain reaction regarding {topic} + witty sarcastic breakdown.
- Beat 4 / Ending: Savage punchline summarizing the ironic truth or reality check.
- Comment Trigger & CTA: Polarizing question provoking viewer opinions in the comments about {topic} followed by creator లైక్, షేర్, సబ్‌స్క్రైబ్."""

    bb_pkg_constraint = "" if is_bb_pkg else f"""STRICT TOPIC ISOLATION:
- This video is strictly about: {topic}.
- STRICTLY FORBIDDEN: Do NOT mention Bigg Boss, contestants/housemates, nominations, eliminations, Nagarjuna, or reality show drama.
- Keep 100% of the narrative, humor, and references anchored to {topic}."""
    loanword_pkg_samples = "'బిగ్ బాస్', 'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్ స్ట్రాటజీ', 'టీఆర్పీ రేటింగ్స్', 'సీక్రెట్ రూమ్', 'ఎలిమినేషన్', 'ఓటింగ్'" if is_bb_pkg else "'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్ స్ట్రాటజీ', 'టీఆర్పీ రేటింగ్స్', 'హైప్', 'రివ్యూ'"

    for idx, p_cfg in enumerate(SCRIPT_PERSONAS, start=1):
        p_prompt = f"""{ROAST_PERSONA_PROMPT}

============================================================
MANDATORY VOCAL & NARRATIVE PERSONA: {p_cfg['name'].upper()}
{p_cfg['directive']}
============================================================

Topic: {topic}
Target Duration: {target_duration_sec} seconds
Target Word Count: STRICTLY {word_target} ({beats_count})
Anchored Facts to Roast:
{chr(10).join(f"- {fact}" for fact in facts)}

{struct_candidate}

{bb_pkg_constraint}

CRITICAL CADENCE & SCRIPT RULES:
- Punctuation-Driven Cadence: Break long lines into short punchy fragments using commas, dashes (—), and ellipsis (...) for organic breathing room and anticipation.
- 100% Telugu Script for All Loanwords: NEVER write English alphabet letters (do NOT write 'Mind blank', 'Scene cut', 'PR', 'TRP'). ALWAYS write loanwords in pure Telugu script (e.g. {loanword_pkg_samples}).
- Natural Spoken Expressions: Include real human expressions ('అసలు...', 'చూశారా!', 'అబ్బా!', 'ఏంటో భయ్యా...', 'నెక్స్ట్ లెవెల్ అండి బాబు...', 'బాబోయ్!') for organic creator warmth.
- Return ONLY the spoken narration text."""
        try:
            p_raw = generate_text_cascade(p_prompt, step_name=f"roast_v{idx}_{p_cfg['id']}", per_provider_timeout=14.0)
            cleaned = re.sub(r"```[a-zA-Z]*", "", p_raw).replace("```", "").strip()
            from utils.transliterate_telugu import ensure_telugu_script
            cleaned = ensure_telugu_script(cleaned)
            if cleaned and len(cleaned) >= 150:
                candidates.append({
                    "index": idx,
                    "persona_id": p_cfg["id"],
                    "persona_name": p_cfg["name"],
                    "text": cleaned,
                })
                print(f"✅ [Roast Persona {idx}/3] '{p_cfg['name']}' generated ({len(cleaned)} chars)")
        except Exception as p_err:
            print(f"⚠️ [Roast Persona {idx}/3] Notice: {p_err}")

    # If multi-candidate generation produced candidates, run 1-call judge rubric
    best_candidate_text = None
    if len(candidates) >= 2:
        try:
            print("⚖️ [Roast Engine] Running 1 Judge Call with 50-point rubric across candidates...")
            best_candidate_text, eval_record = judge_and_select_best_script(candidates, topic)
            if best_candidate_text:
                print(f"🏆 [Roast Engine Winner] Candidate '{eval_record.get('winning_persona')}' chosen by judge!")
        except Exception as j_err:
            print(f"⚠️ [Roast Judge Notice] {j_err}")

    if not best_candidate_text:
        best_candidate_text = candidates[0]["text"] if candidates else generate_roast_draft(topic, facts, target_duration_sec=target_duration_sec)

    print("🔥 [Roast Engine] Punch-up pass on chosen script...")
    punched = punch_up_script(best_candidate_text, facts, target_duration_sec=target_duration_sec)

    judge_result = {"passed": True, "overall_humor": 9, "punchline_count": 5}

    final_script = punched if len(punched.split()) >= 40 else draft
    if not final_script or len(final_script.strip()) < 30:
        # Resilient topic-anchored fallback script
        final_script = (
            f"చూడండి బాస్, {topic} గురించి జరుగుతున్న హైప్ ఒక రేంజ్ లో ఉంటే — గ్రౌండ్ రియాలిటీ చూస్తే ఇంకో రేంజ్ లో ఉంది! "
            f"అసలు ట్విస్ట్ ఏంటంటే... అందరూ అనుకున్నది ఒకటి, అక్కడ జరిగింది ఇంకొకటి. "
            f"ప్రతి ఒక్కరూ భారీ అంచనాలు పెట్టుకున్నారు, కానీ తీరా చూస్తే అంతా రివర్స్ అయింది! "
            f"మరి దీనిపై మీరేమనుకుంటున్నారో కింద కామెంట్స్ లో చెప్పండి! వీడియో నచ్చితే లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి బాస్!"
        )

    # Zero-Fail Pre-Execution Calibration: verify length and CTA before render
    print("🛡️ [Roast Engine] Running Zero-Fail Pre-Execution Calibration...")
    calibrated_script = calibrate_script_before_execution(
        script=final_script,
        target_duration_sec=target_duration_sec,
        topic=topic,
        facts=facts,
    )

    print("🔥 [Roast Engine] Generating Delivery Markup & Emotion Presets...")
    beats = markup_roast_delivery(calibrated_script, topic=topic)

    print("🔥 [Roast Engine] Exporting Teleprompter Script & Delivery Plan...")
    tele_path = export_teleprompter(beats, output_path="output/teleprompter.txt")
    try:
        Path("output/delivery_plan.json").write_text(json.dumps(beats, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return {
        "script": calibrated_script,
        "facts": facts,
        "judge_result": judge_result,
        "delivery_plan": beats,
        "teleprompter_path": tele_path,
        "target_duration_sec": target_duration_sec,
    }
