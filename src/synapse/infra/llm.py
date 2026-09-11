"""LLM provider abstraction with retry, fallback, and circuit breaker."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from synapse.config import Settings, get_settings
from synapse.core.exceptions import LLMProviderError

logger = structlog.get_logger()


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    failures: int = field(default=0, init=False)
    last_failure: float = field(default=0.0, init=False)
    is_open: bool = field(default=False, init=False)

    def record_success(self) -> None:
        self.failures = 0
        self.is_open = False

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure = time.monotonic()
        if self.failures >= self.failure_threshold:
            self.is_open = True
            logger.warning("circuit_breaker_open", failures=self.failures)

    def can_execute(self) -> bool:
        if not self.is_open:
            return True
        if time.monotonic() - self.last_failure > self.recovery_timeout:
            self.is_open = False
            self.failures = 0
            return True
        return False


class SemanticCache:
    """Simple hash-based response cache for identical prompts."""

    def __init__(self, max_size: int = 256) -> None:
        self._cache: dict[str, LLMResponse] = {}
        self._max_size = max_size

    def _key(self, prompt: str, model: str) -> str:
        return hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()

    def get(self, prompt: str, model: str) -> LLMResponse | None:
        resp = self._cache.get(self._key(prompt, model))
        if resp:
            return LLMResponse(
                text=resp.text,
                model=resp.model,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cached=True,
            )
        return None

    def put(self, prompt: str, response: LLMResponse) -> None:
        if len(self._cache) >= self._max_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[self._key(prompt, response.model)] = response


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system: str = "", **kwargs: Any) -> LLMResponse: ...


class GeminiProvider(BaseLLMProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.gemini_model
        self._breaker = CircuitBreaker()
        self._cache = SemanticCache()
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import google.generativeai as genai

                api_key = self.settings.gemini_api_key.get_secret_value()
                if api_key:
                    genai.configure(api_key=api_key)
                    self._client = genai.GenerativeModel(self.model)
                else:
                    self._client = None
            except ImportError:
                self._client = None
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def generate(self, prompt: str, system: str = "", **kwargs: Any) -> LLMResponse:
        if not self._breaker.can_execute():
            raise LLMProviderError("gemini", "Circuit breaker open")

        cached = self._cache.get(prompt, self.model)
        if cached:
            return cached

        client = self._get_client()
        start = time.monotonic()

        if client is None:
            # Deterministic mock for offline/dev without API key
            response = self._mock_generate(prompt, system)
            self._breaker.record_success()
            return response

        try:
            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            result = await asyncio.to_thread(client.generate_content, full_prompt)
            text = result.text if hasattr(result, "text") else str(result)
            latency = (time.monotonic() - start) * 1000

            resp = LLMResponse(
                text=text,
                model=self.model,
                input_tokens=len(full_prompt.split()),
                output_tokens=len(text.split()),
                latency_ms=latency,
            )
            self._cache.put(prompt, resp)
            self._breaker.record_success()
            return resp
        except Exception as exc:
            self._breaker.record_failure()
            raise LLMProviderError("gemini", str(exc)) from exc

    def _mock_generate(self, prompt: str, system: str) -> LLMResponse:
        """Intelligent mock for testing without API keys."""
        prompt_lower = prompt.lower()
        combined = f"{system} {prompt}".lower()

        # Order matters: specific agent intents before generic keyword matches
        if "synthes" in prompt_lower or "final polished answer" in prompt_lower:
            text = (
                "Based on retrieved evidence, LangGraph provides stateful multi-agent "
                "orchestration with cyclic graph support [1]. pgvector enables efficient "
                "vector similarity search within PostgreSQL [2]. RAG combines retrieval "
                "with LLM reasoning for grounded, citation-backed answers [3]."
            )
        elif "critique" in prompt_lower or "score each claim" in prompt_lower:
            text = json.dumps(
                {
                    "spans": [
                        {
                            "text": "LangGraph enables stateful multi-agent workflows.",
                            "score": 0.95,
                            "flagged": False,
                        },
                        {
                            "text": "This is unsupported claim.",
                            "score": 0.3,
                            "flagged": True,
                            "reason": "No citation",
                        },
                    ]
                }
            )
        elif "compress" in prompt_lower:
            text = json.dumps(
                {
                    "summary": "Compressed context preserving key facts.",
                    "mode": "lossy",
                    "ratio": 0.4,
                }
            )
        elif "rewrite" in prompt_lower or ("meta" in prompt_lower and "prompt" in prompt_lower):
            text = json.dumps(
                {
                    "rewritten_prompt": "Provide a concise, citation-backed answer.",
                    "rationale": "Original prompt was ambiguous",
                }
            )
        elif "decide which agent should run next" in combined or "routing_decision" in combined:
            text = json.dumps(
                {
                    "next_agent": "decomposition",
                    "reason": "Query requires task breakdown",
                    "confidence": 0.92,
                }
            )
        elif "decompos" in prompt_lower or "subtask" in prompt_lower:
            text = json.dumps(
                {
                    "subtasks": [
                        {
                            "description": "Retrieve relevant documents",
                            "agent": "retrieval",
                            "dependencies": [],
                        },
                        {
                            "description": "Reason over retrieved context",
                            "agent": "reasoning",
                            "dependencies": ["0"],
                        },
                        {
                            "description": "Critique factual claims",
                            "agent": "critique",
                            "dependencies": ["1"],
                        },
                        {
                            "description": "Synthesize final answer",
                            "agent": "synthesis",
                            "dependencies": ["2"],
                        },
                    ]
                }
            )
        elif "retriev" in prompt_lower or "search" in prompt_lower:
            text = json.dumps(
                {
                    "results": [
                        {
                            "doc_id": "doc-1",
                            "chunk_id": "c-1",
                            "text": "LangGraph enables stateful multi-agent workflows.",
                            "score": 0.95,
                        },
                        {
                            "doc_id": "doc-2",
                            "chunk_id": "c-2",
                            "text": "pgvector provides efficient similarity search in PostgreSQL.",
                            "score": 0.88,
                        },
                    ]
                }
            )
        elif "draft answer" in prompt_lower or "reasoning agent" in prompt_lower:
            text = (
                "LangGraph enables stateful multi-agent workflows with shared state [doc-langgraph]. "
                "pgvector provides efficient similarity search in PostgreSQL [doc-pgvector]."
            )
        else:
            text = f"Analysis complete for: {prompt[:200]}"

        return LLMResponse(
            text=text,
            model=f"{self.model}-mock",
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            latency_ms=50.0,
        )


class LLMRouter:
    """Routes to primary model with deterministic fallback."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.primary = GeminiProvider(settings)
        self.fallback = GeminiProvider(settings)
        self.fallback.model = settings.fallback_model if settings else "gemini-1.5-flash"

    async def generate(self, prompt: str, system: str = "", **kwargs: Any) -> LLMResponse:
        try:
            return await self.primary.generate(prompt, system, **kwargs)
        except LLMProviderError as exc:
            logger.warning("llm_fallback", primary_error=str(exc))
            try:
                resp = await self.fallback.generate(prompt, system, **kwargs)
                return LLMResponse(
                    text=resp.text,
                    model=f"{resp.model}-fallback",
                    input_tokens=resp.input_tokens,
                    output_tokens=resp.output_tokens,
                    latency_ms=resp.latency_ms,
                )
            except LLMProviderError:
                # Deterministic fallback — parse intent and return structured response
                return self.primary._mock_generate(prompt, system)
