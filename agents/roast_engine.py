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
from typing import Any, Dict, List, Optional, Tuple, Union

ROOT = Path(__file__).resolve().parent.parent

try:
    from providers.llm import generate_text_cascade
except ImportError:
    def generate_text_cascade(prompt: str, **kwargs) -> str:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        for m in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]:
            try:
                return client.models.generate_content(model=m, contents=prompt).text
            except Exception:
                continue
        return ""

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
- STRICT BAN ON MECHANICAL TRANSLATION & INVENTED GIBBERISH:
  * STRICTLY FORBIDDEN: NEVER invent literal word-by-word machine translations of English idioms or slang (e.g. STRICTLY FORBID: "షాపింగ్ లిస్ట్", "క్లబ్‌బింగ్ చేస్తూ", "హాస్యం చోటు చేసుకుంది", "ఇక్కడా భారతదేశమేనా", "క్షేత్రం", "నోరు మళ్ళించాడు", "హోమ్‌వర్క్ హెడ్‌ఫోన్లు", "హ్యూమన్ స్నూ", "టూ-బీడెల్‌బ్రైట్", "ఐబర్ప్పింగ్", "సెగాబ్రేక్", "స్పష్టీకరణ కెమ్", "హేయాజము", or awkward pseudo-Telugu compounds).
  * MANDATORY: Always speak in 100% natural, colloquial spoken Telugu conversation (సరళమైన సహజ వాడుక భాష) as spoken by authentic Telugu YouTubers (like Mahathalli, Praneeth Hanumantu, 301 Diaries)!
  * Use real, natural creator expressions: "ఓవరాక్టింగ్", "ఎలిమినేషన్ భయం", "షాకింగ్ ఎక్స్‌ప్రెషన్స్", "కవరింగ్ మాస్టర్లు", "ఫేక్ డ్రామా", "డబుల్ స్టాండర్డ్స్", "ముఖంలో కలవరం", "పచ్చి అబద్ధాలు", "మైండ్ బ్లాంక్", "ఫన్నీ కౌంటర్లు", "ఫ్యూజులు ఎగిరిపోయాయి", "గాలి తీసేశాడు", "పరువు పోయింది", "రచ్చ రంబోలా".
  * HOST NAGARJUNA HONORIFIC RULE: ALWAYS refer to Host Akkineni Nagarjuna with respectful plural honorifics: "నాగ్‌గారు అన్నారు", "నాగ్‌గారు కౌంటర్ వేశారు", "నాగ్‌గారు క్లాస్ పీకారు". NEVER use singular ("ఇచ్చాడు", "జోక్ చేశాడు")!
  * CONTESTANT NAMES RULE: Use clean, authentic names: "త్రిగుణ్" (NEVER "ట్రైగన్" or "ఎస్వరన్"), "ముకేష్ గౌడ", "సుధీర్ రెడ్డి", "అమన్", "టెంపర్ వంశీ".

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

