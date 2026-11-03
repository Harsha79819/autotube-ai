"""
AutoTube AI - Perceptual Image Hashing & Deduplication (utils/image_hasher.py)

Provides robust visual duplicate detection using perceptual difference hashing (dHash):
- Works with official `imagehash` library if installed, or high-performance native PIL+numpy implementation.
- Generates 64-bit hexadecimal perceptual hashes invariant to small rescales and compressions.
- Fast bitwise XOR Hamming distance calculation for duplicate matching.
"""

from pathlib import Path
from typing import Iterable, Optional, Tuple, Union
from PIL import Image

try:
    import imagehash as _ext_imagehash
    _HAS_EXTERNAL_IMAGEHASH = True
except ImportError:
    _HAS_EXTERNAL_IMAGEHASH = False
    _ext_imagehash = None

import numpy as np


def compute_image_hash(image_input: Union[str, Path, Image.Image], hash_size: int = 8) -> str:
    """
    Computes a 64-bit difference hash (dHash) hex string for an image.
    If imagehash is available, returns its dhash. Otherwise, computes
    the exact standard dHash via PIL and numpy.
    """
    try:
        if isinstance(image_input, (str, Path)):
            img = Image.open(str(image_input)).convert("L")
        else:
            img = image_input.convert("L")
    except Exception:
        return ""

    if _HAS_EXTERNAL_IMAGEHASH:
        try:
            return str(_ext_imagehash.dhash(img, hash_size=hash_size))
        except Exception:
            pass

    # High-performance native dHash implementation
    # Resize to (width = hash_size + 1, height = hash_size)
    resized = img.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = np.array(resized, dtype=np.float32)
    
    # Compare adjacent horizontal pixels: pixel[y, x] > pixel[y, x + 1]
    diff = pixels[:, 1:] > pixels[:, :-1]
    
    # Pack 64 boolean bits into a 16-character hexadecimal string
    bits = diff.flatten()
    val = 0
    for bit in bits:
        val = (val << 1) | int(bool(bit))
    
    # Return zero-padded 16-hex characters
    return f"{val:0{hash_size * hash_size // 4}x}"


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Calculates the Hamming distance (number of differing bits) between two hex hashes.
    Distance 0 = identical images.
    Distance <= 5 = very likely duplicate / slight crop or compression.
    Distance >= 10 = distinct images.
    """
    if not hash1 or not hash2:
        return 64
    try:
        v1 = int(hash1, 16)
        v2 = int(hash2, 16)
        return bin(v1 ^ v2).count("1")
    except ValueError:
        # Fallback character difference
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


def is_duplicate_hash(
    candidate_hash: str,
    seen_hashes: Iterable[str],
    threshold: int = 6,
) -> Tuple[bool, Optional[str]]:
    """
    Checks if candidate_hash is within `threshold` Hamming distance of any seen hash.
    Returns (is_duplicate: bool, matched_existing_hash: Optional[str]).
    """
    if not candidate_hash:
        return False, None

    for existing in seen_hashes:
        dist = hamming_distance(candidate_hash, existing)
        if dist <= threshold:
            return True, existing

    return False, None
