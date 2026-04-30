from __future__ import annotations

import json

import pytest

from src.infra.tool import mcp_global


class _FakeHub:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[str, object]] = []
        self.unsubscribed: list[str] = []
        self.start_calls = 0
        self.stop_if_idle_calls = 0

    def subscribe(self, channel: str, handler) -> str:
        token = f"token-{len(self.subscriptions) + 1}"
        self.subscriptions.append((channel, handler))
        return token

    def unsubscribe(self, token: str) -> None:
        self.unsubscribed.append(token)

    async def start(self) -> None:
        self.start_calls += 1

    async def stop_if_idle(self) -> None:
        self.stop_if_idle_calls += 1


class _FakeRedisClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


class _FakeManager:
    def __init__(self) -> None:
        self.close_calls = 0
        self._initialized = True

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_mcp_cache_pubsub_subscribes_to_invalidation_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_hub = _FakeHub()
    monkeypatch.setattr("src.infra.tool.mcp_global.get_pubsub_hub", lambda: fake_hub)

    pubsub = mcp_global.MCPGlobalCachePubSub()
    await pubsub.start_listener()

    assert fake_hub.start_calls == 1
    assert fake_hub.subscriptions[0][0] == mcp_global.MCP_CACHE_INVALIDATE_CHANNEL

    await pubsub.stop_listener()
    assert fake_hub.unsubscribed == ["token-1"]


@pytest.mark.asyncio
async def test_mcp_cache_pubsub_invalidates_foreign_user_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = _FakeManager()
    mcp_global._global_entries["user-1"] = mcp_global.GlobalMCPEntry(
        manager=fake_manager,
        tools=[],
    )

    pubsub = mcp_global.MCPGlobalCachePubSub()
    pubsub._instance_id = "instance-a"

    await pubsub._handle_message(
        {
            "data": json.dumps(
                {
                    "instance_id": "instance-b",
                    "scope": "user",
                    "user_id": "user-1",
                }
            )
        }
    )

    assert "user-1" not in mcp_global._global_entries
    assert fake_manager.close_calls == 1


@pytest.mark.asyncio
async def test_invalidate_global_cache_publishes_cross_instance_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr("src.infra.tool.mcp_global.get_redis_client", lambda: fake_redis)

    fake_manager = _FakeManager()
    mcp_global._global_entries["user-1"] = mcp_global.GlobalMCPEntry(
        manager=fake_manager,
        tools=[],
    )

    pubsub = mcp_global.MCPGlobalCachePubSub()
    pubsub._instance_id = "instance-a"
    monkeypatch.setattr(mcp_global, "get_mcp_cache_pubsub", lambda: pubsub)

    await mcp_global.invalidate_global_cache("user-1")

    assert fake_redis.published == [
        (
            mcp_global.MCP_CACHE_INVALIDATE_CHANNEL,
            json.dumps(
                {
                    "instance_id": "instance-a",
                    "scope": "user",
                    "user_id": "user-1",
                }
            ),
        )
    ]


@pytest.fixture(autouse=True)
def _reset_mcp_global_state() -> None:
    mcp_global._global_entries.clear()
    mcp_global._local_locks.clear()
