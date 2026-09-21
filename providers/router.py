"""
AutoTube AI - Multi-Provider Router (providers/router.py)
Orchestrates prioritized visual sourcing across:
  Pexels -> DuckDuckGo -> Wikimedia -> Pixabay -> Pollinations FLUX AI
"""

import os
from providers.image import (
    search_pexels_photos,
    search_pexels_videos,
    search_duckduckgo_images,
    search_wikimedia,
    search_pixabay,
    generate_pollinations_image,
)
from providers.tracker import record_call

def get_visual_candidates(query, orientation="landscape", max_candidates=15):
    """
    Query multi-provider cascade in prioritized sequence:
      1. Pexels HD Stock (if key available)
      2. DuckDuckGo Image Search (free live web)
      3. Wikimedia Commons (news/history/places)
      4. Pixabay (if key available)
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

