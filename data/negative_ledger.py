"""
data/negative_ledger.py - Persistent Negative Memory Ledger for AutoTube AI.

Tracks and enforces permanent exclusions across runs:
- Banned publisher URLs & Domains (e.g. political portals, clickbait archives)
- Banned image hashes (perceptual/MD5 hashes of corrupted, wrong-person, or prior-season images)
- Banned OCR text signatures (e.g. prior season branding, political slogans)
"""

import os
import re
import sqlite3
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from typing import Tuple, Optional, List, Dict, Any

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "autotube.db"


def get_db_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_negative_ledger_schema():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS negative_memory_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL CHECK(entry_type IN ('url', 'domain', 'image_hash', 'ocr_pattern')),
                value TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hit_count INTEGER DEFAULT 1
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_neg_ledger_type_val ON negative_memory_ledger(entry_type, value);")
        conn.commit()


def compute_image_hash(image_path: Path) -> str:
    """Computes a lightweight difference hash (dHash) and MD5 hash for visual duplicate detection."""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            # 8x8 difference hash (dHash)
            resized = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(resized.getdata())
            diff = []
            for row in range(8):
                for col in range(8):
                    diff.append(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
            decimal_val = 0
            for idx, bit in enumerate(diff):
                if bit:
                    decimal_val |= 1 << idx
            if decimal_val == 0:
                avg = sum(pixels) // max(1, len(pixels))
                return f"dhash:flat_{avg:03d}"
            dhash_str = f"dhash:{decimal_val:016x}"
            return dhash_str
    except Exception:
        # Fallback to file byte MD5
        try:
            with open(image_path, "rb") as f:
                return f"md5:{hashlib.md5(f.read()).hexdigest()}"
        except Exception:
            return ""


class NegativeMemoryLedger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            init_negative_ledger_schema()
            cls._instance._seed_baseline_exclusions()
        return cls._instance

    def _seed_baseline_exclusions(self):
        """Seed known prior-season and political patterns into the database if not present."""
        baseline_domains = [
            ("sakshi.com/telangana-politics", "Political aggregator"),
            ("greatandhra.com/politics", "Political news portal"),
            ("eenadu.net/andhra-pradesh/politics", "State political news"),
            ("etsy.com", "Commercial shopping site"),
            ("pinterest.com", "Social pin board low-fidelity"),
            ("aliexpress.com", "E-commerce platform"),
        ]
        baseline_patterns = [
            ("season 7", "Prior season Bigg Boss 7 branding"),
            ("season 8", "Prior season Bigg Boss 8 branding"),
            ("season 9", "Prior season Bigg Boss 9 branding"),
            ("bigg boss 7", "Prior season Bigg Boss 7 logo"),
            ("bigg boss 8", "Prior season Bigg Boss 8 logo"),
            ("bigg boss 9", "Prior season Bigg Boss 9 logo"),
            ("shiv thakare", "Hindi Bigg Boss contestant mismatch"),
            ("ysr congress", "Political entity mismatch"),
            ("chandrababu naidu", "Political entity mismatch"),
        ]
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for dom, reason in baseline_domains:
                cursor.execute("""
                    INSERT OR IGNORE INTO negative_memory_ledger (entry_type, value, reason)
                    VALUES ('domain', ?, ?)
                """, (dom.lower(), reason))
            for pat, reason in baseline_patterns:
                cursor.execute("""
                    INSERT OR IGNORE INTO negative_memory_ledger (entry_type, value, reason)
                    VALUES ('ocr_pattern', ?, ?)
                """, (pat.lower(), reason))
            conn.commit()

    def ban_url(self, url: str, reason: str):
        if not url:
            return
        clean_url = url.strip()
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO negative_memory_ledger (entry_type, value, reason)
                VALUES ('url', ?, ?)
                ON CONFLICT(value) DO UPDATE SET hit_count = hit_count + 1
            """, (clean_url, reason))

    def ban_domain(self, domain_or_url: str, reason: str):
        if not domain_or_url:
            return
        parsed = urlparse(domain_or_url)
        domain = (parsed.netloc or domain_or_url).lower().strip()
        if not domain:
            return
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO negative_memory_ledger (entry_type, value, reason)
                VALUES ('domain', ?, ?)
                ON CONFLICT(value) DO UPDATE SET hit_count = hit_count + 1
            """, (domain, reason))

    def ban_image_hash(self, image_path: Path, reason: str):
        h = compute_image_hash(Path(image_path))
        if not h:
            return
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO negative_memory_ledger (entry_type, value, reason)
                VALUES ('image_hash', ?, ?)
                ON CONFLICT(value) DO UPDATE SET hit_count = hit_count + 1
            """, (h, reason))

    def ban_ocr_pattern(self, pattern: str, reason: str):
        if not pattern or len(pattern.strip()) < 3:
            return
        clean_p = pattern.strip().lower()
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO negative_memory_ledger (entry_type, value, reason)
                VALUES ('ocr_pattern', ?, ?)
                ON CONFLICT(value) DO UPDATE SET hit_count = hit_count + 1
            """, (clean_p, reason))

    def is_url_banned(self, url: str) -> Tuple[bool, Optional[str]]:
        if not url:
            return False, None
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT reason FROM negative_memory_ledger WHERE entry_type='url' AND value=?", (url.strip(),))
            row = cursor.fetchone()
            if row:
                return True, f"Banned URL: {row[0]}"
        return False, None

    def is_domain_banned(self, domain_or_url: str) -> Tuple[bool, Optional[str]]:
        if not domain_or_url:
            return False, None
        parsed = urlparse(domain_or_url)
        domain = (parsed.netloc or domain_or_url).lower().strip()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value, reason FROM negative_memory_ledger WHERE entry_type='domain'")
            for banned_dom, reason in cursor.fetchall():
                if banned_dom in domain or domain in banned_dom:
                    return True, f"Banned domain '{banned_dom}': {reason}"
        return False, None

    def is_image_hash_banned(self, image_path: Path) -> Tuple[bool, Optional[str]]:
        h = compute_image_hash(Path(image_path))
        if not h:
            return False, None
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT reason FROM negative_memory_ledger WHERE entry_type='image_hash' AND value=?", (h,))
            row = cursor.fetchone()
            if row:
                return True, f"Banned image fingerprint: {row[0]}"
        return False, None

    def is_ocr_text_banned(self, ocr_text: str) -> Tuple[bool, Optional[str]]:
        if not ocr_text:
            return False, None
        t_lower = ocr_text.lower()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value, reason FROM negative_memory_ledger WHERE entry_type='ocr_pattern'")
            for pat, reason in cursor.fetchall():
                regex = r"\b" + re.escape(pat) + r"\b"
                if re.search(regex, t_lower):
                    return True, f"Matches banned OCR pattern '{pat}': {reason}"
        return False, None

    def audit_candidate(self, url: str = "", domain: str = "", image_path: Optional[Path] = None, ocr_text: str = "") -> Tuple[bool, str]:
        """One-stop audit method for all candidate visual assets."""
        if url:
            banned, reason = self.is_url_banned(url)
            if banned:
                return False, reason
            banned_dom, r_dom = self.is_domain_banned(url)
            if banned_dom:
                return False, r_dom

        if domain:
            banned_dom, r_dom = self.is_domain_banned(domain)
            if banned_dom:
                return False, r_dom

        if image_path and Path(image_path).exists():
            banned_h, r_h = self.is_image_hash_banned(Path(image_path))
            if banned_h:
                return False, r_h

        if ocr_text:
            banned_txt, r_txt = self.is_ocr_text_banned(ocr_text)
            if banned_txt:
                return False, r_txt

        return True, "CLEAN"


def get_negative_ledger() -> NegativeMemoryLedger:
    return NegativeMemoryLedger()
