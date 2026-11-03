"""
Fact-Checking and Originality Reviewer for AutoTube AI (agents/fact_originality_reviewer.py).

Provides non-destructive pre-render/pre-upload editorial validation:
  1. Checks factual claims for traceable sources & context.
  2. Ensures distinction between facts, opinions, and unverified allegations.
  3. Identifies and flags unnecessary repetition across narration beats.
  4. Verifies presence of original commentary/analysis beyond raw aggregation.
  5. Flags visual misrepresentation risks (AI imagery vs real news events).
  6. Confirms title, thumbnail, and platform disclosure compliance.
  7. Returns structured findings (severity: ADVISORY, WARNING, CRITICAL) with suggested fixes.
  8. Strictly non-blocking by default (preserves existing upload behavior unless STRICT_FACT_CHECK_ENFORCEMENT=True).
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parent.parent

# Unverified allegation indicators that should be qualified with attribution phrases
ALLEGATION_KEYWORDS = [
    "allegedly", "rumored", "claims that", "sources suggest", "reportedly",
    "వార్తలు వస్తున్నాయి", "చెబుతున్నారు", "అనుమానం", "ప్రచారం"
]

# Words indicating numbers, metrics, or factual claims that need grounding
FACTUAL_CLAIM_PATTERNS = [
    r"\b\d+(?:[\,\.]\d+)?(?:\s*(?:crores|lakhs|million|billion|views|votes|percent|\%|cr))\b",
    r"\b(?:first time in history|world record|banned by government)\b",
]


def review_fact_and_originality(
    script_text: str,
    topic: str,
    title: str = "",
    thumbnail_text: str = "",
    visual_sources: Optional[List[str]] = None,
    strict_enforcement: bool = False,
) -> Dict[str, Any]:
    """
    Performs editorial review of script, packaging, and visual grounding.
    Returns structured findings with severity, explanation, and non-destructive fixes.
    """
    findings: List[Dict[str, Any]] = []
    script_clean = script_text.strip()
    lines = [l.strip() for l in script_clean.splitlines() if l.strip()]

    # 1. Check Factual Claims Traceability
    for pat in FACTUAL_CLAIM_PATTERNS:
        matches = re.findall(pat, script_clean, re.IGNORECASE)
        for m in matches:
            # Check if source attribution phrase is nearby
            attribution_found = any(att in script_clean.lower() for att in ("reports", "official", "sources", "according to", "నివేదికల ప్రకారం", "అధికారికంగా"))
            if not attribution_found:
                findings.append({
                    "rule": "Factual Claim Grounding",
                    "severity": "WARNING" if strict_enforcement else "ADVISORY",
                    "issue": f"Specific numerical/factual claim detected: '{m}' without clear contextual attribution.",
                    "suggested_fix": f"Prefix the claim with attribution (e.g., 'As per trade reports' or 'సమాచారం ప్రకారం').",
                })

    # 2. Distinguish Facts vs Allegations
    # If discussing intense accusations or controversies without qualifying them
    controversy_words = ["cheated", "crime", "bribe", "scam", "illegal", "కుంభకోణం", "మోసం", "నేరం"]
    has_controversy = any(cw in script_clean.lower() for cw in controversy_words)
    has_qualification = any(ak in script_clean.lower() for ak in ALLEGATION_KEYWORDS)
    if has_controversy and not has_qualification:
        findings.append({
            "rule": "Allegation Framing",
            "severity": "WARNING" if strict_enforcement else "ADVISORY",
            "issue": "Controversial allegations stated as absolute facts without attribution qualifier.",
            "suggested_fix": "Add journalistic framing like 'allegedly' or 'According to viral reports'.",
        })

    # 3. Unnecessary Information Repetition Check
    sentences = [s.strip() for s in re.split(r"[\.\?\!\n]+", script_clean) if len(s.strip()) > 15]
    seen_concepts = []
    for s in sentences:
        words = set(s.lower().split()[:5])
        duplicate = False
        for seen in seen_concepts:
            if len(words.intersection(seen)) >= 4:
                duplicate = True
                break
        if duplicate:
            findings.append({
                "rule": "Information Redundancy",
                "severity": "ADVISORY",
                "issue": f"Repetitive narrative concept detected in sentence: '{s[:60]}...'",
                "suggested_fix": "Condense or introduce a fresh analytical angle instead of repeating facts.",
            })
        else:
            seen_concepts.append(words)

    # 4. Original Analysis and Context Check
    analysis_signals = [
        "because", "analysis", "reason", "impact", "in reality", "why this matters",
        "ఎందుకు అంటే", "దీని వల్ల", "విశ్లేషిస్తే", "అసలు కారణం"
    ]
    has_analysis = any(asig in script_clean.lower() for asig in analysis_signals)
    if not has_analysis and len(lines) >= 4:
        findings.append({
            "rule": "Original Analysis & Value-Add",
            "severity": "ADVISORY",
            "issue": "Script reports facts but lacks original editorial breakdown or perspective.",
            "suggested_fix": "Add 1-2 sentences explaining why this development matters to the audience.",
        })

    # 5. Visual Misrepresentation Guard
    if visual_sources:
        ai_sources = [v for v in visual_sources if "ai_generation" in str(v).lower() or "flux" in str(v).lower()]
        news_topic = any(k in topic.lower() for k in ("news", "court", "police", "arrest", "hospital", "station"))
        if ai_sources and news_topic:
            findings.append({
                "rule": "Visual Misrepresentation Guard",
                "severity": "ADVISORY",
                "issue": "AI-generated visuals used for a breaking real-world news topic.",
                "suggested_fix": "Ensure on-screen watermark or disclaimer denotes dramatization / concept visual.",
            })

    # 6. Title / Thumbnail Representation Check
    if title:
        from agents.packaging_intelligence import verify_packaging_alignment
        pack_res = verify_packaging_alignment(title, thumbnail_text or "", script_clean)
        for iss in pack_res.get("issues", []):
            findings.append({
                "rule": "Packaging Integrity",
                "severity": "WARNING" if strict_enforcement else "ADVISORY",
                "issue": iss,
                "suggested_fix": "Align title and thumbnail keywords strictly with script events.",
            })

    # Overall Fact & Originality Score (0-100)
    score = 100.0 - (len(findings) * 12.0)
    score = max(30.0, min(100.0, score))

    # Review status determination
    has_critical = any(f["severity"] == "CRITICAL" for f in findings)
    has_warning = any(f["severity"] == "WARNING" for f in findings)

    if strict_enforcement and (has_critical or has_warning):
        status = "CHANGES_REQUESTED"
        passed = False
    else:
        status = "PASSED_WITH_ADVISORY" if findings else "PASSED_CLEAN"
        passed = True

    return {
        "status": status,
        "passed": passed,
        "score": round(score, 1),
        "total_findings": len(findings),
        "findings": findings,
        "is_advisory": not strict_enforcement,
        "summary": (
            f"Review completed with {len(findings)} editorial findings. "
            f"Status: {status} (Advisory-only mode: Pipeline will not be blocked)."
        ),
    }
