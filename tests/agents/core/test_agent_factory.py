from __future__ import annotations

import pytest

from src.agents.core.base import AgentFactory


class _DummyAgent:
    def __init__(self) -> None:
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True


@pytest.mark.asyncio
async def test_agent_factory_get_discovers_agents_when_registry_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.core import base as base_module

    AgentFactory._instances.clear()
    monkeypatch.setattr(base_module, "_AGENT_REGISTRY", {})

    def _fake_discover_agents() -> None:
        base_module._AGENT_REGISTRY["dummy"] = _DummyAgent

    monkeypatch.setattr("src.agents.discover_agents", _fake_discover_agents)

    agent = await AgentFactory.get("dummy")

    assert isinstance(agent, _DummyAgent)
    assert agent.initialized is True
