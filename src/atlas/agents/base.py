"""Base agent with telemetry and event publishing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

from atlas.core.blackboard import Blackboard
from atlas.core.models import AgentEvent, AgentRole
from atlas.infra.llm import LLMRouter
from atlas.infra.redis_bus import publish_event, store_checkpoint

logger = structlog.get_logger()


class BaseAgent(ABC):
    role: AgentRole

    def __init__(self, llm: LLMRouter | None = None) -> None:
        self.llm = llm or LLMRouter()

    async def execute(self, blackboard: Blackboard) -> Blackboard:
        await self._publish(blackboard, "started", f"{self.role.value} agent started")
        logger.info("agent_started", agent=self.role.value, run_id=blackboard.run_id)

        try:
            result = await self._run(blackboard)
            await self._publish(blackboard, "completed", f"{self.role.value} agent completed")
            await store_checkpoint(blackboard.run_id, blackboard.snapshot())
            return result
        except Exception as exc:
            await self._publish(blackboard, "failed", str(exc))
            logger.error("agent_failed", agent=self.role.value, error=str(exc))
            raise

    @abstractmethod
    async def _run(self, blackboard: Blackboard) -> Blackboard:
        ...

    async def _publish(
        self,
        blackboard: Blackboard,
        status: str,
        message: str,
        progress: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event = AgentEvent(
            run_id=blackboard.run_id,
            agent=self.role,
            status=status,
            message=message,
            progress=progress,
            metadata=metadata or {},
        )
        await publish_event(event)

    async def _llm_call(
        self,
        blackboard: Blackboard,
        prompt: str,
        system: str = "",
    ) -> str:
        response = await self.llm.generate(prompt, system)
        await blackboard.record_event(
            self.role,
            "llm_call",
            {"model": response.model, "cached": response.cached},
            token_count=response.input_tokens + response.output_tokens,
        )
        return response.text
