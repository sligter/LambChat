"""
Checkpoint 存储实现

提供 LangGraph checkpointer 的工厂函数，支持 MongoDB 和 PostgreSQL 持久化。

用户通过 CHECKPOINT_BACKEND 配置选择后端：
- "mongodb": 使用 MongoDBSaver（默认，受 16MB 文档大小限制）
- "postgres": 使用 AsyncPostgresSaver（无文档大小限制，需 PostgreSQL 连接参数）

两者都不可用时回退到 MemorySaver（内存存储，重启丢失）。
"""

import time
from collections import OrderedDict
from typing import AsyncContextManager, Optional

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

_MEMORY_SAVER_MAX_THREADS = max(int(getattr(settings, "MEMORY_SAVER_MAX_THREADS", 200) or 0), 1)
_MEMORY_SAVER_TTL_SECONDS = max(
    int(getattr(settings, "MEMORY_SAVER_TTL_SECONDS", 3600) or 0),
    1,
)
_MEMORY_SAVER_CLEANUP_INTERVAL = max(
    int(getattr(settings, "MEMORY_SAVER_CLEANUP_INTERVAL", 50) or 0),
    1,
)

# MongoDB Checkpointer 单例
_mongo_checkpointer: Optional[object] = None

# PostgreSQL Checkpointer 单例
_pg_checkpointer: Optional[object] = None
_pg_checkpointer_ctx: Optional[AsyncContextManager] = None


def _cleanup_memory_saver_cache(now: float | None = None) -> int:
    cache: OrderedDict[str, tuple[object, float]] | None = getattr(
        get_async_checkpointer,
        "_memory_saver_cache",
        None,
    )
    if not cache:
        return 0

    current_time = time.time() if now is None else now
    removed = 0

    stale_threads = [
        thread_id
        for thread_id, (_, last_access) in list(cache.items())
        if current_time - last_access > _MEMORY_SAVER_TTL_SECONDS
    ]
    for thread_id in stale_threads:
        cache.pop(thread_id, None)
        removed += 1

    while len(cache) > _MEMORY_SAVER_MAX_THREADS:
        cache.popitem(last=False)
        removed += 1

    if not cache and hasattr(get_async_checkpointer, "_memory_saver_cache"):
        delattr(get_async_checkpointer, "_memory_saver_cache")

    return removed


def close_async_checkpointer() -> None:
    """Release MemorySaver fallback references so the process can reclaim memory."""
    if hasattr(get_async_checkpointer, "_memory_saver"):
        delattr(get_async_checkpointer, "_memory_saver")
    if hasattr(get_async_checkpointer, "_memory_saver_cache"):
        delattr(get_async_checkpointer, "_memory_saver_cache")
    if hasattr(get_async_checkpointer, "_memory_saver_access_count"):
        delattr(get_async_checkpointer, "_memory_saver_access_count")


def get_mongo_checkpointer(collection_name: str = "checkpoints"):
    """
    获取 MongoDB checkpointer 单例

    复用 motor 的底层同步 MongoClient，避免创建独立的同步连接池。

    Args:
        collection_name: MongoDB collection 名称，默认为 "checkpoints"

    Returns:
        MongoDBSaver 实例，如果创建失败则返回 None
    """
    global _mongo_checkpointer
    if _mongo_checkpointer is not None:
        return _mongo_checkpointer

    try:
        from langgraph.checkpoint.mongodb import MongoDBSaver

        from src.infra.storage.mongodb import get_mongo_client

        motor_client = get_mongo_client()
        sync_client = motor_client.delegate

        cp = MongoDBSaver(
            sync_client,
            db_name=settings.MONGODB_DB,
            checkpoint_collection_name=collection_name,
        )

        logger.info(
            f"MongoDB checkpointer created: {settings.MONGODB_DB}.{collection_name} (reusing motor connection pool)"
        )
        _mongo_checkpointer = cp
        return _mongo_checkpointer

    except ImportError as e:
        logger.warning(f"MongoDB checkpointer not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to create MongoDB checkpointer: {e}")
        return None


def close_mongo_checkpointer():
    """释放 MongoDB checkpointer 单例引用，允许 GC 回收。"""
    global _mongo_checkpointer
    if _mongo_checkpointer is not None:
        _mongo_checkpointer = None
        logger.info("MongoDB checkpointer reference released")


