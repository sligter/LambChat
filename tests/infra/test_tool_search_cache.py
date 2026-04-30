from __future__ import annotations

import gc

from src.infra.tool import tool_search


class _FakeTool:
    def __init__(self, idx: int) -> None:
        self.name = f"server:tool_{idx}"
        self.description = f"Tool {idx} for cache cleanup testing"
        self.server = "server"


def test_parse_cache_does_not_retain_transient_tool_objects() -> None:
    tool_search._parse_cache.clear()

    tools = [_FakeTool(i) for i in range(50)]
    results = tool_search.search_tools_with_keywords("tool", tools, max_results=100)

    assert len(results) == 50
    assert len(tool_search._parse_cache) == 50

    del results
    del tools
    gc.collect()

    assert len(tool_search._parse_cache) == 0
