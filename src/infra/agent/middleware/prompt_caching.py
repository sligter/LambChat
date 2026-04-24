"""Prompt caching middleware — KV cache optimization for Anthropic models."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from src.infra.agent.middleware._helpers import _system_message_to_blocks
from src.kernel.config import settings


class PromptCachingMiddleware(AgentMiddleware):
    """Re-tags cache breakpoints AFTER all user middleware has injected dynamic content.

    Problem
    -------
    deepagents' built-in ``AnthropicPromptCachingMiddleware`` runs **before** user
    middleware (AppPrompt, MemoryIndex, SandboxMCP, ToolSearch).  It tags the *then*
    last system-message content block with ``cache_control``, but user middleware
    subsequently appends more blocks (skills, memory, MCP tools, deferred stubs).
    The original cache breakpoint ends up in the middle of the final system message,
    so all dynamic content is re-processed every turn.

    Solution
    --------
    This middleware runs **last** in the user middleware chain (innermost layer).
    It walks the final system message and tools, then:

    1. Moves ``cache_control`` to the **actual** last content block so the full
       system message is one contiguous cache segment.
    2. Re-tags the **last tool** with ``cache_control`` (important when
       ``ToolSearchMiddleware`` has appended new tools).

    Result: between consecutive turns within the same session, the entire stable
    prefix (base prompt + workflow + skills + memory + MCP) is served from KV
    cache — only the changed tail (e.g. deferred-tool stubs) is re-processed.
    """

    _CACHE_CONTROL = {"type": "ephemeral"}

    def __init__(self) -> None:
        super().__init__()
        self._max_cached_system_blocks = max(
            int(getattr(settings, "PROMPT_CACHE_MAX_SYSTEM_BLOCKS", 8) or 0), 1
        )
        self._max_cached_tools = max(int(getattr(settings, "PROMPT_CACHE_MAX_TOOLS", 8) or 0), 1)

    @staticmethod
    def _is_anthropic_model(model: Any) -> bool:
        """Return True when request.model is backed by langchain-anthropic."""
        seen: set[int] = set()
        current = model
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            cls = type(current)
            if cls.__module__.startswith("langchain_anthropic"):
                return True

            # RunnableBinding and similar wrappers keep the underlying model on
            # ``bound``.  Some adapters use ``model`` for the wrapped runnable.
            next_model = getattr(current, "bound", None)
            if next_model is None:
                next_model = getattr(current, "_bound", None)
            if next_model is None:
                candidate = getattr(current, "model", None)
                next_model = candidate if not isinstance(candidate, str) else None
            current = next_model
        return False

    # ---- system message ---------------------------------------------------

    @staticmethod
    def _retag_system_message(
        system_message: Any, cache_control: dict, *, max_cached_blocks: int = 4
    ) -> Any:
        """Strip stale cache_control from inner blocks and tag the final block."""
        if system_message is None:
            return system_message

        blocks = _system_message_to_blocks(system_message)
        if not blocks:
            return system_message

        # Remove cache_control from every block
        for i, block in enumerate(blocks):
            if isinstance(block, dict) and "cache_control" in block:
                blocks[i] = {k: v for k, v in block.items() if k != "cache_control"}

        # Tag the last N blocks so semi-stable sections remain cacheable
        start_idx = max(len(blocks) - max_cached_blocks, 0)
        for i in range(start_idx, len(blocks)):
            block = blocks[i]
            base = block if isinstance(block, dict) else {"type": "text", "text": str(block)}
            blocks[i] = {**base, "cache_control": cache_control}

        return SystemMessage(content=blocks)

    # ---- tools ------------------------------------------------------------

    @staticmethod
    def _retag_tools(
        tools: list[Any] | None, cache_control: dict, *, max_cached_tools: int = 4
    ) -> list[Any] | None:
        """Re-tag the last tool with cache_control (handles newly appended tools)."""
        if not tools:
            return tools

        # Find and remove existing cache_control from tools
        cleaned = []
        tool_indices: list[int] = []
        for i, tool in enumerate(tools):
            if isinstance(tool, BaseTool):
                tool_indices.append(i)
                extras = tool.extras or {}
                if "cache_control" in extras:
                    new_extras = {k: v for k, v in extras.items() if k != "cache_control"}
                    cleaned.append(tool.model_copy(update={"extras": new_extras}))
                    continue
            cleaned.append(tool)

        # Tag the last N tools
        for idx in tool_indices[-max_cached_tools:]:
            tool = cleaned[idx]
            if isinstance(tool, BaseTool):
                new_extras = {**(tool.extras or {}), "cache_control": cache_control}
                cleaned[idx] = tool.model_copy(update={"extras": new_extras})

        return cleaned

    # ---- main entry -------------------------------------------------------

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._is_anthropic_model(getattr(request, "model", None)):
            return await handler(request)

        overrides: dict[str, Any] = {}

        new_system = self._retag_system_message(
            request.system_message,
            self._CACHE_CONTROL,
            max_cached_blocks=self._max_cached_system_blocks,
        )
        if new_system is not request.system_message:
            overrides["system_message"] = new_system

        new_tools = self._retag_tools(
            request.tools,
            self._CACHE_CONTROL,
            max_cached_tools=self._max_cached_tools,
        )
        if new_tools is not request.tools:
            overrides["tools"] = new_tools

        if overrides:
            request = request.override(**overrides)

        return await handler(request)
