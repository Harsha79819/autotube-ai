"""
semantic_broll_mapper.py

Fixes: irrelevant B-roll (kiwi fruit for "Siri/Alexa", press conference
for "dentist appointment"), and the same stock clip repeating across
videos.

Pipeline:
  1. Split script into ~4-second narration chunks (word-count based on
     average Telugu speech rate).
  2. For each chunk, ask an LLM (Gemini, already in your stack) for 2-3
     precise ENGLISH search queries -- stock libraries index tags in
     English, so English queries return far better hits than Telugu text.
  3. Apply a negative-keyword filter per topic category so off-topic
     categories (food, nature, random people) never get pulled in for a
     tech video.
  4. Track used video/photo IDs (per Pexels/Pixabay) so the same clip
     isn't reused across recent videos.

Usage in image_agent.py:
    chunks = chunk_script_by_duration(script_text, seconds_per_chunk=4.0)
    for chunk in chunks:
        queries = generate_search_queries(chunk, topic_category="tech", gemini_call_fn=...)
        asset = fetch_fresh_stock_asset(queries, topic_category="tech", pexels_search_fn=..., pixabay_search_fn=...)
"""

import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 1. Script chunking (approx 4-second narration segments)
# ---------------------------------------------------------------------------
AVG_WORDS_PER_SECOND_TELUGU = 2.3  # tune against your own measured narration pace

def chunk_script_by_duration(script_text: str, seconds_per_chunk: float = 4.0) -> list[str]:
    """Split script text into chunks that take roughly `seconds_per_chunk`
    seconds to narrate, based on average Telugu speaking rate."""
    words = script_text.split()
    words_per_chunk = max(1, int(AVG_WORDS_PER_SECOND_TELUGU * seconds_per_chunk))

    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunk = " ".join(words[i:i + words_per_chunk])
        if chunk.strip():
            chunks.append(chunk.strip())
    return chunks


# ---------------------------------------------------------------------------
# 2. LLM-driven query generation (uses your existing Gemini call)
# ---------------------------------------------------------------------------
QUERY_GENERATION_PROMPT = """
You are a stock-footage search assistant for a Telugu tech review video.
Given a script chunk (which may mix Telugu and English), output 2-3 precise
ENGLISH search queries that would find visually accurate, on-topic stock
footage/photos for this exact chunk.

RULES:
- Queries must be concrete and filmable (subject + action/setting), never
  abstract single words.
- If the chunk mentions a specific product/brand, describe it generically
  (e.g. "Siri Alexa" -> "voice assistant smart speaker glowing light",
  NOT the brand name itself, since stock libraries won't have exact brand
  footage).
- Never include unrelated categories (food, nature, wildlife, random
  people) unless the chunk is literally about that category.
- Output ONLY a JSON array of strings, nothing else.

Script chunk: "{chunk}"
Topic category: "{topic_category}"
"""

def generate_search_queries(chunk: str, topic_category: str = "tech", gemini_call_fn=None) -> list[str]:
    """gemini_call_fn: your existing wrapper around the Gemini API call
    (already used elsewhere in script_agent.py) -- pass it in so this
    module has no direct dependency on your provider router."""
    if gemini_call_fn is None:
        try:
            from providers.llm import generate_text_cascade
            gemini_call_fn = generate_text_cascade
        except Exception:
            try:
                from google import genai
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    client = genai.Client(api_key=api_key)
                    def _default_call(p):
                        resp = client.models.generate_content(
                            model="gemini-3.6-flash",
                            contents=p,
                        )
                        return resp.text
                    gemini_call_fn = _default_call
            except Exception:
                pass

    if gemini_call_fn:
        prompt = QUERY_GENERATION_PROMPT.format(chunk=chunk, topic_category=topic_category)
        try:
            raw_response = gemini_call_fn(prompt)
            cleaned = raw_response.strip().strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
            queries = json.loads(cleaned)
            if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                return queries[:3]
        except Exception:
            pass

    # Fallback: never return empty -- degrade to a generic category query
    # rather than letting the pipeline fetch nothing for this chunk.
    return [f"{topic_category} technology close up"]


# ---------------------------------------------------------------------------
# 3. Negative-keyword filtering per topic category
# ---------------------------------------------------------------------------
NEGATIVE_KEYWORDS_BY_CATEGORY = {
    "tech": [
        "fruit", "kiwi", "vegetable", "food", "cooking", "kitchen",
        "wildlife", "animal", "forest", "nature landscape",
        "press conference", "politician", "government meeting",
        "wedding", "party balloon",
    ],
    "news": [
        "fruit", "food", "cooking", "wildlife", "cartoon", "clipart",
    ],
    "lifestyle": [
        "government meeting", "press conference", "industrial machinery",
    ],
}

def is_result_allowed(asset_tags: list[str], topic_category: str = "tech") -> bool:
    """Reject a candidate asset if any of its tags/description words match
    a negative keyword for this topic category."""
    cat_key = "tech"
    if topic_category:
        for k in NEGATIVE_KEYWORDS_BY_CATEGORY:
            if k in str(topic_category).lower():
                cat_key = k
                break
    negatives = NEGATIVE_KEYWORDS_BY_CATEGORY.get(cat_key, NEGATIVE_KEYWORDS_BY_CATEGORY["tech"])
    tags_lower = " ".join(str(t) for t in asset_tags).lower()
    return not any(neg in tags_lower for neg in negatives)


