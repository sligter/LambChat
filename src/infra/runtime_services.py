"""
Runtime service orchestration for distributed listeners.

Centralizes startup/shutdown of lightweight process-local listeners that
coordinate through shared Redis/Mongo infrastructure.
"""

from __future__ import annotations

from src.infra.channel.pubsub import get_channel_config_pubsub
from src.infra.llm.pubsub import get_model_config_pubsub
from src.infra.memory.distributed import get_memory_pubsub
from src.infra.memory.tools import shutdown as memory_shutdown
from src.infra.settings.pubsub import get_settings_pubsub
from src.infra.task.manager import get_task_manager
from src.infra.tool.cache_pubsub import get_tool_cache_pubsub
from src.infra.tool.mcp_global import get_mcp_cache_pubsub
from src.infra.websocket import get_connection_manager


async def start_runtime_services() -> None:
    """Start distributed runtime listeners needed by the current process."""
    task_manager = get_task_manager()
    await task_manager.start_pubsub_listener()

    settings_pubsub = get_settings_pubsub()
    await settings_pubsub.start_listener()

    model_config_pubsub = get_model_config_pubsub()
    await model_config_pubsub.start_listener()

    memory_pubsub = get_memory_pubsub()
    await memory_pubsub.start_listener()

    channel_pubsub = get_channel_config_pubsub()
    await channel_pubsub.start_listener()

    tool_cache_pubsub = get_tool_cache_pubsub()
    await tool_cache_pubsub.start_listener()

    mcp_cache_pubsub = get_mcp_cache_pubsub()
    await mcp_cache_pubsub.start_listener()

    websocket_manager = get_connection_manager()
    await websocket_manager.start_pubsub_listener()


async def stop_runtime_services() -> None:
    """Stop distributed runtime listeners in reverse dependency order."""
    websocket_manager = get_connection_manager()
    await websocket_manager.stop_pubsub_listener()

    mcp_cache_pubsub = get_mcp_cache_pubsub()
    await mcp_cache_pubsub.stop_listener()

    tool_cache_pubsub = get_tool_cache_pubsub()
    await tool_cache_pubsub.stop_listener()

    channel_pubsub = get_channel_config_pubsub()
    await channel_pubsub.stop_listener()

    memory_pubsub = get_memory_pubsub()
    await memory_pubsub.stop_listener()
    await memory_shutdown()

    model_config_pubsub = get_model_config_pubsub()
    await model_config_pubsub.stop_listener()

    settings_pubsub = get_settings_pubsub()
    await settings_pubsub.stop_listener()

    task_manager = get_task_manager()
    await task_manager.stop_pubsub_listener()