async def get_pg_checkpointer():
    """
    获取 PostgreSQL checkpointer 单例（异步）

    使用 AsyncPostgresSaver.from_conn_string()，无 16MB 文档大小限制。
    仅需 CHECKPOINT_BACKEND=postgres，独立于 ENABLE_POSTGRES_STORAGE。

    Returns:
        AsyncPostgresSaver 实例，如果创建失败则返回 None
    """
    global _pg_checkpointer, _pg_checkpointer_ctx

    if _pg_checkpointer is not None:
        return _pg_checkpointer

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        ctx = AsyncPostgresSaver.from_conn_string(settings.checkpoint_postgres_url)
        try:
            cp = await ctx.__aenter__()
        except Exception:
            await ctx.__aexit__(None, None, None)
            raise

        try:
            await cp.setup()
            logger.info("PostgreSQL checkpointer created (AsyncPostgresSaver via from_conn_string)")
            _pg_checkpointer_ctx = ctx
            _pg_checkpointer = cp
            return _pg_checkpointer
        except Exception:
            await ctx.__aexit__(None, None, None)
            raise

    except ImportError as e:
        logger.warning(f"PostgreSQL checkpointer not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to create PostgreSQL checkpointer: {e}")
        return None


async def close_pg_checkpointer():
    """
    关闭 PostgreSQL checkpointer（释放连接）

    应在应用关闭时调用。
    """
    global _pg_checkpointer, _pg_checkpointer_ctx
    ctx = _pg_checkpointer_ctx
    if _pg_checkpointer is not None and ctx is not None:
        try:
            await ctx.__aexit__(None, None, None)
            logger.info("PostgreSQL checkpointer closed")
        except Exception as e:
            logger.warning(f"Error closing PostgreSQL checkpointer: {e}")
        finally:
            _pg_checkpointer = None
            _pg_checkpointer_ctx = None


async def get_async_checkpointer(thread_id: str | None = None):
    """
    获取 checkpointer 实例（兼容异步调用）

    根据 CHECKPOINT_BACKEND 配置选择后端：
    - "postgres": 优先使用 PostgreSQL（无 16MB 限制）
    - "mongodb": 使用 MongoDB（默认）
    - 都不可用: 回退到 MemorySaver

    Args:
        thread_id: 可选的会话/线程 ID。仅在 MemorySaver fallback 时使用，
            用于按线程复用并限制进程内缓存规模。

    Returns:
        Checkpointer 实例
    """
    backend = getattr(settings, "CHECKPOINT_BACKEND", "mongodb")

    if backend == "postgres":
        logger.info("Using PostgreSQL checkpointer")
        checkpointer = await get_pg_checkpointer()
        if checkpointer is not None:
            return checkpointer
        logger.warning("PostgreSQL checkpointer unavailable, falling back")

    # MongoDB (default)
    logger.info("Using MongoDB checkpointer")
    checkpointer = get_mongo_checkpointer()
    if checkpointer is None:
        logger.warning("MongoDB checkpointer unavailable, falling back")
    if checkpointer is not None:
        return checkpointer

    # MemorySaver fallback
    from langgraph.checkpoint.memory import MemorySaver

    if thread_id:
        if not hasattr(get_async_checkpointer, "_memory_saver_cache"):
            get_async_checkpointer._memory_saver_cache = OrderedDict()  # type: ignore[attr-defined]
            get_async_checkpointer._memory_saver_access_count = 0  # type: ignore[attr-defined]
            logger.warning(
                "Using thread-scoped MemorySaver fallback cache (data will be lost on restart)"
            )

        cache: OrderedDict[str, tuple[MemorySaver, float]] = getattr(
            get_async_checkpointer,
            "_memory_saver_cache",
        )
        access_count = getattr(get_async_checkpointer, "_memory_saver_access_count", 0) + 1
        get_async_checkpointer._memory_saver_access_count = access_count  # type: ignore[attr-defined]
        if access_count % _MEMORY_SAVER_CLEANUP_INTERVAL == 0:
            _cleanup_memory_saver_cache()

        now = time.time()
        cached = cache.get(thread_id)
        if cached is not None:
            saver, _ = cached
            cache.move_to_end(thread_id)
            cache[thread_id] = (saver, now)
            return saver

        saver = MemorySaver()
        cache[thread_id] = (saver, now)
        _cleanup_memory_saver_cache(now=now)
        return saver

    if not hasattr(get_async_checkpointer, "_memory_saver"):
        get_async_checkpointer._memory_saver = MemorySaver()  # type: ignore[attr-defined]
        logger.warning("Using MemorySaver singleton (data will be lost on restart)")
    return get_async_checkpointer._memory_saver  # type: ignore[attr-defined]
