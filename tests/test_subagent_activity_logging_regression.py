import os

os.environ["DEBUG"] = "false"

import asyncio
from pathlib import Path

from langchain_core.messages import AIMessage

from src.infra.agent.middleware import SubagentActivityMiddleware


def test_search_agent_subagents_enable_activity_logging():
    source = Path("src/agents/search_agent/nodes.py").read_text()

    assert "SubagentActivityMiddleware" in source


def test_search_agent_subagents_enable_tool_search_middleware():
    source = Path("src/agents/search_agent/nodes.py").read_text()

    assert "subagent_middleware.append(" in source
    assert "ToolSearchMiddleware(" in source


def test_fast_agent_subagents_enable_tool_search_middleware():
    source = Path("src/agents/fast_agent/nodes.py").read_text()

    assert "subagent_middleware.append(" in source
    assert "ToolSearchMiddleware(" in source


def test_subagent_activity_logging_externalizes_large_payloads_with_unique_paths():
    source = Path("src/infra/agent/middleware.py").read_text()

    assert "self._payload_dir" in source
    assert "self._payload_counter" in source
    assert "Full payload:" in source
    assert "payloads/{self._run_id}" in source


def test_subagent_activity_logging_appends_detail_hint_after_log_path():
    source = Path("src/infra/agent/middleware.py").read_text()

    assert "[Activity log saved to: {self._log_path}]" in source
    assert "For more details, check this file." in source


def test_subagent_activity_logging_keeps_full_llm_output_inline():
    middleware = SubagentActivityMiddleware(backend=None)
    llm_text = "A" * 2501

    entry = asyncio.run(middleware._build_llm_entry(None, AIMessage(content=llm_text)))

    assert f"> {llm_text}" in entry
    assert "Full payload:" not in entry
    assert "\n...\n" not in entry


def test_subagent_activity_logging_uses_datetime_with_timezone(monkeypatch):
    monkeypatch.setattr("src.infra.agent.middleware.time.strftime", lambda fmt: fmt)
    middleware = SubagentActivityMiddleware(backend=None)

    assert middleware._timestamp() == "%Y-%m-%d %H:%M:%S %z"


def test_subagent_activity_logging_formats_tool_calls_under_llm_entry():
    middleware = SubagentActivityMiddleware(backend=None)
    message = AIMessage(
        content="Let me search for that.",
        tool_calls=[
            {"id": "call_1", "name": "search_tools", "args": {}},
            {"id": "call_2", "name": "web_search_prime", "args": {}},
        ],
    )

    entry = asyncio.run(middleware._build_llm_entry(None, message))

    assert "> Let me search for that." in entry
    assert "Tool calls: search_tools, web_search_prime" in entry
