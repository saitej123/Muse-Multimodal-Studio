"""Backwards-compatible shim.

The LLM layer lives in :mod:`llm_client` (Muse). This module is kept so existing
``from . import muse_client`` imports continue to work.
"""
from __future__ import annotations

from .llm_client import generate_from_images, generate_multimodal, generate_text, parallel_map

__all__ = ["generate_text", "generate_from_images", "generate_multimodal", "parallel_map"]
