import os

os.environ["DEBUG"] = "false"

from pathlib import Path


def test_search_agent_subagents_enable_activity_logging():
    source = Path("src/agents/search_agent/nodes.py").read_text()

    assert "SubagentActivityMiddleware" in source


def test_subagent_activity_logging_externalizes_large_payloads_with_unique_paths():
    source = Path("src/infra/agent/middleware.py").read_text()

    assert "self._payload_dir" in source
    assert "self._payload_counter" in source
    assert "Full payload:" in source
    assert "payloads/{self._run_id}" in source