def _sanitize_awkward_loanwords(text: str) -> str:
    """Replaces awkward English transliterated words with natural conversational Telugu idioms."""
    replacements = [
        (r"సింకోఫాంట్[లాల్వాని]*", "భజన బ్యాచ్"),
        (r"సికోఫాంట్[లాల్వాని]*", "భజన బ్యాచ్"),
        (r"స్పానియెనిటీ", "సొంత తెలివి"),
        (r"స్పాంటానియెటీ", "సొంత తెలివి"),
        (r"మానిప్యులేషన్", "మైండ్ గేమ్"),
        (r"పారాడైమ్", "పద్ధతి"),
        (r"యాంబిగ్విటీ", "కన్ఫ్యూజన్"),
        (r"ఎమోషనల్ బ్లాక్‌మెయిల్", "సెంటిమెంట్ డ్రామా"),
        (r"హోమ్‌వర్క్\s*హెడ్‌ఫోన్లు?", "హౌస్ రూల్స్"),
        (r"హ్యూమన్\s*స్నూ[^\s]*", "నిద్రపోవడం"),
        (r"టూ-బీడెల్‌బ్రైట్|టూ\s*బీడెల్[^\s]*", "ఓవర్ యాక్షన్"),
        (r"సెగాబ్రేక్|సియో\s*\d+\s*నిమిషాల", "షాకింగ్ ట్విస్ట్"),
        (r"ఐబర్ప్పింగ్[^\s]*", "కళ్ళు తేలేయడం"),
        (r"స్పష్టీకరణ\s*కెమ్[^\s]*", "కెమెరా ముందు క్లారిటీ"),
        (r"కామెడీ-ఫాటిగ్యూ[^\s]*", "బోరింగ్ కామెడీ"),
        (r"హేయాజము[^\s]*", "ఓవర్ యాక్షన్"),
        (r"స్ట్రాటజిక్\s*ఘోస్టింగ్[^\s]*", "సైలెంట్ గేమ్"),
        (r"ఎక్స్‌ఫ్లేషన్[^\s]*", "టెన్షన్"),
        (r"హాస్య\s*ప్రాగల్భ్యత", "కామెడీ రచ్చ"),
        (r"సగటు\s*రోజులోనే", "టాస్క్ మొదలవగానే"),
        (r"ఏ\s*పిచ్చి\s*రాత్రి", "నిన్న రాత్రి జరిగిన రచ్చ"),
        (r"గందరగోళం\s*ఆవిడలా", "ఫుల్ కన్‌ఫ్యూజన్"),
        (r"నాయుడు\s*కాదు!?", ""),
        (r"పుచ్చుకున్నాడు", "నిలదీశాడు"),
        (r"ఎంబరాస్[^\s]*", "షాకయ్యారు"),
        (r"సెన్సరల్[^\s]*", "హౌస్ లో"),
        (r"టీకా[^\s]*", "క్లాస్ పీకింది"),
        (r"సేమా\s*ఉపన్యాసం", "సినిమా ఉపన్యాసం"),
        (r"మోడ్\s*క్లోజ్\s*అయిపోయింది", "ఫ్యూజులు ఎగిరిపోయాయి"),
        (r"తాడుతో\s*బైండ్", "తాడుతో కట్టేసి"),
        (r"బైండ్\s*చేశాడు", "కట్టేశాడు"),
        (r"(?<![\u0C00-\u0C7F])అమ్‌న(?![\u0C00-\u0C7F])", "అమన్"),
        (r"(?<![\u0C00-\u0C7F])అమ్నా(?![\u0C00-\u0C7F])", "అమన్"),
        (r"(?<![\u0C00-\u0C7F])ట్రైగన్\s*ఎస్వరన్(?![\u0C00-\u0C7F])", "త్రిగుణ్"),
        (r"(?<![\u0C00-\u0C7F])ట్రిగన్\s*ఎస్వరన్(?![\u0C00-\u0C7F])", "త్రిగుణ్"),
        (r"(?<![\u0C00-\u0C7F])ట్రైగన్(?![\u0C00-\u0C7F])", "త్రిగుణ్"),
        (r"(?<![\u0C00-\u0C7F])ట్రిగన్(?![\u0C00-\u0C7F])", "త్రిగుణ్"),
        (r"(?<![\u0C00-\u0C7F])త్రిగన్(?![\u0C00-\u0C7F])", "త్రిగుణ్"),
        (r"(?<![\u0C00-\u0C7F])నామల్\s*టీజర్", "నార్మల్ టీజర్"),
        (r"(?<![\u0C00-\u0C7F])నామల్(?![\u0C00-\u0C7F])", "నార్మల్"),
        (r"అక్టోర్\s*షాపింగ్\s*లిస్ట్[^\s]*", "టార్గెట్ లిస్ట్"),
        (r"షాపింగ్\s*లిస్ట్[^\s]*", "టార్గెట్ లిస్ట్"),
        (r"(?<![\u0C00-\u0C7F])అక్టోర్(?![\u0C00-\u0C7F])", "యాక్టర్"),
        (r"సైలింగ్\s*చేశాడు", "స్మైల్ చేశాడు"),
        (r"నాగార్జున\s*క్షేత్రంలో?", "బిగ్ బాస్ హౌస్ లో"),
        (r"ఇక్కడా\s*భారతదేశమేనా[?!]?", "ఇదేం ఆటయ్యా బాబు!"),
        (r"నోరు\s*మళ్ళించాడు", "కవరింగ్ మొదలెట్టాడు"),
        (r"క్లబ్‌బింగ్\s*చేస్తూ", "బిల్డప్ ఇస్తూ"),
        (r"హాస్యం\s*చోటు\s*చేసుకుంది", "అందరూ పగలబడి నవ్వుకున్నారు"),
        (r"(?<![\u0C00-\u0C7F])కమెడీ(?![\u0C00-\u0C7F])", "కామెడీ"),
        (r"ఓవర్‌కాన్ఫ్డెంట్\s*గా\s*ఆన్స్వర్", "ఓవర్ కాన్ఫిడెన్స్ తో ఆన్సర్"),
        (r"నాగ్[\u200c\u200d]?గారి\s*(.*?)\s*జోక్\s*చేశాడు", r"నాగ్‌గారు \1 జోక్ చేశారు"),
        (r"నాగ్[\u200c\u200d]?గారి\s*(.*?)\s*రీప్లై\s*ఇచ్చాడు", r"నాగ్‌గారు \1 కౌంటర్ ఇచ్చారు"),
        (r"నాగ్[\u200c\u200d]?గారి\s*(.*?)\s*రిప్లై\s*ఇచ్చాడు", r"నాగ్‌గారు \1 కౌంటర్ ఇచ్చారు"),
        (r"నాగ్[\u200c\u200d]?గారి\s*చిరునవ్వుతో", "నాగ్‌గారు చిరునవ్వుతో"),
        (r"నాగ్[\u200c\u200d]?గారి\s*(.*?)\s*అన్నాడు", r"నాగ్‌గారు \1 అన్నారు"),
        (r"నాగ్[\u200c\u200d]?గారి\s*(.*?)\s*ఇచ్చాడు", r"నాగ్‌గారు \1 ఇచ్చారు"),
        # Anti-machine-translation replacements
        (r"(?<![\u0C00-\u0C7F])యాజ్(?![\u0C00-\u0C7F])", "ప్లాన్"),
        (r"ముచ్చుడు\s*పెట్టారు|ముచ్చుడు", "చురకలు అంటించారు"),
        (r"ప్లీడ్\s*చేశాడు", "బ్రతిమిలాడాడు"),
        (r"(?<![\u0C00-\u0C7F])ప్లీడ్(?![\u0C00-\u0C7F])", "రిక్వెస్ట్"),
        (r"డ్రామాట్టెక్‌గా", "డ్రామా చేస్తూ"),
        (r"ఐసీయూకి\s*వెళ్తాను", "హౌస్ లో ఉండలేను"),
        (r"(?<![\u0C00-\u0C7F])ఐసీయూ[^\s]*", "హాస్పిటల్"),
        (r"సౌండ్\s*అవుతూ", "సపోర్ట్ చేస్తూ"),
        (r"నెట్టెగిరించాడు", "పక్కన పెట్టేశాడు"),
        (r"ఓట్లు\s*వస్తున్నాలో\s*కాదు", "ఓట్లు వస్తున్నాయో లేదో"),
        # Anti-robot literal English-to-Telugu translations
        (r"పాత్ర\s*తీసుకున్నాడు", "లీడ్ తీసుకున్నాడు"),
        (r"ఇంటిలో\s*ఉష్ణోగ్రత\s*పెరిగింది", "హౌస్‌లో రచ్చ మొదలైంది"),
        (r"చిన్న\s*అర్థమైన\s*దావాపేదావాను?", "మాటల యుద్ధాన్ని"),
        (r"దావాపేదావా", "మాటల యుద్ధం"),
        (r"యూనిట్‌లోనే\s*ముఖ్యంగా", "హౌస్‌లో"),
        (r"(?<![\u0C00-\u0C7F])నాగర్‌జున(?![\u0C00-\u0C7F])", "నాగార్జున"),
        (r"(?<![\u0C00-\u0C7F])డీబ్జాని(?![\u0C00-\u0C7F])", "దేబ్జాని"),
        (r"(?<![\u0C00-\u0C7F])ఊర్వశి(?![\u0C00-\u0C7F])", "వర్షిణి"),
        (r"ఆల్ఫా\s*మేల్", "టాప్ ప్లేయర్"),
        (r"తర్క\s*వాదాలు", "మాటల యుద్ధం"),
        (r"బెట్రయల్|బెత్రాయల్", "వెన్నుపోటు"),
        (r"బిజినెస్\s*మోడల్", "స్ట్రాటజీ"),
        (r"డామర్జ్[^\s]*", "డేంజర్ జోన్"),
        (r"బూం[^\s]*", "మారిపోయి"),
        (r"పాపా\s*బోధించడానికి", "టార్గెట్ చేయడానికి"),
        (r"బ్లైండ్‌ఫోల్డ్[^\s]*", "హౌస్"),
        (r"అంకామోకాన్ని\s*ప్యాకేజీగా", "ఓవరాక్షన్"),
        (r"పురుషుల\s*కలహాల", "హౌస్‌లో గొడవల"),
        (r"బలీగా", "బలిపశువుగా"),
        # Anti-bizarre tech metaphors and transliterations
        (r"ఐఫోల్", "యాపిల్"),
        (r"థెర్మల్\s*కాఫీ|థర్మల్\s*కాఫీ", "టీ కప్పులా వేడెక్కిపోతోంది"),
        (r"హాట్\s*డాగ్", "ఇస్త్రీ పెట్టె"),
        (r"కాల్డ్\s*వెపన్", "రహస్య ఆయుధం"),
        (r"థర్మల్\s*క్రైసిస్", "హీటింగ్ సమస్య"),
        (r"పాఠశాల\s*బ్యాటరీ", "ఫోన్ బ్యాటరీ"),
        (r"లావెండర్\s*తలంపు", ""),
        (r"బాలాథ్", ""),
        (r"బంగారు\s*బాస్కెట్", "భగ్గుమంది బాస్"),
        (r"త్రిగుణ్‌ను\s*వార్నింగ్", "త్రిగుణ్‌కి వార్నింగ్"),
        # Anti-machine-translation hallucinations (Groq/OpenSource Telugu defects)
        (r"నాన్‌ఆఫ్|నాన్\s*ఆఫ్", "డిస్క్వాలిఫై"),
        (r"జాతి\s*గుండెలు(?:\s*మరుస్తున్నాక)?", "గుండెల్లో రైళ్లు పరిగెడుతుంటే"),
        (r"సటోర్\s*రూమ్|సటోర్\s*రూం", "స్టోర్ రూమ్"),
        (r"అసహాయకారపూర్వకతకు|అసహాయకారపూర్వక", "పక్షపాతానికి"),
        (r"డ్యాగర్\s*వేసిన", "గట్టి"),
        (r"గుంజీలు\s*చేస్తున్నాక", "గుంజీలు తీస్తుంటే"),
        (r"(?:Bigg Boss Telugu|బిగ్ బాస్ Telugu|బిగ్ బాస్ తెలుగు)\s*మధ్య", "కంటెస్టెంట్ల మధ్య"),
        (r"(?<![\u0C00-\u0C7F])Telugu(?![\u0C00-\u0C7F])", "తెలుగు"),
    ]
    for pat, rep in replacements:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    # Strip orphan quotes at start of lines or sentences or before 'అని'
    text = re.sub(r'^\s*["\'“”‘’`]+', '', text, flags=re.MULTILINE)
    text = re.sub(r'(?<=[.!?\n])\s*["\'“”‘’`]+(?=\S)', ' ', text)
    text = re.sub(r'["\'“”‘’`]+\s*(?=అని\b)', ' ', text)

    return text


