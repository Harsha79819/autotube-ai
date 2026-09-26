"""
AutoTube AI - Unified Multi-Provider Router (providers/router.py)
Orchestrates prioritized execution across free provider chains with automatic fallback:
  - LLM: Gemini -> Groq -> OpenRouter
  - Visual: Pexels -> Pollinations FLUX
"""

import os
import time
from typing import Callable, Any
from providers.image import (
    search_pexels_photos,
    search_pexels_videos,
    search_duckduckgo_images,
    search_wikimedia,
    search_pixabay,
    generate_pollinations_image,
)
from providers.tracker import record_call, record_step_provider


def try_providers(step_name: str, providers: list, *args, **kwargs) -> Any:
    """
    Executes a chain of providers in prioritized sequence for a given step.
    Falls back automatically on exception, timeout, empty/invalid response, or rate limit.

    providers can be:
      - list of (name, callable) tuples
      - list of callables
      - list of dicts {"name": ..., "fn": ...}
    """
    last_errors = []
    attempt = 0

    for item in providers:
        attempt += 1
        is_fallback = (attempt > 1)

        if isinstance(item, (tuple, list)) and len(item) >= 2:
            name, fn = str(item[0]), item[1]
        elif isinstance(item, dict):
            name, fn = str(item.get("name", f"provider_{attempt}")), item.get("fn")
        elif callable(item):
            name = getattr(item, "__name__", f"provider_{attempt}")
            fn = item
        else:
            continue

        t0 = time.time()
        try:
            print(f"🔄 [{step_name.upper()}] Trying provider: {name}{' (FALLBACK)' if is_fallback else ''}...")
            result = fn(*args, **kwargs)
            dur_ms = (time.time() - t0) * 1000

            # Validate non-empty response
            if result is None:
                raise ValueError("Provider returned None")
            if isinstance(result, (str, list, dict)) and len(result) == 0:
                raise ValueError("Provider returned empty result")

            record_call(name, True, duration_ms=dur_ms)
            record_step_provider(step_name, name, duration_ms=dur_ms, is_fallback=is_fallback)
            print(f"✅ [{step_name.upper()}] {name} succeeded in {dur_ms:.0f}ms")
            return result
        except Exception as err:
            dur_ms = (time.time() - t0) * 1000
            record_call(name, False, error=str(err), duration_ms=dur_ms)
            print(f"⚠️ [{step_name.upper()}] Provider {name} failed: {err}. Trying next fallback...")
            last_errors.append(f"{name}: {err}")

    summary = "; ".join(last_errors)
    raise RuntimeError(f"All providers in chain failed for step '{step_name}': {summary}")


def get_visual_candidates(query, orientation="landscape", max_candidates=15):
    """
    Query multi-provider cascade in prioritized sequence:
      1. Pexels HD Stock (if key available)
      2. DuckDuckGo Image Search (free live web)
      3. Wikimedia Commons (news/history/places)
      4. Pixabay (if key configured)
    """
    candidates = []
    seen_urls = set()

    def _add_candidates(results, prov_name):
        if results:
            record_call(prov_name, True)
            for c in results:
                u = c.get("image_url")
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    candidates.append(c)
        else:
            record_call(prov_name, False, "No results returned")

    # 1. Pexels
    pexels_key = os.getenv("PEXELS_API_KEY", "")
    if pexels_key:
        pex_results = search_pexels_photos(query, pexels_key=pexels_key, orientation=orientation)
        _add_candidates(pex_results, "pexels")

    # 2. DuckDuckGo (Free web photography)
    if len(candidates) < max_candidates:
        ddg_results = search_duckduckgo_images(query, max_results=max_candidates - len(candidates))
        _add_candidates(ddg_results, "duckduckgo")

    # 3. Wikimedia Commons
    if len(candidates) < max_candidates:
        wiki_results = search_wikimedia(query, max_results=8)
        _add_candidates(wiki_results, "wikimedia")

    # 4. Pixabay (if key configured)
    pix_key = os.getenv("PIXABAY_API_KEY", "")
    if pix_key and len(candidates) < max_candidates:
        pix_results = search_pixabay(query, orientation=orientation)
        _add_candidates(pix_results, "pixabay")

    return candidates


def route_image_chain(query: str, destination_path: str, aspect_ratio: str = "16:9", step_name: str = "image") -> bool:
    """
    Executes 3-tier visual provider cascade according to IMAGE_PROVIDER_ORDER:
      1. Pexels Stock HD
      2. Pixabay Stock HD
      3. Pollinations.ai FLUX AI Generative Fallback
    """
    order_str = os.getenv("IMAGE_PROVIDER_ORDER", "pexels,pixabay,pollinations")
    providers_order = [p.strip().lower() for p in order_str.split(",") if p.strip()]

    def _try_pexels():
        key = os.getenv("PEXELS_API_KEY", "")
        if not key:
            raise ValueError("PEXELS_API_KEY not configured")
        orient = "portrait" if aspect_ratio == "9:16" else ("square" if aspect_ratio == "1:1" else "landscape")
        photos = search_pexels_photos(query, pexels_key=key, orientation=orient, per_page=5)
        if not photos:
            raise ValueError(f"No Pexels photos found for '{query}'")
        from agents.image_agent import download_image
        if download_image(photos[0], destination_path):
            return True
        raise RuntimeError("Failed downloading Pexels image")

    def _try_pixabay():
        key = os.getenv("PIXABAY_API_KEY", "")
        if not key:
            raise ValueError("PIXABAY_API_KEY not configured")
        orient = "portrait" if aspect_ratio == "9:16" else ("square" if aspect_ratio == "1:1" else "landscape")
        photos = search_pixabay(query, orientation=orient, max_results=5)
        if not photos:
            raise ValueError(f"No Pixabay photos found for '{query}'")
        from agents.image_agent import download_image
        if download_image(photos[0], destination_path):
            return True
        raise RuntimeError("Failed downloading Pixabay image")

    def _try_pollinations():
        success = generate_pollinations_image(query, destination_path, aspect_ratio=aspect_ratio)
        if not success:
            raise RuntimeError("Pollinations FLUX image generation failed")
        return True

    provider_fns = {
        "pexels": ("Pexels", _try_pexels),
        "pixabay": ("Pixabay", _try_pixabay),
        "pollinations": ("Pollinations FLUX", _try_pollinations),
    }

    chain = [provider_fns[p] for p in providers_order if p in provider_fns]
    if "pollinations" not in [p for p, _ in chain]:
        chain.append(provider_fns["pollinations"])

    return try_providers(step_name, chain)
