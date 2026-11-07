#!/usr/bin/env python3
"""
tools/telugu_typography.py - Alias for tools/native_typography.py
"""
from tools.native_typography import (
    render_native_telugu_badge,
    render_native_indic_text,
    render_pillow_fallback_badge,
)

__all__ = [
    "render_native_telugu_badge",
    "render_native_indic_text",
    "render_pillow_fallback_badge",
]
