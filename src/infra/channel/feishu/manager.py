"""
Feishu channel manager for managing multiple user bot connections.
"""

import logging
from typing import Any, Callable, Optional

from src.infra.channel.base import UserChannelManager
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.feishu.channel import FEISHU_AVAILABLE, FeishuChannel
from src.kernel.schemas.channel import ChannelType
from src.kernel.schemas.feishu import FeishuConfig, FeishuGroupPolicy

logger = logging.getLogger(__name__)


class FeishuChannelManager(UserChannelManager):
    """
    Manager for all user Feishu channels.

    Manages multiple Feishu bot connections, one per user.
    """

    channel_type = ChannelType.FEISHU
    config_class = FeishuConfig

    def __init__(self, message_handler: Optional[Callable] = None):
        super().__init__(message_handler)
        self._storage = ChannelStorage()
        self._message_handler: Optional[Callable] = message_handler

    @classmethod
    def get_instance(cls) -> "FeishuChannelManager":
        """Get the singleton instance, consistent with get_feishu_channel_manager()."""
        return get_feishu_channel_manager()

    def _dict_to_config(self, user_id: str, config_dict: dict[str, Any]) -> FeishuConfig:
        """Convert a config dict to FeishuConfig."""
        return FeishuConfig(
            user_id=user_id,
            app_id=config_dict.get("app_id") or "",
            app_secret=config_dict.get("app_secret") or "",
            encrypt_key=config_dict.get("encrypt_key") or "",
            verification_token=config_dict.get("verification_token") or "",
            react_emoji=config_dict.get("react_emoji") or "THUMBSUP",
            group_policy=FeishuGroupPolicy(config_dict.get("group_policy") or "mention"),
            enabled=config_dict.get("enabled", True),
        )

    async def start(self) -> None:
        """Start all enabled Feishu channels."""
        if not FEISHU_AVAILABLE:
            logger.warning("Feishu SDK not installed. Run: pip install lark-oapi")
            return

        self._running = True

        # Load all enabled configs from ChannelStorage
        config_dicts = await self._storage.list_enabled_configs(ChannelType.FEISHU)
        logger.info(f"Found {len(config_dicts)} enabled Feishu configurations")

        for config_dict in config_dicts:
            try:
                user_id = config_dict.get("user_id")
                if not user_id:
                    logger.warning("Skipping config without user_id")
                    continue

                # Check if required fields are present (decryption may have failed)
                app_id = config_dict.get("app_id") or ""
                app_secret = config_dict.get("app_secret") or ""

                if not app_id or not app_secret:
                    logger.warning(
                        f"Skipping Feishu config for user {user_id}: "
                        "missing app_id or app_secret (decryption may have failed). "
                        "Please re-save the channel configuration."
                    )
                    continue

                config = self._dict_to_config(user_id, config_dict)
                await self._start_user_client(config)
            except Exception as e:
                logger.error(
                    f"Failed to start Feishu client for user {config_dict.get('user_id')}: {e}"
                )

    async def stop(self) -> None:
        """Stop all Feishu channels."""
        self._running = False

        for user_id, client in list(self._channels.items()):
            try:
                await client.stop()
            except Exception as e:
                logger.error(f"Error stopping Feishu client for user {user_id}: {e}")

        self._channels.clear()
        await self._storage.close()

    async def _start_user_client(self, config: FeishuConfig) -> bool:
        """Start a user's Feishu client."""
        if config.user_id in self._channels:
            await self._channels[config.user_id].stop()

        client = FeishuChannel(config, self._message_handler)
        success = await client.start()

        if success:
            self._channels[config.user_id] = client
            return True
        return False

    async def reload_user(self, user_id: str) -> bool:
        """Reload a user's Feishu configuration and restart the client."""
        config_dict = await self._storage.get_config(user_id, ChannelType.FEISHU)

        # Stop existing client if any
        if user_id in self._channels:
            await self._channels[user_id].stop()
            del self._channels[user_id]

        # Start new client if enabled
        if config_dict and config_dict.get("enabled", True):
            config = self._dict_to_config(user_id, config_dict)
            return await self._start_user_client(config)

        return True

    async def send_message(self, user_id: str, chat_id: str, content: str) -> bool:
        """Send a message through a user's Feishu bot."""
        client = self._channels.get(user_id)
        if not client:
            logger.warning(f"No Feishu client for user {user_id}")
            return False

        return await client.send_message(chat_id, content)

    def is_connected(self, user_id: str) -> bool:
        """Check if a user's Feishu bot is connected."""
        return user_id in self._channels and self._channels[user_id]._running


# Global instance
_feishu_channel_manager: Optional[FeishuChannelManager] = None


def get_feishu_channel_manager() -> FeishuChannelManager:
    """Get the global Feishu channel manager instance."""
    global _feishu_channel_manager
    if _feishu_channel_manager is None:
        _feishu_channel_manager = FeishuChannelManager()
    return _feishu_channel_manager


async def start_feishu_channels(message_handler=None) -> None:
    """Start the Feishu channel manager with all enabled user bots."""
    manager = get_feishu_channel_manager()
    manager._message_handler = message_handler
    await manager.start()


async def stop_feishu_channels() -> None:
    """Stop the Feishu channel manager."""
    global _feishu_channel_manager
    if _feishu_channel_manager:
        await _feishu_channel_manager.stop()
        _feishu_channel_manager = None
