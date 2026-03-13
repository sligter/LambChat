"""
OpenViking 客户端管理

单例管理 AsyncHTTPClient 生命周期，在 FastAPI app startup/shutdown 中注册。
封装常用 API，提供类型安全的调用接口。
"""

import logging
from typing import Any, Optional

from src.kernel.config import settings

logger = logging.getLogger(__name__)

_client: Optional[Any] = None


class OpenVikingClient:
    """OpenViking 客户端封装，提供类型安全的 API。"""

    def __init__(self, inner_client: Any):
        self._client = inner_client

    def __getattr__(self, name: str) -> Any:
        """将未定义的方法代理到底层 client。"""
        return getattr(self._client, name)

    async def search(
        self,
        query: str,
        session_id: Optional[str] = None,
        target_uri: Optional[str] = None,
        limit: int = 10,
    ) -> Any:
        """
        智能检索：带意图分析 + session context。

        Args:
            query: 搜索查询
            session_id: OpenViking session ID（用于上下文感知）
            target_uri: 搜索范围限制
            limit: 返回结果数量

        Returns:
            FindResult 对象，包含 memories, resources, skills
        """
        kwargs: dict = {"query": query, "limit": limit}
        if session_id:
            kwargs["session_id"] = session_id
        if target_uri:
            kwargs["target_uri"] = target_uri

        return await self._client.search(**kwargs)

    async def find(
        self,
        query: str,
        target_uri: Optional[str] = None,
        limit: int = 10,
    ) -> Any:
        """
        简单检索：无 session context。

        Args:
            query: 搜索查询
            target_uri: 搜索范围限制
            limit: 返回结果数量

        Returns:
            FindResult 对象
        """
        kwargs: dict = {"query": query, "limit": limit}
        if target_uri:
            kwargs["target_uri"] = target_uri

        return await self._client.find(**kwargs)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: Optional[str] = None,
        parts: Optional[list] = None,
    ) -> None:
        """添加消息到 session。"""
        await self._client.add_message(session_id, role, content=content, parts=parts)

    async def create_session(self) -> dict:
        """创建新 session。"""
        return await self._client.create_session()

    async def commit_session(self, session_id: str) -> dict:
        """提交 session，触发记忆提取。"""
        return await self._client.commit_session(session_id)

    async def close(self) -> None:
        """关闭客户端连接。"""
        await self._client.close()


async def get_openviking_client() -> Optional[OpenVikingClient]:
    """
    获取 OpenViking 客户端单例（封装版）。

    首次调用时创建并初始化客户端。
    """
    global _client

    if _client is not None:
        return _client

    if not settings.ENABLE_OPENVIKING:
        return None

    try:
        from openviking import AsyncHTTPClient

        inner_client = AsyncHTTPClient(
            url=settings.OPENVIKING_URL,
            api_key=settings.OPENVIKING_API_KEY or None,
            agent_id=settings.OPENVIKING_AGENT_ID or None,
        )
        await inner_client.initialize()
        _client = OpenVikingClient(inner_client)
        logger.info("[OpenViking] Client initialized, url=%s", settings.OPENVIKING_URL)
        return _client
    except ImportError:
        logger.error("[OpenViking] openviking package not installed. Run: pip install openviking")
        return None
    except Exception as e:
        logger.error("[OpenViking] Failed to initialize client: %s", e)
        _client = None
        return None


async def close_openviking_client() -> None:
    """关闭 OpenViking 客户端连接。"""
    global _client

    if _client is not None:
        try:
            await _client.close()
            logger.info("[OpenViking] Client closed")
        except Exception as e:
            logger.warning("[OpenViking] Error closing client: %s", e)
        finally:
            _client = None
