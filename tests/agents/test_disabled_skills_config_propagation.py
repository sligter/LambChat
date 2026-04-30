from __future__ import annotations

from types import SimpleNamespace

import pytest


class _FakeDeepAgent:
    def __init__(self) -> None:
        self.captured_inner_config = None

    def with_config(self, _config):
        return self

    async def astream_events(self, _initial_state, config, version="v2"):
        self.captured_inner_config = config
        if False:
            yield version

    async def aget_state(self, _config):
        return SimpleNamespace(values={"messages": []})


class _FakeEventProcessor:
    def __init__(self, *_args, **_kwargs) -> None:
        self.output_text = ""

    async def process_event(self, _event) -> None:
        return None

    async def flush(self) -> None:
        return None

    def clear(self) -> None:
        return None


def _patch_common(monkeypatch: pytest.MonkeyPatch, module, fake_graph: _FakeDeepAgent) -> None:
    async def fake_get_model(**_kwargs):
        return object()

    async def fake_resolve_fallback_model(*_args, **_kwargs):
        return None

    async def fake_checkpointer(**_kwargs):
        return object()

    async def fake_store():
        return object()

    async def fake_emit_token_usage(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.LLMClient, "get_model", fake_get_model)
    monkeypatch.setattr(module, "resolve_fallback_model", fake_resolve_fallback_model)
    monkeypatch.setattr(module, "get_async_checkpointer", fake_checkpointer)
    monkeypatch.setattr(module, "acreate_store", fake_store)
    monkeypatch.setattr(module, "emit_token_usage", fake_emit_token_usage)
    monkeypatch.setattr(module, "AgentEventProcessor", _FakeEventProcessor)
    monkeypatch.setattr(module, "create_deep_agent", lambda **_kwargs: fake_graph)
    monkeypatch.setattr(module, "create_retry_middleware", lambda **_kwargs: [])
    monkeypatch.setattr(module, "ToolResultBinaryMiddleware", lambda **_kwargs: object())
    monkeypatch.setattr(module, "SubagentActivityMiddleware", lambda **_kwargs: object())
    monkeypatch.setattr(module, "PromptCachingMiddleware", lambda: object())
    monkeypatch.setattr(module.settings, "ENABLE_MCP", False)
    monkeypatch.setattr(module.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(module.settings, "ENABLE_SKILLS", False)


@pytest.mark.asyncio
async def test_fast_agent_node_propagates_disabled_skills_to_inner_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    presenter = object()
    config = {
        "configurable": {
            "context": context,
            "presenter": presenter,
            "disabled_skills": ["hidden-skill"],
            "base_url": "",
            "agent_options": {},
        }
    }

    await fast_nodes.fast_agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_inner_config is not None
    assert fake_graph.captured_inner_config["configurable"]["disabled_skills"] == ["hidden-skill"]


@pytest.mark.asyncio
async def test_search_agent_node_propagates_disabled_skills_to_inner_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.search_agent import nodes as search_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, search_nodes, fake_graph)

    async def fake_create_backend_and_prompt(**_kwargs):
        return object(), "system prompt", object(), None

    monkeypatch.setattr(search_nodes, "_create_backend_and_prompt", fake_create_backend_and_prompt)

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    presenter = object()
    config = {
        "configurable": {
            "context": context,
            "presenter": presenter,
            "disabled_skills": ["hidden-skill"],
            "base_url": "",
            "agent_options": {},
        }
    }

    await search_nodes.agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_inner_config is not None
    assert fake_graph.captured_inner_config["configurable"]["disabled_skills"] == ["hidden-skill"]
