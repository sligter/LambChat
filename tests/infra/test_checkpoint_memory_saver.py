from __future__ import annotations

import pytest

import src.infra.storage.checkpoint as checkpoint_mod


@pytest.fixture(autouse=True)
def _reset_memory_saver_state(monkeypatch: pytest.MonkeyPatch) -> None:
    checkpoint_mod._mongo_checkpointer = None
    checkpoint_mod._pg_checkpointer = None
    checkpoint_mod._pg_checkpointer_ctx = None

    if hasattr(checkpoint_mod.get_async_checkpointer, "_memory_saver"):
        delattr(checkpoint_mod.get_async_checkpointer, "_memory_saver")
    if hasattr(checkpoint_mod.get_async_checkpointer, "_memory_saver_cache"):
        delattr(checkpoint_mod.get_async_checkpointer, "_memory_saver_cache")

    monkeypatch.setattr(
        checkpoint_mod,
        "get_mongo_checkpointer",
        lambda collection_name="checkpoints": None,
    )

    async def _fake_pg_checkpointer():
        return None

    monkeypatch.setattr(checkpoint_mod, "get_pg_checkpointer", _fake_pg_checkpointer)
    monkeypatch.setattr(checkpoint_mod, "_MEMORY_SAVER_MAX_THREADS", 3, raising=False)
    monkeypatch.setattr(checkpoint_mod, "_MEMORY_SAVER_TTL_SECONDS", 3600, raising=False)
    monkeypatch.setattr(checkpoint_mod, "_MEMORY_SAVER_CLEANUP_INTERVAL", 1, raising=False)


@pytest.mark.asyncio
async def test_memory_saver_fallback_reuses_same_thread_cache() -> None:
    saver1 = await checkpoint_mod.get_async_checkpointer(thread_id="session-1")
    saver2 = await checkpoint_mod.get_async_checkpointer(thread_id="session-1")

    assert saver1 is saver2


@pytest.mark.asyncio
async def test_memory_saver_fallback_bounds_cached_threads() -> None:
    for i in range(5):
        await checkpoint_mod.get_async_checkpointer(thread_id=f"session-{i}")

    cache = getattr(checkpoint_mod.get_async_checkpointer, "_memory_saver_cache")

    assert len(cache) == 3
    assert "session-0" not in cache
    assert "session-1" not in cache
