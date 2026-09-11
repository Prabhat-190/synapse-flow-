"""Text embedding generation — deterministic hash-based for offline dev."""

from __future__ import annotations

import hashlib
import math


def embed_text(text: str, dim: int = 768) -> list[float]:
    """
    Generate a deterministic embedding vector.

    Uses hash-based projection for offline/testing. In production,
    swap with Gemini embedding API or sentence-transformers.
    """
    tokens = text.lower().split()
    vector = [0.0] * dim

    for token in tokens:
        h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        for i in range(dim):
            bit = (h >> (i % 64)) & 1
            vector[i] += 1.0 if bit else -0.5

    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
