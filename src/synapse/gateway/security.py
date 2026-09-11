"""Prompt injection screening and API authentication."""

from __future__ import annotations

import re
import time
from collections import defaultdict

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from synapse.config import get_settings
from synapse.core.exceptions import PromptInjectionError

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?prior",
    r"you\s+are\s+now\s+a",
    r"system\s*:\s*",
    r"<\|?(system|admin|root)\|?>",
    r"jailbreak",
    r"do\s+anything\s+now",
    r"override\s+safety",
    r"forget\s+(your|all)\s+(rules|instructions)",
    r"act\s+as\s+(if|though|an?\s+\w+|admin|root)",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

_rate_buckets: dict[str, list[float]] = defaultdict(list)


async def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    settings = get_settings()
    expected = settings.synapse_api_key.get_secret_value()
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key


def check_rate_limit(client_id: str, rpm: int | None = None) -> None:
    settings = get_settings()
    limit = rpm or settings.rate_limit_rpm
    now = time.monotonic()
    window = 60.0

    bucket = _rate_buckets[client_id]
    _rate_buckets[client_id] = [t for t in bucket if now - t < window]

    if len(_rate_buckets[client_id]) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    _rate_buckets[client_id].append(now)


def screen_prompt_injection(text: str) -> None:
    """Screen for prompt injection at API boundary."""
    settings = get_settings()
    matched_patterns: list[str] = []
    score = 0.0

    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            matched_patterns.append(pattern.pattern)
            score += 0.5

    # Length-based heuristic
    if len(text) > 10000:
        score += 0.1

    # Excessive special characters
    special_ratio = sum(1 for c in text if not c.isalnum() and not c.isspace()) / max(len(text), 1)
    if special_ratio > 0.3:
        score += 0.15

    score = min(score, 1.0)

    if score >= settings.prompt_injection_threshold:
        raise PromptInjectionError(score, matched_patterns)
