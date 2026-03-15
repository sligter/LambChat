"""
Feishu/Lark channel module.

This module provides Feishu (Lark) integration with WebSocket long connection support.
Each user can have their own Feishu bot configuration.
"""

from src.infra.channel.feishu.channel import FEISHU_AVAILABLE, FeishuChannel
from src.infra.channel.feishu.handler import (
    FeishuResponseCollector,
    create_feishu_message_handler,
    execute_feishu_agent,
    setup_feishu_handler,
)
from src.infra.channel.feishu.manager import (
    FeishuChannelManager,
    get_feishu_channel_manager,
    start_feishu_channels,
    stop_feishu_channels,
)
from src.infra.channel.feishu.markdown import FeishuMarkdownAdapter
from src.infra.channel.feishu.state import ConnectionState
from src.infra.channel.feishu.storage import FeishuStorage

__all__ = [
    # Channel
    "FEISHU_AVAILABLE",
    "FeishuChannel",
    "ConnectionState",
    # Manager
    "FeishuChannelManager",
    "get_feishu_channel_manager",
    "start_feishu_channels",
    "stop_feishu_channels",
    # Handler
    "FeishuResponseCollector",
    "create_feishu_message_handler",
    "execute_feishu_agent",
    "setup_feishu_handler",
    # Markdown
    "FeishuMarkdownAdapter",
    # Storage
    "FeishuStorage",
]
