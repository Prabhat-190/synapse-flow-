"""Domain-specific exceptions."""


class SynapseError(Exception):
    """Base exception for SynapseFlow orchestrator."""


class BudgetOverflowError(SynapseError):
    """Raised when context exceeds token budget — never silently truncated."""

    def __init__(self, current_tokens: int, max_tokens: int) -> None:
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens
        super().__init__(
            f"Budget overflow: {current_tokens} tokens exceeds limit of {max_tokens}. "
            "Routing to Compression agent."
        )


class PromptInjectionError(SynapseError):
    """Raised when prompt injection is detected at API boundary."""

    def __init__(self, score: float, patterns: list[str]) -> None:
        self.score = score
        self.patterns = patterns
        super().__init__(f"Prompt injection detected (score={score:.2f}): {patterns}")


class AgentExecutionError(SynapseError):
    """Raised when an agent fails irrecoverably."""

    def __init__(self, agent: str, reason: str) -> None:
        self.agent = agent
        self.reason = reason
        super().__init__(f"Agent {agent} failed: {reason}")


class LLMProviderError(SynapseError):
    """Raised when LLM API calls fail after retries."""

    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"LLM provider {provider} error: {reason}")
