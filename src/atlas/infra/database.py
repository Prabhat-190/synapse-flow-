"""PostgreSQL persistence for execution traces and vector store."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from atlas.config import get_settings
from atlas.core.models import ExecutionTrace, TraceEvent


class Base(DeclarativeBase):
    pass


class TraceRecord(Base):
    __tablename__ = "execution_traces"

    run_id = Column(String(36), primary_key=True)
    query = Column(Text, nullable=False)
    status = Column(String(32), default="running")
    trace_json = Column(Text, nullable=False)
    total_tokens = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime(timezone=True), nullable=True)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String(64), primary_key=True)
    doc_id = Column(String(64), nullable=False, index=True)
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, default="{}")
    # embedding stored as JSON array for portability without pgvector runtime
    embedding_json = Column(Text, nullable=True)


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, echo=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def persist_trace(trace: ExecutionTrace) -> None:
    factory = get_session_factory()
    async with factory() as session:
        record = TraceRecord(
            run_id=trace.run_id,
            query=trace.query,
            status=trace.status,
            trace_json=trace.model_dump_json(),
            total_tokens=trace.total_tokens,
            completed_at=trace.completed_at,
        )
        await session.merge(record)
        await session.commit()


async def load_trace(run_id: str) -> ExecutionTrace | None:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(TraceRecord).where(TraceRecord.run_id == run_id))
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return ExecutionTrace.model_validate_json(record.trace_json)


async def get_trace_events_since(run_id: str, since_index: int = 0) -> list[TraceEvent]:
    trace = await load_trace(run_id)
    if trace is None:
        return []
    return trace.events[since_index:]


async def seed_documents(chunks: list[dict[str, Any]]) -> None:
    factory = get_session_factory()
    async with factory() as session:
        for chunk in chunks:
            record = DocumentChunk(
                id=chunk["id"],
                doc_id=chunk["doc_id"],
                content=chunk["content"],
                metadata_json=json.dumps(chunk.get("metadata", {})),
                embedding_json=json.dumps(chunk.get("embedding", [])),
            )
            await session.merge(record)
        await session.commit()


async def search_documents(query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    """Cosine similarity search over stored embeddings."""
    import numpy as np

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(DocumentChunk))
        chunks = result.scalars().all()

    if not chunks:
        return []

    query_vec = np.array(query_embedding)
    query_norm = np.linalg.norm(query_vec) or 1.0
    scored = []

    for chunk in chunks:
        emb = json.loads(chunk.embedding_json or "[]")
        if not emb:
            continue
        doc_vec = np.array(emb)
        doc_norm = np.linalg.norm(doc_vec) or 1.0
        score = float(np.dot(query_vec, doc_vec) / (query_norm * doc_norm))
        scored.append({
            "doc_id": chunk.doc_id,
            "chunk_id": chunk.id,
            "text": chunk.content,
            "score": score,
            "metadata": json.loads(chunk.metadata_json or "{}"),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
