"""
Async SQLAlchemy engine + session factory for FastAPI.
Provides get_db() dependency and init_db() startup hook.
"""
from __future__ import annotations

import os
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models import Base

logger = logging.getLogger("agora.db")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Resolve DATABASE_URL, converting postgresql:// to postgresql+asyncpg://."""
    url = os.getenv("DATABASE_URL", "postgresql://agora:agora@localhost:5432/agora")
    # Ensure async driver
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = get_database_url()
        pool_kwargs = {} if url.startswith("sqlite") else {"pool_size": 5, "max_overflow": 10}
        _engine = create_async_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            **pool_kwargs,
        )
        logger.info(f"Created async engine: {url.split('@')[-1] if '@' in url else url}")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def init_db() -> None:
    """Create all tables on startup."""
    engine = get_engine()
    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # PRD §8.10 Cross-Incident Memory — enables the native `vector` column type used by
            # Hypothesis.embedding (models.py). No-op / already-present on repeat startups.
            try:
                from sqlalchemy import text
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception as e:
                logger.warning(f"Could not enable pgvector extension (non-fatal): {e}")
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


async def close_db() -> None:
    """Close engine on shutdown."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine disposed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async session, auto-closes."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