# ---------------------------------------------------------------------------
# 4. Used-asset tracking (prevents repeats across videos)
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
USED_ASSETS_FILE = os.path.join(ROOT_DIR, "assets", "used_asset_history.json")
HISTORY_RETENTION_DAYS = 30

def _load_used_assets() -> dict:
    if not os.path.exists(USED_ASSETS_FILE):
        return {}
    try:
        with open(USED_ASSETS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_used_assets(data: dict):
    try:
        os.makedirs(os.path.dirname(USED_ASSETS_FILE), exist_ok=True)
        with open(USED_ASSETS_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Warning: could not save used assets history: {e}")


def _prune_old_entries(data: dict) -> dict:
    cutoff = time.time() - (HISTORY_RETENTION_DAYS * 86400)
    return {asset_id: ts for asset_id, ts in data.items() if ts >= cutoff}


def mark_asset_used(asset_id: str):
    data = _prune_old_entries(_load_used_assets())
    data[str(asset_id)] = time.time()
    _save_used_assets(data)


def is_asset_fresh(asset_id: str) -> bool:
    """True if this asset has NOT been used in the retention window."""
    data = _prune_old_entries(_load_used_assets())
    return str(asset_id) not in data


# ---------------------------------------------------------------------------
# 5. Full fetch pipeline tying it together
# ---------------------------------------------------------------------------
def fetch_fresh_stock_asset(
    queries,
    topic_category="tech",
    pexels_search_fn=None,
    pixabay_search_fn=None,
    relevance_scorer_fn=None,
    relevance_threshold=0.05,
):
    """
    Try each query in order, checking negative keywords + freshness + SigLIP 2 relevance gate.
    If no candidate clears the threshold across queries, returns None so caller falls through to FLUX.
    """
    if relevance_scorer_fn is None:
        try:
            from agents.image_agent import score_visual_relevance
            relevance_scorer_fn = score_visual_relevance
        except Exception:
            relevance_scorer_fn = None

    for query in queries:
        if pexels_search_fn:
            candidates = pexels_search_fn(query, per_page=8) if callable(pexels_search_fn) else []
            for candidate in candidates:
                asset_id = f"pexels_{candidate.get('id', candidate.get('title', ''))}"
                tags = candidate.get("tags") or candidate.get("title", "").split()
                if not is_result_allowed(tags, topic_category) or not is_asset_fresh(asset_id):
                    continue

                # SigLIP 2 Relevance Gate
                local_img = candidate.get("local_path") or candidate.get("preview_path")
                if local_img and os.path.exists(local_img) and relevance_scorer_fn:
                    score = relevance_scorer_fn(local_img, query)
                    if score < relevance_threshold:
                        print(f"❌ Candidate rejected by SigLIP 2 gate ({score:.4f} < {relevance_threshold}): {candidate.get('title', '')[:30]}")
                        continue
                    print(f"✅ Candidate accepted by SigLIP 2 gate ({score:.4f} >= {relevance_threshold}): {candidate.get('title', '')[:30]}")

                mark_asset_used(asset_id)
                return candidate

        if pixabay_search_fn:
            candidates = pixabay_search_fn(query, per_page=8) if callable(pixabay_search_fn) else []
            for candidate in candidates:
                asset_id = f"pixabay_{candidate.get('id', candidate.get('title', ''))}"
                tags = candidate.get("tags") or candidate.get("title", "").split()
                if not is_result_allowed(tags, topic_category) or not is_asset_fresh(asset_id):
                    continue

                # SigLIP 2 Relevance Gate
                local_img = candidate.get("local_path") or candidate.get("preview_path")
                if local_img and os.path.exists(local_img) and relevance_scorer_fn:
                    score = relevance_scorer_fn(local_img, query)
                    if score < relevance_threshold:
                        print(f"❌ Candidate rejected by SigLIP 2 gate ({score:.4f} < {relevance_threshold}): {candidate.get('title', '')[:30]}")
                        continue
                    print(f"✅ Candidate accepted by SigLIP 2 gate ({score:.4f} >= {relevance_threshold}): {candidate.get('title', '')[:30]}")

                mark_asset_used(asset_id)
                return candidate

    return None  # caller should trigger the generative (FLUX/Pollinations) fallback


if __name__ == "__main__":
    script = ("Siri మరియు Alexa లాంటి voice assistants ఇప్పుడు మన రోజువారీ జీవితంలో భాగం అయ్యాయి. "
              "ఈ AI systems ఎలా పని చేస్తాయో చూద్దాం.")
    chunks = chunk_script_by_duration(script, seconds_per_chunk=4.0)
    for i, c in enumerate(chunks):
        print(f"Chunk {i+1}: {c}")

    print("\nNegative filter test:")
    print("Kiwi fruit tags allowed for 'tech'?", is_result_allowed(["kiwi", "fruit", "water splash"], "tech"))
    print("Smart speaker tags allowed for 'tech'?", is_result_allowed(["smart speaker", "voice assistant", "glowing light"], "tech"))
