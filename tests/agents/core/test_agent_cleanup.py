from __future__ import annotations

import asyncio

import pytest

from src.agents.core.base import BaseGraphAgent


class _TestAgent(BaseGraphAgent):
    def build_graph(self, builder) -> None:
        return None


@pytest.mark.asyncio
async def test_close_cancels_background_cleanup_task() -> None:
    agent = _TestAgent()
    cleanup_task = asyncio.create_task(asyncio.sleep(3600))
    agent._cleanup_task = cleanup_task

    await agent.close()

    assert cleanup_task.cancelled() is True