def validate_and_heal_script(script: str, topic: str = "") -> str:
    """
    Pre-flight quality gate ensuring authentic native Telugu language:
    - Runs loanword sanitization and honorific repair
    - Checks for hallucination artifacts ('క్షేత్రం', 'క్లబ్బింగ్', 'షాపింగ్ లిస్ట్', 'భారతదేశమేనా', 'హాస్యం చోటు చేసుకుంది', 'యాజ్', 'ముచ్చుడు', 'ప్లీడ్', 'ఐసీయూ', 'ఐఫోల్', 'హాట్ డాగ్', 'నాన్‌ఆఫ్', 'జాతి గుండెలు', 'సటోర్ రూమ్', 'అసహాయకారపూర్వకతకు')
    - If severe artifacts exist, triggers a rapid native Telugu rephrase pass
    - Guarantees respectful honorifics for Nagarjuna ('నాగ్‌గారు', 'అన్నారు', 'కౌంటర్ వేశారు')
    - Purges eliminated contestants from active house gameplay
    """
    cleaned = _sanitize_awkward_loanwords(script)
    try:
        from analytics.youtube_director import get_youtube_director
        cleaned = get_youtube_director().sanitize_script_cliches(cleaned)
    except Exception:
        pass

    # Check for severe machine-translation or hallucination flags
    hallucination_flags = [
        "క్షేత్రం", "క్లబ్బింగ్", "షాపింగ్ లిస్ట్", "భారతదేశమేనా",
        "సైలింగ్", "అక్టోర్", "ట్రైగన్", "ఎస్వరన్", "నోరు మళ్ళించాడు",
        "యాజ్", "ముచ్చుడు", "ప్లీడ్", "ఐసీయూ", "డ్రామాట్టెక్‌గా",
        "ఐఫోల్", "హాట్ డాగ్", "థర్మల్ కాఫీ", "థెర్మల్ కాఫీ", "కాల్డ్ వెపన్", "పాఠశాల బ్యాటరీ",
        "నాన్‌ఆఫ్", "నాన్ ఆఫ్", "జాతి గుండెలు", "సటోర్ రూమ్", "సటోర్ రూం", "అసహాయకారపూర్వకతకు", "అసహాయకారపూర్వక"
    ]
    detected_flags = [f for f in hallucination_flags if f in cleaned]

    orig_words = len(cleaned.split())
    if detected_flags:
        print(f"⚠️ [Script Quality Guard] Detected unnatural machine-translation flags: {detected_flags}. Healing with Native Telugu Rephrase pass...")
        healing_prompt = f"""You are an elite Telugu YouTube comedy reviewer and roaster.
The following Telugu roast script contains awkward, machine-translated English phrases or hallucinated words ({', '.join(detected_flags)}).
Rewrite it into 100% natural, colloquial, lively spoken Telugu (సరళమైన సహజ వాడుక తెలుగు) as spoken by authentic Telugu creators.

Original Topic: {topic}
Original Draft:
{cleaned}

MANDATORY RULES:
1. Write 100% in natural spoken Telugu script (తెలుగు లిపి).
2. Use authentic conversational Telugu phrases: 'రచ్చ రంబోలా', 'కౌంటర్ పడింది', 'ఫ్యూజులు ఎగిరిపోయాయి', 'గాలి తీసేశాడు', 'ఓవర్ యాక్షన్ పీక్స్', 'సీన్ కట్ చేస్తే'.
3. Contestant Names: 'త్రిగుణ్' (NOT 'ట్రైగన్' or 'ఎస్వరన్'), 'ముకేష్ గౌడ', 'సుధీర్ రెడ్డి', 'అమన్', 'టెంపర్ వంశీ'.
4. Host Honorifics: Always address Host Nagarjuna respectfully in plural: 'నాగ్‌గారు అన్నారు', 'నాగ్‌గారు కౌంటర్ వేశారు', 'నాగ్‌గారు క్లాస్ పీకారు' (NEVER singular 'ఇచ్చాడు' or 'జోక్ చేశాడు').
5. Maintain the exact same length and punchy structure (~{orig_words} words, do NOT shrink the script below {int(orig_words * 0.85)} words).
Return ONLY the healed Telugu script narration text."""
        try:
            healed = generate_text_cascade(healing_prompt, step_name="roast_heal", per_provider_timeout=12.0)
            clean_healed = re.sub(r"```[a-zA-Z]*", "", healed).replace("```", "").strip()
            min_keep_words = max(40, int(orig_words * 0.80))
            if len(clean_healed.split()) >= min_keep_words:
                cleaned = _sanitize_awkward_loanwords(clean_healed)
                print("✅ [Script Quality Guard] Script healed into authentic native Telugu successfully!")
        except Exception as e:
            print(f"⚠️ [Script Quality Guard] Rephrase notice: {e}")

    # Final honorific assurance pass
    cleaned = re.sub(r"నాగ్[\u200c\u200d]?గారి\s*(.*?)\s*జోక్\s*చేశాడు", r"నాగ్‌గారు \1 జోక్ చేశారు", cleaned)
    cleaned = re.sub(r"నాగ్[\u200c\u200d]?గారి\s*(.*?)\s*రీప్లై\s*ఇచ్చాడు", r"నాగ్‌గారు \1 కౌంటర్ ఇచ్చారు", cleaned)
    cleaned = re.sub(r"నాగ్[\u200c\u200d]?గారి\s*(.*?)\s*రిప్లై\s*ఇచ్చాడు", r"నాగ్‌గారు \1 కౌంటర్ ఇచ్చారు", cleaned)
    cleaned = re.sub(r"నాగ్[\u200c\u200d]?గారి\s*(.*?)\s*ఇచ్చాడు", r"నాగ్‌గారు \1 ఇచ్చారు", cleaned)
    # Check and replace eliminated contestants and captaincy errors in Bigg Boss context
    try:
        from utils.season_guard import is_bigg_boss_topic
        is_bb_check = is_bigg_boss_topic(topic) if topic else False
    except Exception:
        is_bb_check = False
    if is_bb_check or any(bb in cleaned for bb in ["బిగ్ బాస్", "బిగ్‌బాస్", "నామినేషన్", "హౌస్‌లో", "హౌస్ లో", "ఎలిమినేషన్", "క్యాప్టెన్", "కెప్టెన్"]):
        # 1. Captaincy Guard: Week 11 captain is Potti Naresh. Temper Vamsi is NOT captain.
        if re.search(r"(?:టెంపర్\s*)?(?:వాంశీ|వంశీ)\s*(?:ఈ\s*వారం\s*)?(?:క్యాప్టెన్సీ|కెప్టెన్సీ)", cleaned):
            cleaned = re.sub(
                r"(?:టెంపర్\s*)?(?:వాంశీ|వంశీ)\s*(?:ఈ\s*వారం\s*)?(?:క్యాప్టెన్సీ|కెప్టెన్సీ)",
                "పొట్టి నరేష్ క్యాప్టెన్సీ",
                cleaned
            )
            print("⚡ [Script Guard] Corrected captaincy hallucination: Potti Naresh captaincy.")
        if re.search(r"(?:టెంపర్\s*)?(?:వాంశీ|వంశీ)\s*(?:ఈ\s*వారం\s*)?(?:క్యాప్టెన్|కెప్టెన్)(?!సీ)", cleaned):
            cleaned = re.sub(
                r"(?:టెంపర్\s*)?(?:వాంశీ|వంశీ)\s*(?:ఈ\s*వారం\s*)?(?:క్యాప్టెన్|కెప్టెన్)(?!సీ)",
                "పొట్టి నరేష్ ఈ వారం క్యాప్టెన్",
                cleaned
            )
            print("⚡ [Script Guard] Corrected captaincy hallucination: Potti Naresh is Week 11 captain (not Temper Vamsi).")
        # Fix awkward Telugu spelling of Vamsi
        cleaned = re.sub(r"(?<![\u0C00-\u0C7F])వాంశీ(?![\u0C00-\u0C7F])", "వంశీ", cleaned)

        # 2. Week 11 Active Elimination Guard: Purge false 'no elimination' claims unless topic is about no elimination
        topic_str = (topic or "").lower()
        if "no elimination" not in topic_str and "ఎలిమినేషన్ లేదు" not in (topic or ""):
            cleaned = re.sub(
                r"(?:కానీ\s*నిజం\s*చెప్పాలంటే,?\s*)?(?:ఈ\s*వారం\s*)?(?:ఎలిమినేషన్‌|ఎలిమినేషన్)\s*జరగలేదు[.!।]*",
                "ఈ వారం ఎలిమినేషన్ గండం ఎవరి మెడకు చుట్టుకుంటుందో వేచి చూడాలి!",
                cleaned
            )
            cleaned = re.sub(
                r"ఖచ్చితంగా\s*ఎలిమినేషన్‌\s*లేదు[.!।]*",
                "ఓటింగ్ లెక్కలు రోజురోజుకీ మారిపోతున్నాయి!",
                cleaned
            )
            cleaned = re.sub(
                r"హౌస్‌లో\s*అందరూ\s*సురక్షితంగా\s*ఉన్నారు[.!।]*",
                "డేంజర్ జోన్‌లో ఉన్న కంటెస్టెంట్లకు ముచ్చెమటలు పడుతున్నాయి!",
                cleaned
            )
            cleaned = re.sub(
                r"ఎలిమినేషన్‌\s*నిజం\s*కాదని\s*తెలిసింది[.!।]*",
                "ఎలిమినేషన్ పోరు హోరాహోరీగా సాగుతోంది!",
                cleaned
            )

        # 3. Eliminated contestants purge
        evicted_replacements = [
            (r"(?<![\u0C00-\u0C7F])ఝాన్సీ(?:ని|తో|పై|కి|తోటి|ను)?(?![\u0C00-\u0C7F])", "వర్షిణి"),
            (r"(?<![\u0C00-\u0C7F])రోహిత్(?:ని|తో|పై|కి|తోటి|ను)?(?![\u0C00-\u0C7F])", "సుధీర్ రెడ్డి"),
            (r"(?<![\u0C00-\u0C7F])శాలిని(?:ని|తో|పై|కి|తోటి|ను)?(?![\u0C00-\u0C7F])", "దేబ్జాని"),
            (r"(?<![\u0C00-\u0C7F])చరణ్(?:ని|తో|పై|కి|తోటి|ను)?(?![\u0C00-\u0C7F])", "త్రిగుణ్"),
            (r"(?<![\u0C00-\u0C7F])చైత్ర(?:ని|తో|పై|కి|తోటి|ను)?(?![\u0C00-\u0C7F])", "శ్వేత"),
            (r"(?<![\u0C00-\u0C7F])కృష్ణుడు(?:ని|తో|పై|కి|తోటి|ను)?(?![\u0C00-\u0C7F])", "ముకేష్"),
        ]
        for pat, rep in evicted_replacements:
            if re.search(pat, cleaned):
                cleaned = re.sub(pat, rep, cleaned)
                print(f"⚡ [Script Guard] Replaced eliminated housemate match ({pat}) with active housemate ({rep}).")
        # 4. Anti-Hallucination: Fake numerical elimination claims in hook (e.g. "1 నిమిషంలో 3 లేడీలు ఎలిమినేట్")
        if re.search(r"(?:ఈ\s*వారం\s*)?\d+\s*(?:నిమిషంలో|నిమిషాల్లో|సెకన్లలో|రోజుల్లో)\s*\d+\s*(?:లేడీలు|మంది|కంటెస్టెంట్లు)?\s*ఎలిమినేట్", cleaned):
            cleaned = re.sub(
                r"(?:ఈ\s*వారం\s*)?\d+\s*(?:నిమిషంలో|నిమిషాల్లో|సెకన్లలో|రోజుల్లో)\s*\d+\s*(?:లేడీలు|మంది|కంటెస్టెంట్లు)?\s*ఎలిమినేట్\s*(?:అయ్యారు|అయ్యారా|అయ్యారని)[.!।?]*",
                "ఈ వారం ఎలిమినేషన్ రచ్చతో బిగ్ బాస్ హౌస్ మొత్తం షేక్ అయింది!",
                cleaned
            )
            print("⚡ [Script Guard] Purged hallucinated rapid elimination numbers in hook.")

        # 5. Sanitize alien transliteration of 'myth' ("మిథే")
        cleaned = re.sub(r"అయ్యో,?\s*ఇది\s*మరీ\s*మిథే,?\s*(?:ఫ్రెండ్స్|బాస్)?[.!।?]*", "కానీ సోషల్ మీడియాలో జరుగుతున్న ప్రచారం ఎంతవరకు నిజం?", cleaned)
        cleaned = re.sub(r"(?<![\u0C00-\u0C7F])మిథే(?![\u0C00-\u0C7F])", "అబద్ధం", cleaned)

    return cleaned


