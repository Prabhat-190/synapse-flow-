"""Decomposition agent — creates typed subtask DAG."""

from __future__ import annotations

import json

from atlas.agents.base import BaseAgent
from atlas.core.blackboard import Blackboard
from atlas.core.models import AgentRole, Subtask, SubtaskDAG


class DecompositionAgent(BaseAgent):
    role = AgentRole.DECOMPOSITION

    PROMPT = """Decompose this query into a directed acyclic graph of subtasks.

Query: {query}

Each subtask needs: description, agent (retrieval|reasoning|critique|synthesis), dependencies (list of indices).

Respond with JSON: {{"subtasks": [{{"description": "...", "agent": "...", "dependencies": []}}]}}"""

    async def _run(self, blackboard: Blackboard) -> Blackboard:
        prompt = self.PROMPT.format(query=blackboard.trace.query)
        response = await self._llm_call(blackboard, prompt)

        try:
            data = json.loads(response)
            subtasks_raw = data.get("subtasks", [])
        except json.JSONDecodeError:
            subtasks_raw = self._default_subtasks()

        nodes: list[Subtask] = []
        id_map: dict[int, str] = {}

        for i, st in enumerate(subtasks_raw):
            node = Subtask(
                description=st.get("description", f"Subtask {i}"),
                agent=AgentRole(st.get("agent", "retrieval")),
                dependencies=[],
            )
            id_map[i] = node.id
            nodes.append(node)

        for i, st in enumerate(subtasks_raw):
            deps = st.get("dependencies", [])
            nodes[i].dependencies = [
                id_map[int(d)] for d in deps if int(d) in id_map
            ]

        dag = SubtaskDAG(root_query=blackboard.trace.query, nodes=nodes)
        await blackboard.set_dag(dag)
        await blackboard.record_event(
            self.role,
            "dag_created",
            {"node_count": len(nodes), "nodes": [n.description for n in nodes]},
        )
        return blackboard

    def _default_subtasks(self) -> list[dict]:
        return [
            {"description": "Retrieve relevant documents", "agent": "retrieval", "dependencies": []},
            {"description": "Reason over context", "agent": "reasoning", "dependencies": [0]},
            {"description": "Critique claims", "agent": "critique", "dependencies": [1]},
            {"description": "Synthesize answer", "agent": "synthesis", "dependencies": [2]},
        ]
