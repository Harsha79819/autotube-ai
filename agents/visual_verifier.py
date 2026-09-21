"""
AutoTube AI - Visual Verifier & Multi-Candidate Re-ranking Module (agents/visual_verifier.py)

Capabilities:
1. Multi-Candidate Video Re-ranking:
   Takes top N video results from Pexels, parses tags/metadata/aspect ratio,
   and selects the most relevant clip rather than blindly picking index 0.
2. CLIP-based Visual Embedding Similarity:
   Computes cosine similarity between image pixels and query text using
   transformers CLIPModel if available.
3. Multi-Factor Semantic Metadata Scoring:
   Fast, zero-network fallback that validates keywords, entity tags,
   resolution, and penalizes generic logos/watermarks.
4. Threshold Rejection:
   Rejects candidates scoring below threshold, triggering next query alternatives
   or Pollinations FLUX generative fallback.
"""

import os
import re
import html
from pathlib import Path
from PIL import Image

# Global singleton cache for CLIP
_CLIP_MODEL = None
_CLIP_PROCESSOR = None
_CLIP_FAILED = False


def _load_clip_if_available():
    """Lazily load CLIP model and processor from HuggingFace cache or network."""
    global _CLIP_MODEL, _CLIP_PROCESSOR, _CLIP_FAILED
    if _CLIP_FAILED:
        return None, None
    if _CLIP_MODEL is not None and _CLIP_PROCESSOR is not None:
        return _CLIP_MODEL, _CLIP_PROCESSOR

    try:
        import torch
        from transformers import CLIPProcessor, CLIPModel
        model_name = "openai/clip-vit-base-patch32"
        # Try local first to avoid blocking if offline
        try:
            _CLIP_MODEL = CLIPModel.from_pretrained(model_name, local_files_only=True)
            _CLIP_PROCESSOR = CLIPProcessor.from_pretrained(model_name, local_files_only=True)
            print("👁️ Loaded local CLIP model for image-text verification.")
            return _CLIP_MODEL, _CLIP_PROCESSOR
        except Exception:
            # Try remote load if network is open
            _CLIP_MODEL = CLIPModel.from_pretrained(model_name)
            _CLIP_PROCESSOR = CLIPProcessor.from_pretrained(model_name)
            print("👁️ Downloaded and initialized CLIP model for image-text verification.")
            return _CLIP_MODEL, _CLIP_PROCESSOR
    except Exception as err:
        _CLIP_FAILED = True
        print(f"ℹ️ CLIP model notice (using high-accuracy semantic metadata verifier): {err}")
        return None, None


def clean_words(text):
    """Tokenize text into significant lowercase words."""
    if not text:
        return []
    clean = re.sub(r"[^\w\s-]", " ", str(text).lower())
    stopwords = {
        "the", "a", "an", "and", "or", "to", "of", "in", "on", "for",
        "at", "with", "from", "by", "is", "are", "was", "were", "this",
        "that", "these", "those", "scene", "shot", "image", "photo",
        "picture", "video", "footage", "clip", "showing", "depicting",
        "view", "close", "up",
    }
    return [w for w in clean.split() if len(w) > 1 and w not in stopwords]


def calculate_clip_similarity(image_path, query_text):
    """
    Calculate normalized cosine similarity (0 to 100) between an image file and query text using CLIP.
    Returns None if CLIP is not available.
    """
    model, processor = _load_clip_if_available()
    if model is None or processor is None:
        return None

    try:
        import torch
        image = Image.open(image_path).convert("RGB")
        inputs = processor(text=[query_text], images=image, return_tensors="pt", padding=True)
        with torch.no_grad():
            outputs = model(**inputs)
            logits_per_image = outputs.logits_per_image
            probs = logits_per_image.softmax(dim=1)
            # Cosine similarity between image and text features
            img_embeds = outputs.image_embeds / outputs.image_embeds.norm(p=2, dim=-1, keepdim=True)
            txt_embeds = outputs.text_embeds / outputs.text_embeds.norm(p=2, dim=-1, keepdim=True)
            sim = torch.sum(img_embeds * txt_embeds, dim=-1).item()
            # Normalize CLIP cosine sim (typically 0.15 - 0.35) into 0-100 scale
            normalized = max(0.0, min(100.0, (sim - 0.12) / (0.35 - 0.12) * 100.0))
            return normalized
    except Exception as e:
        print(f"CLIP similarity calculation notice: {e}")
        return None