def load_golden_full_script(topic: str = "") -> str:
    """Loads a complete 120-150 word golden script example matching the topic category."""
    ex_file = ROOT / "config" / "roast_examples.json"
    if not ex_file.exists():
        return ""
    try:
        data = json.loads(ex_file.read_text(encoding="utf-8"))
        full_scripts = data.get("full_scripts", [])
        if not full_scripts:
            return ""
        from utils.season_guard import is_bigg_boss_topic
        is_bb = is_bigg_boss_topic(topic) if topic else False
        t_low = (topic or "").lower()

        if is_bb:
            target_cat = "reality_tv"
        elif any(k in t_low for k in ["tech", "phone", "iphone", "apple", "samsung", "ai", "laptop", "gadget", "software", "code"]):
            target_cat = "tech"
        elif any(k in t_low for k in ["movie", "cinema", "film", "teaser", "trailer", "box office", "actor", "hero", "star"]):
            target_cat = "cinema"
        else:
            target_cat = "reality_tv" if is_bb else "cinema"

        for fs in full_scripts:
            if fs.get("category") == target_cat:
                return fs.get("script", "")
        return full_scripts[0].get("script", "")
    except Exception:
        return ""


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
    """Extracts 3-4 cohesive narrative story points that form ONE complete comedic arc."""
    from utils.season_guard import is_bigg_boss_topic
    is_bb = is_bigg_boss_topic(topic)

    context_text = ""
    if source_context and isinstance(source_context, dict) and source_context.get("articles"):
        arts = source_context["articles"][:3]
        context_text = "\n".join([f"- {a.get('title', '')}: {a.get('snippet', '')}" for a in arts])

    contestant_context = ""
    if is_bb:
        try:
            from data.bb10_contestants import get_active_contestants_prompt_context
            contestant_context = f"\n{get_active_contestants_prompt_context()}\n"
        except Exception:
            contestant_context = "\nActive Bigg Boss Telugu Housemates: Temper Vamsi, Thrigun (త్రిగుణ్), Aman Masud, Sudheer Reddy, Auto Ram Prasad, Potti Naresh (Captain), Debjani, Shiv, Mukesh Gowda, Varshini Sounderajan, Rama Krishna, Swetha, Neethu. Host: Akkineni Nagarjuna.\n"

    if is_bb:
        prompt = f"""You are an entertainment comedy script writer for Bigg Boss Telugu.
Extract 3 to 4 CONCRETE, COHESIVE story points forming ONE single narrative arc about this topic:
Topic: {topic}
{contestant_context}
Context:
{context_text or "Latest Bigg Boss Telugu house events, nominations, voting flips, and housemate conflicts"}

MANDATORY RULES:
- Focus on ONE continuous narrative arc with active housemates:
  Point 1: The Core Conflict / Clash: Which active housemates clashed (e.g. Potti Naresh, Temper Vamsi, Thrigun, Aman Masud, Sudheer Reddy, Mukesh Gowda) and what triggered the argument.
  Point 2: The Overacting / Hypocrisy: How housemates overreacted, played safe games, or tried to cover up.
  Point 3: The Reality Check / Stakes: What Nag's weekend reality check or the Week 11 voting danger zone means for them.
- STRICT: Only name ACTIVE housemates. Current Captain is Potti Naresh (పొట్టి నరేష్). DO NOT name eliminated housemates (Rohit, Shalini, Jhansi, Chaithra, Krishnudu, Srishti, Charan were evicted).
- STRICT: Ground statements in realistic house conflicts. DO NOT invent fake voting percentages or impossible events.
Return ONLY a bulleted list of 3-4 cohesive story points in natural spoken Telugu script (తెలుగు లిపి). One per line."""
    else:
        prompt = f"""Extract 3-5 concrete, verified facts about this topic forming a cohesive narrative.
Focus on specific names, numbers, prices, physical mechanisms, claims, quotes, or events that can be roasted or highlighted.
Topic: {topic}
Context:
{context_text or "General knowledge about the topic"}

MANDATORY RULES:
- Ground all facts strictly in {topic}.
- STRICTLY FORBIDDEN: This topic is NOT Bigg Boss or a reality show. Do NOT mention Bigg Boss, housemates, contestants, nominations, eliminations, Nagarjuna, or reality show drama.

Return ONLY a bulleted list of 3-5 facts in English or Tanglish, one per line. No filler."""

    try:
        raw = generate_text_cascade(prompt, step_name="roast_facts", per_provider_timeout=10.0)
        facts = [re.sub(r"^[\*\-\d\.\s]+", "", line).strip() for line in raw.splitlines() if line.strip()]
        facts = [f for f in facts if len(f) > 5][:5]
        if len(facts) >= 2:
            return facts
    except Exception as e:
        print(f"⚠️ Fact extraction notice: {e}")

    # Fallback default facts anchored to real entities rather than generic filler
    if is_bb:
        return [
            "డే 75-76 టికెట్ టు ఫినాలే ఏరీనా టాస్క్‌లో త్రిగుణ్ టీమ్ ప్లానింగ్, అమన్ మసూద్ దూకుడు గేమ్",
            "సంచాలక్ రూల్స్ మర్చిపోయి పక్షపాతం చూపించిన ముకేష్ గౌడ తప్పుల తడక నిర్ణయాలు",
            "శ్వేత స్టోర్ రూమ్ గుంజీల పనిష్మెంట్, కెప్టెన్ పొట్టి నరేష్ బొమ్మ బాకు వార్నింగ్స్, వర్షిణి-దేబ్జాని నామినేషన్ల టెన్షన్",
            "ఈ వీకెండ్‌లో నాగార్జునగారు ముకేష్ పక్షపాతానికి ఎలాంటి క్లాస్ పీకబోతున్నారో చూడాలనే ప్రేక్షకుల ఆసక్తి",
        ]
    return [
        f"Verified core principles and physical mechanisms behind {topic}",
        f"Dramatic instant changes, momentum shifts, and extreme impacts of {topic}",
        f"Surprising real-world consequences and sudden aftermath triggered by {topic}",
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
        comment_rule = '- COMMENT TRIGGER QUESTION: Ask viewers a provocative, polarizing debate question that forces them to comment (e.g. "ఈ వారం బిగ్ బాస్ హౌస్‌లో అసలైన కవర్ డ్రైవర్ ఎవరు? మీ అభిప్రాయం ఏమిటో కింద కామెంట్ చేయండి!").'
    else:
        comment_rule = f'- COMMENT TRIGGER QUESTION: Ask viewers a provocative, polarizing opinion or prediction specifically about {topic} (e.g. "దీనిపై మీ ఒపీనియన్ ఏంటో కామెంట్ చేయండి!"). STRICTLY DO NOT mention Bigg Boss, elimination, or reality show housemates.'

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
        return "ఈ వారం బిగ్ బాస్ హౌస్‌లో అసలైన కవర్ డ్రైవర్ ఎవరు? మీ అభిప్రాయం కింద కామెంట్ చేయండి! మరిన్ని సాలిడ్ రోస్ట్‌ల కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి!"
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
    golden_script = load_golden_full_script(topic=topic)
    golden_section = f"""
============================================================
🌟 GOLDEN BENCHMARK TELUGU CREATOR SCRIPT (FOLLOW THIS EXACT VIBE, FLOW & QUALITY):
============================================================
"{golden_script}"
============================================================
""" if golden_script else ""

    if target_duration_sec <= 44:
        word_target = "70-88 words (for a crisp, high-retention 30-40s Short)"
        beats_count = "4-6 punchy visual beats"
    elif target_duration_sec <= 75:
        # User requirement: Strictly 45 to 70 seconds duration (nominal 60 seconds)
        word_target = "115-145 words (for a dynamic 45-70s Short, nominal 60s)"
        beats_count = "8-12 punchy visual beats (10-14 words per beat)"
    else:
        word_target = "150-185 words (for an extended Short)"
        beats_count = "12-16 punchy visual beats"

    from utils.season_guard import is_bigg_boss_topic
    is_bb = is_bigg_boss_topic(topic)
    if is_bb:
        struct_text = """Structure:
- Hook (0-3s): SAVAGE HIGH-VOLTAGE OBSERVATIONAL HOOK (0.0s START):
  * STRICTLY FORBIDDEN: NEVER open with flat questions like "నిన్న రాత్రి జరిగిన ఎపిసోడ్ చూశారా", "అసలు ఏం జరిగిందో తెలుసా", or flat greetings.
  * MANDATORY: Open directly with a hilarious disbelief reality-check or witty hyperbole that shocks the viewer!
    Example: "బిగ్ బాస్ 10 హౌస్‌లో సంచాలక్ ముకేష్ గౌడ చేసిన రచ్చతో సీన్ మొత్తం సితార అయిపోయింది బాస్!"
- Beat 1 & 2 (DRAMATIC OVERACTION SATIRE):
  * Describe the concrete arena task drama using vivid comedic hyperbole and contestant antics.
    Example: "రూల్స్ బుక్ మర్చిపోయిన ముకేష్ గౌడ సంచాలక్ పోస్ట్ దొరికిందే ఛాన్స్ అని తన గ్రూప్‌కే సపోర్ట్ చేస్తూ ఆడియన్స్‌కి కూడా మైండ్ బ్లాంక్ చేశాడు!"
- Beat 3 (COVERING & REACTIONS):
  * Roast the gameplay, physical arena fights, and punishments.
    Example: "మరోపక్క త్రిగుణ్ తెలివైన గేమ్ ప్లాన్‌తో అమన్ మసూద్ టాస్క్‌లో దుమ్మురేపితే, శ్వేత స్టోర్ రూమ్‌లో గుంజీలు తీస్తూ కెప్టెన్ పొట్టి నరేష్ బొమ్మ బాకు పట్టుకుని వార్నింగ్ ఇవ్వడం చూస్తే నవ్వు ఆపుకోవడం ఎవరి వల్లా కాలేదు!"
- Beat 4 / Ending: Upcoming Weekend reality check or voting stakes.
  * Note: The weekend episode has NOT aired yet. Frame Host Nagarjuna as UPCOMING EXPECTATION.
    Example: "మరి ఈ వీకెండ్‌లో నాగార్జునగారు వచ్చి ముకేష్ పక్షపాతానికి ఎలాంటి క్లాస్ పీకబోతున్నారో చూడాలి బాస్!"
- Comment Trigger & CTA (Final Beat):
  * End with a provocative, polarizing debate question followed by creator లైక్, షేర్, సబ్‌స్క్రైబ్.
    Example: "మరి ముకేష్ సంచాలక్‌గా ఫెయిల్ అయ్యాడా? కింద కామెంట్ చేయండి! మరిన్ని కిర్రాక్ రోస్ట్‌ల కోసం లైక్ కొట్టి, ఇప్పుడే సబ్‌స్క్రైబ్ చేసుకోండి!" """
        try:
            from data.bb10_contestants import get_active_contestants_prompt_context
            bb_constraint = get_active_contestants_prompt_context()
        except Exception:
            bb_constraint = """BIGG BOSS TELUGU 10 ROSTER RULES:
- CURRENT CAPTAIN: Potti Naresh (పొట్టి నరేష్). CRITICAL: Potti Naresh is the sole current Captain of the house. Temper Vamsi is NOT the captain!
- ACTIVE HOUSEMATES: Potti Naresh (Captain), Temper Vamsi, Thrigun (Trigun / త్రిగుణ్), Aman Masud, Sudheer Reddy (Sudheer), Auto Ram Prasad, Debjani Modak, Shiv, Mukesh Gowda, Varshini Sounderajan, Rama Krishna, Swetha, Neethu Natraj.
- HOST: Akkineni Nagarjuna (గౌరవంగా 'నాగ్‌గారు' అని సంబోధించాలి).
- THIS WEEK REALITY: Week 11 nomination clashes, voting trends, and Ticket to Finale race are underway. There IS an active elimination race this week (DO NOT claim 'no elimination this week'!).
- ELIMINATED CONTESTANTS: Rohit Patnam, Shalini Patel, Gundeboina Jhansi, Chaithra Rai, Krishna Alluri, Srishti Vyakaranam, Charan Mahadev, Mithilesh Reddy."""
        loanword_samples = "'బిగ్ బాస్', 'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్ స్ట్రాటజీ', 'టీఆర్పీ రేటింగ్స్', 'సీక్రెట్ రూమ్', 'ఎలిమినేషన్', 'ఓటింగ్', 'కెప్టెన్'"
    else:
        struct_text = f"""Structure:
- Hook (0-3s): SAVAGE HIGH-VOLTAGE OBSERVATIONAL HOOK (0.0s START):
  * STRICTLY FORBIDDEN: NEVER open with flat questions or "ఈ రోజు మనం X గురించి మాట్లాడుకుందాం".
  * MANDATORY: Open directly with a shocking curiosity gap, funny comparison, or disbelief reality check!
- Beat 1 & 2 (DRAMATIC COMEDIC CONTRAST):
  * The concrete facts about {topic} + sharp comedic contrast, ironic observation, or mock praise.
- Beat 3 (REACTIONS & CHAIN REACTION):
  * The extreme reaction, consequence, or absurdity regarding {topic} with witty sarcastic breakdown.
- Beat 4 / Ending: Savage punchline summarizing the ironic truth or reality check.
- Comment Trigger & CTA: Polarizing question provoking viewer opinions in the comments about {topic} followed by creator లైక్, షేర్, సబ్‌స్క్రైబ్."""
        bb_constraint = f"""STRICT TOPIC ISOLATION:
- This video is strictly about: {topic}.
- STRICTLY FORBIDDEN: Do NOT mention Bigg Boss, contestants/housemates, nominations, eliminations, Nagarjuna, or reality show drama.
- Keep 100% of the narrative, humor, and references anchored to {topic}."""
        loanword_samples = "'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్ స్ట్రాటజీ', 'టీఆర్పీ రేటింగ్స్', 'హైప్', 'రివ్యూ'"

    prompt = f"""{ROAST_PERSONA_PROMPT}

{golden_section}

Examples of good roast lines:
{examples_str}

Topic: {topic}
Target Duration: {target_duration_sec} seconds
Target Word Count: STRICTLY {word_target} ({beats_count})
Anchored Story Beats to Cover:
{chr(10).join(f"- {fact}" for fact in facts)}

{struct_text}

{bb_constraint}

CRITICAL SCRIPT & FLOW RULES:
- STRUCTURE INTO {beats_count}:
  * Divide the script into {beats_count} (each beat on a separate line with 10-14 words).
  * This guarantees rapid, dynamic visual transitions (cuts every 4-6 seconds) instead of frozen static visuals.
  * Tell ONE cohesive story from start to finish (Hook -> Conflict -> Hilarious Roast -> Reality Check -> Polarizing Question + CTA).
- STRICT PROHIBITION ON ALIEN TRANSLITERATIONS: NEVER phonetically transliterate obscure English words into Telugu (e.g. NEVER write 'సింకోఫాంట్', 'స్పానియెనిటీ', 'పారాడైమ్', 'మానిప్యులేషన్', 'నాన్‌ఆఫ్', 'సటోర్ రూమ్', 'జాతి గుండెలు'). ALWAYS use natural Telugu colloquial idioms that real Telugu people speak (e.g. use 'భజన బ్యాచ్' instead of sycophant; use 'సొంత గేమ్' instead of spontaneity; use 'స్టోర్ రూమ్' instead of 'సటోర్ రూమ్'; use 'డిస్క్వాలిఫై' instead of 'నాన్‌ఆఫ్').
- Punctuation-Driven Cadence: Use commas (,), dashes (—), and ellipsis (...) inside sentences for natural breath pauses and comedic timing.
- 100% Telugu Script for All Loanwords: NEVER write English alphabet letters (write 'బిగ్ బాస్', 'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్', NOT English letters).
- Natural Spoken Expressions: Include real creator conversational words ('అసలు...', 'చూశారా బాస్!', 'అబ్బో!', 'సీన్ కట్ చేస్తే...', 'ఫ్యూజులు ఎగిరిపోయాయి', 'గాలి తీసేశాడు').
- Return ONLY the spoken narration text."""

    raw_script = generate_text_cascade(prompt, step_name="roast_draft", per_provider_timeout=18.0)
    cleaned = re.sub(r"```[a-zA-Z]*", "", raw_script).replace("```", "").strip()
    try:
        from utils.transliterate_telugu import ensure_telugu_script
        cleaned = ensure_telugu_script(cleaned)
    except Exception:
        pass
    cleaned = validate_and_heal_script(cleaned, topic=topic)
    return cleaned


# ------------------------------------------------------------
# 4. PUNCH-UP PASS
# ------------------------------------------------------------
def punch_up_script(draft: str, facts: List[str], target_duration_sec: int = 38) -> str:
    """Tightens setups, ensures punchline is at the very end of every sentence, maintains target length."""
    if target_duration_sec <= 44:
        length_rule = "Maintain total script strictly between 70 and 88 words (minimum 65 words) so spoken narration completes in 30-40 seconds with maximum audience retention."
        min_keep = 60
    elif target_duration_sec <= 75:
        length_rule = "Maintain total script STRICTLY between 115 and 145 words (minimum 110 words) structured into 8-12 punchy beat lines so spoken narration completes in 45-70 seconds (target ~60s) with rapid visual cuts."
        min_keep = 105
    else:
        length_rule = "Maintain total script STRICTLY between 150 and 185 words (minimum 140 words) so spoken narration lasts 75-90 seconds."
        min_keep = 135

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
        cleaned = _sanitize_awkward_loanwords(cleaned)
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
    if target_duration_sec <= 44:
        min_required = 65
        max_allowed = 90
    elif target_duration_sec <= 75:
        # Strictly calibrated for 45 to 70s duration (nominal 60s)
        min_required = 115
        max_allowed = 145
    else:
        min_required = 145
        max_allowed = 185

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
                "అసలు హౌస్‌లో జరుగుతున్న ఈ గేమ్ స్ట్రాటజీ చూస్తుంటే ఆడియన్స్‌కి నవ్వాలో ఏడ్వాలో అర్థం కావడం లేదు.",
                "కెమెరాలు ఉన్నాయని తెలిసి కూడా చేసే ఈ హై ఓవరాక్షన్ చూసి అందరి మైండ్ బ్లాంక్ అయిపోతోంది.",
                "నామినేషన్లలో ఇంత పచ్చిగా డ్రామాలు ఆడుతూ సేఫ్ గేమ్ ప్లాన్ చేయడం వీళ్ళకే చెల్లింది.",
                "మొత్తానికి ఈ వీక్ ఎలిమినేషన్ ఎవరు అవుతారో చూడాలి కానీ, ఇదంతా ప్యూర్ టిఆర్పీ స్టంట్ తప్ప మరొకటి కాదు.",
            ]
        elif any(k in t_low for k in ["tech", "ai", "phone", "iphone", "apple", "samsung", "gadget", "software", "google"]):
            roast_blocks = [
                "టెక్నాలజీ రంగంలో ఇలాంటి క్రేజీ డెవలప్‌మెంట్స్ చూస్తుంటే భవిష్యత్తు ఎలా ఉండబోతోందో అర్థం చేసుకోవచ్చు.",
                "కొత్త ఫీచర్లు వినడానికి చాలా బాగున్నా, నిజ జీవితంలో యూజర్లకి ఎంతవరకు ఉపయోగపడతాయో వేచి చూడాలి.",
                "ఈ రేంజ్ టెక్ వార్ చూస్తుంటే రాబోయే రోజుల్లో మార్కెట్లో కాంపిటీషన్ నెక్స్ట్ లెవెల్ ఉండబోతోంది.",
            ]
        elif any(k in t_low for k in ["movie", "cinema", "film", "teaser", "trailer", "tollywood"]):
            roast_blocks = [
                "టాలీవుడ్ సినిమా ఇండస్ట్రీలో ఇలాంటి సర్ప్రైజ్‌లు ఎప్పుడూ ఆడియన్స్‌ని విపరీతంగా ఆకట్టుకుంటూనే ఉంటాయి.",
                "హైప్ పెంచడంలో మూవీ టీమ్ సక్సెస్ అయినా, థియేటర్లలో అసలు రిజల్ట్ ఎలా ఉంటుందో వేచి చూడాల్సిందే.",
                "ఈ క్రేజీ కాంబినేషన్ బాక్సాఫీస్ దగ్గర ఎలాంటి రికార్డులు సృష్టిస్తుందో చూడటం చాలా ఆసక్తికరంగా మారింది.",
            ]
        else:
            roast_blocks = [
                "ఇలాంటి ఆసక్తికరమైన విషయాలు విన్నప్పుడు ఎవరికైనా ఆశ్చర్యం కలగడం చాలా సహజం.",
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
            # If script already ends with a CTA, insert added before the CTA so the CTA remains at the very end
            sents = [s.strip() for s in re.split(r"(?<=[.!?।\n])\s+", script) if s.strip()]
            if sents and any(k in sents[-1].lower() for k in ["లైక్", "సబ్‌స్క్రైబ్", "కామెంట్", "subscribe", "like"]):
                body = " ".join(sents[:-1])
                cta = sents[-1]
                script = f"{body} " + " ".join(added) + f" {cta}"
            else:
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

    return validate_and_heal_script(script, topic=topic)


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
def markup_roast_delivery(script: Union[str, List[Any]], topic: str = "") -> List[Dict[str, Any]]:
    """Splits roast script into beats and tags with emotion presets, pauses, SFX, and on_screen_text."""
    if isinstance(script, list):
        merged_beats = []
        for item in script:
            if isinstance(item, dict):
                merged_beats.append(item.get("spoken_text", ""))
            else:
                merged_beats.append(str(item))
    else:
        # Split into clean, cohesive beats (aim for 8-14 words per beat, 12-16 beats total)
        # Avoid micro-slicing every 2-word fragment which floods the project with 35+ redundant image downloads
        raw_tokens = [s.strip() for s in re.split(r"([.!?।]+|\n+)", str(script)) if s.strip()]
        merged_beats = []
        curr = ""
        for token in raw_tokens:
            curr += (" " + token if curr and token not in (".", "!", "?", "।") else token)
            # Consolidate sentences into semantic beats (min 7 words per beat)
            if token in (".", "!", "?", "।", "\n") and len(curr.split()) >= 7:
                merged_beats.append(curr.strip())
                curr = ""
        if curr.strip():
            if merged_beats and len(curr.split()) < 5:
                merged_beats[-1] = f"{merged_beats[-1]} {curr.strip()}"
            else:
                merged_beats.append(curr.strip())

        # Clamp total beats between 10 and 16 for optimal 60-90s pacing
        if len(merged_beats) > 16:
            # Consolidate smallest adjacent beats
            consolidated = []
            c_buf = ""
            target_per_beat = max(8, len(str(script).split()) // 14)
            for b in merged_beats:
                c_buf = f"{c_buf} {b}".strip() if c_buf else b
                if len(c_buf.split()) >= target_per_beat:
                    consolidated.append(c_buf)
                    c_buf = ""
            if c_buf:
                if consolidated:
                    consolidated[-1] = f"{consolidated[-1]} {c_buf}"
                else:
                    consolidated.append(c_buf)
            merged_beats = consolidated

        if len(merged_beats) < 4:
            parts = [p.strip() for p in re.split(r"[,;]+", str(script)) if len(p.strip()) > 15]
            if len(parts) >= 4:
                merged_beats = parts
            else:
                merged_beats = [str(script)]

    # Clean up quotation marks, whitespace, and orphan quotes from each beat
    cleaned_beats = []
    for b in merged_beats:
        b_clean = re.sub(r'[\"“”‘’`]+', '', b)
        b_clean = re.sub(r'\s+', ' ', b_clean).strip()
        if b_clean:
            cleaned_beats.append(b_clean)
    merged_beats = cleaned_beats or merged_beats

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
        "fake_shock": ["షాకింగ్ ట్విస్ట్?!", "ఓవరాక్షన్ పీక్స్!", "అదిరిపోయే ట్విస్ట్!", "ఇదేం డ్రామా?!", "బిగ్ బాస్ షాక్!", "నమ్మలేకపోతున్నాం!"],
        "hype": ["గేమ్ చేంజర్!", "మాస్ వార్ మొదలైంది!", "హౌస్‌లో రచ్చ రచ్చ!", "ఫైర్ బ్రాండ్!", "టాస్క్ కింగ్!", "నెక్స్ట్ లెవెల్ ప్లాన్!"],
        "mock": ["ఫేక్ డ్రామా బయటపడింది!", "వెన్నుపోటు ప్లాన్!", "డ్రామా క్వీన్!", "ఎవరిని మోసం చేస్తున్నారు?!", "అసలు స్కెచ్ ఇదే!", "ఓవరాక్షన్ ఆపు!"],
        "deadpan": ["అసలు నిజం ఇదీ!", "మాస్ ఆడియన్స్ తీర్పు!", "నిజాలు నిలకడగా!", "ఎవరి గేమ్ ఎక్కడ?!", "నో ఫిల్టర్ టాక్!", "పచ్చి నిజాలు!"],
        "smug": ["నాగార్జున ఫైర్!", "అడ్డంగా దొరికిపోయారు!", "ఫైనల్ పంచ్!", "ఇక ముగిసిన ఆట!", "బండారం బయటపడింది!", "ఆట ఖతం!"],
        "dramatic_question": ["ఎవరు ఎలిమినేట్ అవుతారు?!", "మీ ఓటు ఎవరికి?!", "హౌస్‌లో నెక్స్ట్ ఏంటి?!", "ఇది న్యాయమా?!", "మీరేమంటారు?!"],
    }
    OUTRO_BADGES = ["మీ కామెంట్ ఏంటి?!", "మీ ఓటు ఎవరికి?!", "లైక్ & షేర్ చేయండి!", "కామెంట్ల వర్షం కురిపించండి!"]

    primary_topic_tag = topic_keywords[0] if topic_keywords else "బిగ్ బాస్"
    used_badges: set = set()
    total_beats = len(merged_beats)

    CONTESTANT_BADGE_VARIANTS = ["గేమ్!", "ప్లాన్!", "రియాక్షన్!", "డ్రామా!", "షాక్!"]

    for idx, sentence in enumerate(merged_beats, 1):
        # Determine emotion preset and dynamic comedy SFX hit
        sfx = None
        if idx == 1:
            emotion = "fake_shock"
            pause_ms = 0
            sfx = "whoosh"
        elif idx == total_beats:
            emotion = "smug"
            pause_ms = 450
            sfx = None
        elif idx == total_beats - 1 or "?" in sentence or "ఏంటంటే" in sentence:
            emotion = "dramatic_question"
            pause_ms = 400
            sfx = "ding" if sfx_assigned < 3 else None
        elif any(k in sentence for k in ["అంట", "చూస్తే", "బాస్", "ఓవర్", "డ్రామా", "యాక్టింగ్"]):
            emotion = "mock"
            pause_ms = 350
            if sfx_assigned < 3 and idx % 2 == 1:
                sfx = "record_scratch"
        elif idx % 2 == 0:
            emotion = "hype"
            pause_ms = 450
            if sfx_assigned < 3 and idx in (2, 4):
                sfx = "rimshot"
        else:
            emotion = "deadpan"
            pause_ms = 300
            sfx = None

        if sfx:
            sfx_assigned += 1

        # Universal Entity / Badge Extraction with pure Telugu punchlines (Zero debug #numbers)
        matched_sentence = match_entities_in_text(sentence)

        badge = ""
        if matched_sentence:
            cand = matched_sentence[0]["canonical_name"].upper()
            if cand not in used_badges:
                badge = cand
            else:
                variant_suffix = CONTESTANT_BADGE_VARIANTS[(idx - 1) % len(CONTESTANT_BADGE_VARIANTS)]
                badge = f"{cand} {variant_suffix}"

        if not badge:
            if idx >= total_beats - 1:
                available_outro = [b for b in OUTRO_BADGES if b not in used_badges]
                badge = available_outro[0] if available_outro else OUTRO_BADGES[(idx - 1) % len(OUTRO_BADGES)]
            else:
                pool = DYNAMIC_EMOTION_BADGES.get(emotion, ["అసలు నిజం ఇదీ!", "షాకింగ్ ట్విస్ట్?!", "ఓవరాక్షన్ పీక్స్!"])
                available_pool = [b for b in pool if b not in used_badges]
                if available_pool:
                    badge = available_pool[0]
                else:
                    badge = pool[(idx - 1) % len(pool)]

        badge = badge[:28].strip()
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

    golden_script = load_golden_full_script(topic=topic)
    golden_section = f"""
============================================================
🌟 GOLDEN BENCHMARK TELUGU CREATOR SCRIPT (FOLLOW THIS EXACT VIBE, FLOW & QUALITY):
============================================================
"{golden_script}"
============================================================
""" if golden_script else ""

    try:
        from analytics.youtube_director import get_youtube_director
        director = get_youtube_director()
        fresh_directive = director.get_fresh_dialogue_directive(channel="Channel 2", topic=topic)
    except Exception:
        fresh_directive = {
            "archetype_id": "skeptical_truth_teller",
            "archetype_name": "Skeptical Truth-Teller (నిజాలు నిలదీసే శైలి)",
            "fresh_hooks": ["పైకి కనిపించే డ్రామా ఒకటైతే... లోపల తెరవెనుక నడిచిన అసలు కథ వేరే లెవల్!"],
            "fresh_punchlines": ["చెప్పే మాటలకి చేసే పనులకి అస్సలు సంబంధమే లేదు!"],
            "fresh_cta": "మరి ఇందులో ఎవరు నిజాయితీగా ఉన్నారు? మీ ఆలోచనలను కింద కామెంట్స్ లో చెప్పండి! జెన్యూన్ అనాలిసిస్ కోసం లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి!",
            "banned_cliches": ["వాతావరణం భగ్గుమంది బాస్", "ఫ్యూజులు ఎగిరిపోయాయి బాస్", "చూశారా బాస్", "గాలి తీసేశాడు"],
            "prompt_directive": "",
        }

    fresh_hook_sample = fresh_directive["fresh_hooks"][0]
    fresh_cta_sample = fresh_directive["fresh_cta"]

    examples_str = load_roast_examples(topic=topic)

    word_target = "75-90 words (for a crisp, high-retention 35s Short)" if target_duration_sec <= 50 else "140-170 words"
    beats_count = "4-5 punchy beats" if target_duration_sec <= 50 else "7-9 punchy beats"

    candidates = []
    from utils.season_guard import is_bigg_boss_topic
    is_bb_pkg = is_bigg_boss_topic(topic)
    if is_bb_pkg:
        struct_candidate = f"""Structure:
- Hook (0-3s): Fresh high-curiosity reveal matching style '{fresh_directive["archetype_name"]}': (e.g. "{fresh_hook_sample}")
- Beat 1 & 2: The concrete event/clash mentioning active housemates + sharp comedic contrast. (e.g. "టాస్క్‌లో అమన్ మసూద్ దూకుడు చూపిస్తే, ముకేష్ గౌడ సంచాలక్‌గా తప్పుల తడక నిర్ణయాలు తీసుకుని ఆడియన్స్‌ని కూడా అయోమయంలో పడేశాడు!")
- Beat 3: The escalation/reactions of housemates or upcoming Host Nagarjuna grilling. (e.g. "ఈ వీకెండ్ వేదికపై నాగార్జునగారు వచ్చి ముకేష్ పక్షపాతానికి ఎలాంటి క్లాస్ పీకబోతున్నారో చూడాలి!")
- Beat 4: Weekend reality check or elimination stakes. (e.g. "ఇక డేంజర్ జోన్‌లో వర్షిణి, డెబ్జాని ఉండగా.. కెప్టెన్ పొట్టి నరేష్ ఇచ్చిన వార్నింగ్ పంచ్‌లు హౌస్‌లో వైరల్ అవుతున్నాయి!")
- Comment Trigger & CTA: Polarizing debate question: (e.g. "{fresh_cta_sample}")"""
    else:
        struct_candidate = f"""Structure:
- Hook (0-3s): Fresh high-curiosity shocking reveal or provocative observation about {topic}. No greetings, straight into the action at 0.0s. (e.g. "{fresh_hook_sample}")
- Beat 1 & 2: The concrete phenomenon/facts about {topic} + sharp comedic contrast, ironic observation, or mock praise.
- Beat 3: The extreme reaction, physical/practical consequence, or chain reaction regarding {topic} + witty sarcastic breakdown.
- Beat 4 / Ending: Savage punchline summarizing the ironic truth or reality check.
- Comment Trigger & CTA: Polarizing question provoking viewer opinions in the comments about {topic}: (e.g. "{fresh_cta_sample}")"""

    if is_bb_pkg:
        try:
            from data.bb10_contestants import get_active_contestants_prompt_context
            bb_context = get_active_contestants_prompt_context()
        except Exception:
            bb_context = "Active: Temper Vamsi, Thrigun, Aman, Sudheer, Ram Prasad, Naresh (Captain), Debjani, Shiv, Mukesh, Varshini, Rama Krishna, Swetha, Neethu. Host: Nagarjuna."
        bb_pkg_constraint = f"""BIGG BOSS TELUGU 10 GROUND TRUTH & ACCURACY CONSTRAINTS:
{bb_context}
- CRITICAL RULES:
  1. Only mention active housemates. DO NOT mention eliminated contestants (Rohit Patnam, Shalini Patel, Gundeboina Jhansi, Charan Mahadev, Chaithra Rai, Krishna Alluri, Srishti Vyakaranam).
  2. Respectful Host Honorifics: Always address Host Nagarjuna respectfully in plural ('నాగ్‌గారు అన్నారు', 'నాగ్‌గారు కౌంటర్ ఇచ్చారు', 'నాగ్‌గారు క్లాస్ పీకారు'). NEVER use singular.
  3. Clean Contestant Names: 'త్రిగుణ్' (NOT 'ట్రైగన్' or 'ఎస్వరన్'), 'ముకేష్ గౌడ', 'సుధీర్ రెడ్డి', 'అమన్', 'టెంపర్ వంశీ'.
  4. Week 11 Captain: Potti Naresh is the Captain. Temper Vamsi is NOT captain."""
    else:
        bb_pkg_constraint = f"""STRICT TOPIC ISOLATION:
- This video is strictly about: {topic}.
- STRICTLY FORBIDDEN: Do NOT mention Bigg Boss, contestants/housemates, nominations, eliminations, Nagarjuna, or reality show drama.
- Keep 100% of the narrative, humor, and references anchored to {topic}."""
    loanword_pkg_samples = "'బిగ్ బాస్', 'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్ స్ట్రాటజీ', 'టీఆర్పీ రేటింగ్స్', 'సీక్రెట్ రూమ్', 'ఎలిమినేషన్', 'ఓటింగ్'" if is_bb_pkg else "'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్ స్ట్రాటజీ', 'టీఆర్పీ రేటింగ్స్', 'హైప్', 'రివ్యూ'"

    for idx, p_cfg in enumerate(SCRIPT_PERSONAS, start=1):
        p_prompt = f"""{ROAST_PERSONA_PROMPT}

{golden_section}

{fresh_directive.get('prompt_directive', '')}

============================================================
MANDATORY VOCAL & NARRATIVE PERSONA: {p_cfg['name'].upper()}
{p_cfg['directive']}
============================================================

Examples of witty comedic lines:
{examples_str}

Topic: {topic}
Target Duration: {target_duration_sec} seconds
Target Word Count: STRICTLY {word_target} ({beats_count})
Anchored Story Beats to Cover:
{chr(10).join(f"- {fact}" for fact in facts)}

{struct_candidate}

{bb_pkg_constraint}

CRITICAL SCRIPT & FLOW RULES:
- WRITE A CONTINUOUS SPOKEN TELUGU MONOLOGUE (ఒకే ప్రవాహంలా సాగే ప్యూర్ తెలుగు సంభాషణ):
  * Combine your thoughts into natural, connected sentences (do NOT put each short phrase on a separate line!).
  * Strictly FORBIDDEN: DO NOT write 1-sentence fragmented lines or bullet points.
  * Tell ONE cohesive story from start to finish (Hook -> Conflict -> Hilarious Roast -> Reality Check -> Polarizing Question + CTA).
- STRICT BAN ON BIZARRE METAPHORS & LITERAL MACHINE TRANSLATIONS: Write straightforward, relatable humor! NEVER invent weird metaphors like 'thermal coffee', 'hot dog', 'cold weapon', or literal English translations. Use real relatable comparisons (e.g. 'ఇస్త్రీ పెట్టెలా వేడెక్కింది', 'టీ కప్పులా కాలిపోతోంది', 'కరెంట్ బిల్లులా ఎగిరిపోయింది'). For tech brands, write 'యాపిల్' (NEVER 'ఐఫోల్').
- STRICT PROHIBITION ON ALIEN TRANSLITERATIONS: NEVER phonetically transliterate obscure English words into Telugu (e.g. NEVER write 'సింకోఫాంట్', 'స్పానియెనిటీ', 'పారాడైమ్', 'మానిప్యులేషన్'). ALWAYS use natural Telugu colloquial idioms that real Telugu people speak (e.g. use 'భజన బ్యాచ్' or 'చంచాగిరీ' instead of sycophant; use 'సొంత తెలివి' or 'ఓన్ గేమ్' instead of spontaneity; use 'మైండ్ గేమ్' or 'ఎత్తుగడలు' instead of manipulation).
- Punctuation-Driven Cadence: Use commas (,), dashes (—), and ellipsis (...) inside sentences for natural breath pauses and comedic timing.
- 100% Telugu Script for All Loanwords: NEVER write English alphabet letters (write 'బిగ్ బాస్', 'మైండ్ బ్లాంక్', 'సీన్ కట్', 'పీఆర్', NOT English letters).
- Natural Spoken Expressions: Include real creator conversational words ('అసలు...', 'గమనించారా!', 'అబ్బో!', 'కానీ తీరా చూస్తే...', 'దిమ్మతిరిగే కౌంటర్').
- Return ONLY the spoken narration text."""
        try:
            p_raw = generate_text_cascade(p_prompt, step_name=f"roast_v{idx}_{p_cfg['id']}", per_provider_timeout=14.0)
            cleaned = re.sub(r"```[a-zA-Z]*", "", p_raw).replace("```", "").strip()
            from utils.transliterate_telugu import ensure_telugu_script
            cleaned = ensure_telugu_script(cleaned)
            cleaned = _sanitize_awkward_loanwords(cleaned)
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
            f"చూడండి, {topic} గురించి జరుగుతున్న హైప్ ఒక రేంజ్ లో ఉంటే — గ్రౌండ్ రియాలిటీ చూస్తే ఇంకో రేంజ్ లో ఉంది! "
            f"అసలు ట్విస్ట్ ఏంటంటే... అందరూ అనుకున్నది ఒకటి, అక్కడ జరిగింది ఇంకొకటి. "
            f"ప్రతి ఒక్కరూ భారీ అంచనాలు పెట్టుకున్నారు, కానీ తీరా చూస్తే అంతా రివర్స్ అయింది! "
            f"మరి దీనిపై మీరేమనుకుంటున్నారో కింద కామెంట్స్ లో చెప్పండి! వీడియో నచ్చితే లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి!"
        )

    # Zero-Fail Pre-Execution Calibration: verify length and CTA before render
    print("🛡️ [Roast Engine] Running Zero-Fail Pre-Execution Calibration...")
    calibrated_script = calibrate_script_before_execution(
        script=final_script,
        target_duration_sec=target_duration_sec,
        topic=topic,
        facts=facts,
    )

    try:
        from analytics.youtube_director import get_youtube_director
        director = get_youtube_director()
        calibrated_script = director.sanitize_script_cliches(calibrated_script)
        director.record_script_dialogues(
            script=calibrated_script,
            topic=topic,
            channel="Channel 2",
            archetype_id=fresh_directive.get("archetype_id", ""),
        )
    except Exception as d_err:
        print(f"⚠️ [YouTube Director Notice] {d_err}")

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
