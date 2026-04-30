import asyncio

import pytest

from src.infra.storage import mongodb_store as store_module


@pytest.fixture(autouse=True)
def reset_store_singleton() -> None:
    store_module._store_instance = None
    store_module._store_initialized = False
    yield
    store_module._store_instance = None
    store_module._store_initialized = False


@pytest.mark.asyncio
async def test_acreate_store_uses_async_setup_for_mongodb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"setup": 0, "asetup": 0}

    monkeypatch.setattr(store_module.settings, "ENABLE_POSTGRES_STORAGE", False)

    def fake_setup(self) -> None:
        calls["setup"] += 1

    async def fake_asetup(self) -> None:
        calls["asetup"] += 1

    monkeypatch.setattr(store_module.MongoDBStore, "setup", fake_setup)
    monkeypatch.setattr(store_module.MongoDBStore, "asetup", fake_asetup)

    store = await store_module.acreate_store()

    assert isinstance(store, store_module.MongoDBStore)
    assert calls == {"setup": 0, "asetup": 1}


@pytest.mark.asyncio
async def test_acreate_store_initializes_singleton_once_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store_module.settings, "ENABLE_POSTGRES_STORAGE", False)

    created = 0

    async def fake_acreate_mongodb_store():
        nonlocal created
        created += 1
        await asyncio.sleep(0)
        return object()

    monkeypatch.setattr(store_module, "acreate_mongodb_store", fake_acreate_mongodb_store)

    first, second = await asyncio.gather(
        store_module.acreate_store(),
        store_module.acreate_store(),
    )

    assert created == 1
    assert first is second