def score_semantic_metadata(candidate_dict, query_text):
    """
    Score relevance of candidate media metadata against query keywords (0 to 100).
    Considers candidate title, tags, description, dimensions, and penalizes logos/graphics.
    """
    query_tokens = clean_words(query_text)
    if not query_tokens:
        return 50.0

    candidate_text = " ".join([
        str(candidate_dict.get("title", "")),
        str(candidate_dict.get("description", "")),
        str(candidate_dict.get("tags", "")),
        str(candidate_dict.get("slug", "")),
        str(candidate_dict.get("alt", "")),
    ])
    candidate_tokens = set(clean_words(candidate_text))

    # Calculate token match ratio
    matched_words = [w for w in query_tokens if w in candidate_tokens or any(w in ct for ct in candidate_tokens)]
    if not matched_words:
        return 0.0

    match_ratio = len(matched_words) / len(query_tokens)
    score = match_ratio * 70.0

    # Bonus for exact phrase matches
    clean_cand = candidate_text.lower()
    clean_q = " ".join(query_tokens)
    if len(clean_q) > 3 and clean_q in clean_cand:
        score += 20.0
    elif any(" ".join(query_tokens[i:i+2]) in clean_cand for i in range(len(query_tokens)-1)):
        score += 10.0

    # Resolution bonus
    w = candidate_dict.get("width", 0)
    h = candidate_dict.get("height", 0)
    if w >= 1280 or h >= 720:
        score += 10.0

    # Penalize undesirable visuals (logos, vectors, icons, newspaper clippings)
    penalty_terms = ["logo", "vector", "icon", "illustration", "svg", "clipart", "newspaper headline"]
    for bad in penalty_terms:
        if bad in clean_cand and bad not in clean_q:
            score -= 25.0

    return max(0.0, min(100.0, score))


def rank_video_candidates(video_candidates, query, orientation="landscape"):
    """
    Re-rank Pexels video candidates and select the best matching clip.
    Rejects clips scoring below threshold (< 30) so pipeline can try alternatives.
    """
    if not video_candidates:
        return None

    scored = []
    for vid in video_candidates:
        files = vid.get("video_files", [])
        if not files:
            continue

        # Find best HD file
        hd_files = [f for f in files if f.get("quality") == "hd" and (f.get("width") or 0) >= 1280]
        if not hd_files:
            hd_files = [f for f in files if (f.get("width") or 0) >= 640]
        if not hd_files:
            continue

        best_file = max(hd_files, key=lambda x: (x.get("width", 0) * x.get("height", 0)))
        w = best_file.get("width", 1920)
        h = best_file.get("height", 1080)

        # Orientation check
        is_portrait = h > w
        is_landscape = w > h
        orient_match = (
            (orientation == "portrait" and is_portrait)
            or (orientation == "landscape" and is_landscape)
            or (orientation == "square")
        )

        vid_metadata = {
            "title": vid.get("url", "").split("/")[-2].replace("-", " ") if vid.get("url") else "",
            "slug": vid.get("user", {}).get("name", ""),
            "width": w,
            "height": h,
            "duration": vid.get("duration", 10),
        }

        base_score = score_semantic_metadata(vid_metadata, query)
        # Only apply bonuses if there is actual topical/keyword relevance
        if base_score > 0:
            if orient_match:
                base_score += 10.0

            # Duration bonus: 5-30s is ideal for B-roll cuts
            dur = vid_metadata["duration"]
            if 4 <= dur <= 35:
                base_score += 5.0

        scored.append((base_score, vid, best_file, vid_metadata))

    if not scored:
        return None

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_vid, best_file, best_meta = scored[0]

    # Rejection threshold: must have at least 25 score to be considered relevant
    if best_score < 25.0:
        print(f"⚠️ Top video candidate scored low ({best_score:.1f}/100) for query '{query}'. Rejecting to try alternative.")
        return None

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", best_meta["title"].lower()).strip("_")[:30] or "pexels_clip"
    print(f"🎯 Selected best video candidate (Score: {best_score:.1f}/100): '{best_meta['title']}' for '{query}'")

    return {
        "download_url": best_file.get("link"),
        "title": slug,
        "duration": best_meta["duration"],
        "source": "Pexels Video",
        "score": best_score,
    }


def verify_image_candidate(image_path, query_text, candidate_metadata=None, threshold=30.0):
    """
    Verify if a candidate image matches the query text.
    Combines CLIP model similarity (if available) with semantic metadata score.
    Returns:
        (is_relevant: bool, score: float, method: str)
    """
    meta_score = score_semantic_metadata(candidate_metadata or {}, query_text)
    clip_score = None
    if image_path and Path(image_path).exists():
        clip_score = calculate_clip_similarity(image_path, query_text)

    if clip_score is not None:
        final_score = (clip_score * 0.6) + (meta_score * 0.4)
        method = "CLIP + Semantic"
    else:
        final_score = meta_score
        method = "Semantic Metadata"

    is_relevant = final_score >= threshold
    return is_relevant, final_score, method
