"""
AutoTube AI - Local Face Verification & Consensus Clustering (agents/face_verifier.py)
Implements Section A5:
  1. Detects faces using OpenCV Haar Cascades (100% free, local, commercial-friendly).
  2. Embeds cropped faces using local SigLIP 2 Vision Encoder (Apache 2.0 / MIT).
  3. Clusters face embeddings across candidate images.
  4. Identifies the dominant cluster to achieve consensus on authentic person identity.
  5. Filters out random guests, audience faces, or unrelated persons.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image
try:
    import torch
except Exception:
    torch = None

_CASCADE = None

def get_face_cascade():
    global _CASCADE
    if _CASCADE is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _CASCADE = cv2.CascadeClassifier(cascade_path)
    return _CASCADE


def detect_and_crop_primary_face(image_path: str) -> Optional[np.ndarray]:
    """Detects and crops the primary/largest face with slight padding."""
    try:
        cascade = get_face_cascade()
        img = cv2.imread(str(image_path))
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(80, 80),
        )
        if len(faces) == 0:
            return None

        # Pick largest face
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces[0]

        # Add 15% padding
        pad_x = int(w * 0.15)
        pad_y = int(h * 0.15)
        h_img, w_img = img.shape[:2]
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(w_img, x + w + pad_x)
        y2 = min(h_img, y + h + pad_y)

        crop = img[y1:y2, x1:x2]
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        return crop_rgb
    except Exception as e:
        print(f"Face crop notice for {image_path}: {e}")
        return None


def get_face_embedding(face_rgb: np.ndarray) -> Optional[np.ndarray]:
    """Generates normalized 768-d face feature embedding using local SigLIP."""
    try:
        from agents.image_agent import get_siglip_pipeline
        model, processor = get_siglip_pipeline()
        if model is None or processor is None:
            return None

        pil_img = Image.fromarray(face_rgb)
        dev = next(model.parameters()).device
        inputs = processor(images=pil_img, return_tensors="pt")
        inputs = {k: v.to(dev) for k, v in inputs.items()}

        with torch.no_grad():
            if hasattr(model, "get_image_features"):
                features = model.get_image_features(**inputs)
            else:
                features = model(**inputs).pooler_output
            features = features / features.norm(dim=-1, keepdim=True)
            emb = features.cpu().numpy()[0]
            return emb
    except Exception as e:
        print(f"Face embedding notice: {e}")
        return None


def cluster_face_candidates(candidate_image_paths: List[str], similarity_threshold: float = 0.70) -> Dict[str, Any]:
    """
    Computes pairwise face consensus across multiple candidate images.
    Returns:
      {
        "dominant_indices": set of candidate indices belonging to majority cluster,
        "face_detected": {idx: True/False},
        "embeddings": {idx: emb},
        "consensus_confidence": float (0.0 to 1.0)
      }
    """
    crops = {}
    embeddings = {}

    for idx, path in enumerate(candidate_image_paths):
        face_crop = detect_and_crop_primary_face(path)
        if face_crop is not None:
            crops[idx] = face_crop
            emb = get_face_embedding(face_crop)
            if emb is not None:
                embeddings[idx] = emb

    if not embeddings:
        return {
            "dominant_indices": set(),
            "face_detected": {idx: False for idx in range(len(candidate_image_paths))},
            "consensus_confidence": 0.0,
            "has_consensus": False,
        }

    # Pairwise cosine similarity clustering
    indices = list(embeddings.keys())
    matrix = np.zeros((len(indices), len(indices)))
    for i, idx1 in enumerate(indices):
        for j, idx2 in enumerate(indices):
            matrix[i, j] = np.dot(embeddings[idx1], embeddings[idx2])

    # Simple connected components / greedy clustering
    clusters = []
    visited = set()
    for i in range(len(indices)):
        if i in visited:
            continue
        cluster = [i]
        visited.add(i)
        for j in range(len(indices)):
            if j not in visited and matrix[i, j] >= similarity_threshold:
                cluster.append(j)
                visited.add(j)
        clusters.append(cluster)

    # Dominant cluster is the largest one
    clusters = sorted(clusters, key=len, reverse=True)
    dominant_cluster = clusters[0] if clusters else []
    dominant_indices = {indices[i] for i in dominant_cluster}
    confidence = len(dominant_cluster) / max(1, len(indices))

    return {
        "dominant_indices": dominant_indices,
        "face_detected": {idx: (idx in embeddings) for idx in range(len(candidate_image_paths))},
        "consensus_confidence": round(confidence, 2),
        "has_consensus": len(dominant_cluster) >= 2 or len(indices) == 1,
    }
