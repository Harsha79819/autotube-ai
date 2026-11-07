#!/usr/bin/env python3
"""
tools/browser_harvester.py - Real-Time Web Proof & Dynamic Content Harvester

Leverages Playwright headless Chromium to capture live browser evidence and scrape
dynamic JavaScript-heavy websites that block standard HTTP requests:
1. Live Voting Poll Cards: Screenshots real Bigg Boss voting percentages for video b-roll.
2. Social Media Proof Cards: Screenshots tweets, X posts, and community discussions.
3. JavaScript-Rendered News Extraction: Bypasses 403 Forbidden / Cloudflare on news sites.
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "data" / "cache" / "browser_evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def capture_web_element_screenshot(
    url: str,
    output_path: str,
    selector: Optional[str] = None,
    wait_time_secs: float = 2.0,
    dark_mode: bool = True,
    width: int = 1280,
    height: int = 800,
) -> Optional[str]:
    """
    Navigates to any URL and captures a clean screenshot of the page or a specific CSS element.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            color_scheme = "dark" if dark_mode else "light"
            context = browser.new_context(
                viewport={"width": width, "height": height},
                color_scheme=color_scheme,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)

            if wait_time_secs > 0:
                time.sleep(wait_time_secs)

            if selector:
                elem = page.query_selector(selector)
                if elem:
                    elem.screenshot(path=str(out_file))
                    browser.close()
                    print(f"📸 [Browser Harvester] Captured element ({selector}): {out_file.name}")
                    return str(out_file)

            # Full viewport screenshot fallback
            page.screenshot(path=str(out_file))
            browser.close()
            print(f"📸 [Browser Harvester] Captured viewport: {out_file.name}")
            return str(out_file)

    except Exception as exc:
        print(f"⚠️ [Browser Harvester] Notice for {url}: {exc}")

    return None


def fetch_dynamic_webpage_text(url: str, timeout_ms: int = 12000) -> str:
    """
    Loads dynamic client-side JS pages and extracts visible text content.
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            content = page.inner_text("body")
            browser.close()
            return content.strip()
    except Exception as exc:
        print(f"⚠️ [Browser Harvester Text] Notice for {url}: {exc}")
        return ""


if __name__ == "__main__":
    test_url = "https://news.google.com"
    test_out = "/tmp/test_harvest_google.png"
    res = capture_web_element_screenshot(test_url, test_out, width=1080, height=720)
    print("Harvester test result:", res)
