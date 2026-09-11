"""Token budget tracking with explicit overflow signaling."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenBudget:
    max_tokens: int
    reserved_for_output: int = 4096
    overflow_count: int = field(default=0, init=False)

    @property
    def available_input(self) -> int:
        return self.max_tokens - self.reserved_for_output

    def remaining(self, used: int) -> int:
        return max(0, self.available_input - used)

    def utilization(self, used: int) -> float:
        if self.available_input == 0:
            return 1.0
        return used / self.available_input

    def should_compress(self, used: int, threshold: float = 0.85) -> bool:
        return self.utilization(used) >= threshold

    def mark_overflow(self, tokens: int) -> None:
        self.overflow_count += 1

    def allocate(self, agent: str, tokens: int) -> dict[str, int]:
        return {
            "agent": agent,
            "allocated": tokens,
            "max": self.max_tokens,
        }
