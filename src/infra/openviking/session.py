"""
OpenViking Session 生命周期管理

将 LambChat 会话映射到 OpenViking session，
在会话结束时 commit 触发自动记忆提取。

设计原则：
- Session 贯穿整个 LambChat 会话，不频繁重建
- 只在 LambChat session 结束时 commit（触发 OpenViking 自动记忆提取）
- 同 session 内使用 search() 智能检索，利用对话上下文
- 跨 session 记忆通过 find() 检索用户的 memories

支持 Redis 振久化映射（分布式部署），回退到进程内缓存。
"""

import logging
from typing import Any, Optional

from src.kernel.config import settings

logger = logging.getLogger(__name__)

# Redis key for session mapping hash
_REDIS_KEY = "openviking:sessions"

# 进程内缓存（Redis 不可用时的回退）
_local_cache: dict[str, str] = {}

# Redis 客户端缓存（避免每次 ping）
_redis_client = None
_redis_checked = False


async def _get_redis():
    """获取 Redis 客户端，缓存连接状态避免重复 ping。"""
    global _redis_client, _redis_checked

    if _redis_checked:
        return _redis_client

    try:
        from src.infra.storage.redis import get_redis_client

        client = get_redis_client()
        await client.ping()  # type: ignore[misc]
        _redis_client = client
        _redis_checked = True
        return client
    except Exception:
        _redis_checked = True
        _redis_client = None
        return None


async def _get_mapping(lambchat_session_id: str) -> Optional[str]:
    """从 Redis 或本地缓存获取映射。"""
    # 先查本地缓存（快路径）
    if lambchat_session_id in _local_cache:
        return _local_cache[lambchat_session_id]

    # 尝试 Redis
    redis = await _get_redis()
    if redis:
        try:
            ov_id = await redis.hget(_REDIS_KEY, lambchat_session_id)
            if ov_id:
                _local_cache[lambchat_session_id] = ov_id
                return ov_id
        except Exception as e:
            logger.debug("[OpenViking] Redis hget failed: %s", e)

    return None


async def _set_mapping(lambchat_session_id: str, ov_session_id: str) -> None:
    """写入映射到 Redis + 本地缓存。"""
    _local_cache[lambchat_session_id] = ov_session_id

    redis = await _get_redis()
    if redis:
        try:
            await redis.hset(_REDIS_KEY, lambchat_session_id, ov_session_id)
        except Exception as e:
            logger.debug("[OpenViking] Redis hset failed: %s", e)


async def _del_mapping(lambchat_session_id: str) -> Optional[str]:
    """删除映射，返回被删除的 ov_session_id。"""
    ov_session_id = _local_cache.pop(lambchat_session_id, None)

    redis = await _get_redis()
    if redis:
        try:
            stored = await redis.hget(_REDIS_KEY, lambchat_session_id)
            if stored:
                ov_session_id = ov_session_id or stored
                await redis.hdel(_REDIS_KEY, lambchat_session_id)
        except Exception as e:
            logger.debug("[OpenViking] Redis hdel failed: %s", e)

    return ov_session_id


async def ensure_ov_session(
    lambchat_session_id: str,
    user_id: str,
) -> Optional[str]:
    """
    确保 LambChat 会话有对应的 OpenViking session。

    首次调用时创建 OV session 并缓存映射关系（Redis + 本地）。
    """
    if not settings.ENABLE_OPENVIKING:
        return None

    # 检查已有映射
    existing = await _get_mapping(lambchat_session_id)
    if existing:
        return existing

    try:
        from src.infra.openviking.client import get_openviking_client

        client = await get_openviking_client()
        if client is None:
            return None

        result = await client.create_session()
        ov_session_id = result.get("session_id")
        if ov_session_id:
            await _set_mapping(lambchat_session_id, ov_session_id)
            logger.info(
                "[OpenViking] Session created: %s → %s",
                lambchat_session_id,
                ov_session_id,
            )
        return ov_session_id

    except Exception as e:
        logger.warning(
            "[OpenViking] Failed to create session: %s: %s",
            type(e).__name__,
            e,
        )
        return None


def _extract_message_content(message: Any) -> str:
    """
    从 LangChain 消息中提取文本内容。

    Args:
        message: LangChain 消息对象

    Returns:
        str: 消息的文本内容
    """
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    # 处理 content 是列表的情况（多模态消息）
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return "\n".join(text_parts)
    return str(content) if content else ""


def _format_tool_message(message: Any) -> str:
    """
    将 ToolMessage 格式化为可读文本。

    Args:
        message: ToolMessage 对象

    Returns:
        str: 格式化后的文本
    """
    content = _extract_message_content(message)
    tool_name = getattr(message, "name", "") or getattr(message, "tool_name", "")
    if tool_name:
        return f"[Tool: {tool_name}]\n{content}"
    return f"[Tool]\n{content}"


async def sync_messages(
    ov_session_id: str,
    messages: list[Any],
    lambchat_session_id: Optional[str] = None,
) -> None:
    """
    将消息列表同步到 OpenViking session。

    支持同步多种类型的 LangChain 消息：
    - HumanMessage -> user role
    - AIMessage -> assistant role
    - ToolMessage -> assistant role (带工具标识)

    注意：不再自动 commit，session 保持连续性。
    记忆提取在 LambChat session 结束时通过 commit_ov_session() 触发。

    Args:
        ov_session_id: OpenViking session ID
        messages: LangChain 消息列表
        lambchat_session_id: LambChat session ID（用于日志）
    """
    if not settings.ENABLE_OPENVIKING or not ov_session_id or not messages:
        return

    try:
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        from src.infra.openviking.client import get_openviking_client

        client = await get_openviking_client()
        if client is None:
            return

        synced_count = 0
        for msg in messages:
            content = ""
            role = ""

            if isinstance(msg, HumanMessage):
                content = _extract_message_content(msg)
                if content:
                    role = "user"
                    await client.add_message(ov_session_id, "user", content=content)
                    synced_count += 1

            elif isinstance(msg, AIMessage):
                # AIMessage 可能包含 tool_calls，优先同步最终文本内容
                content = _extract_message_content(msg)
                if content:
                    role = "assistant"
                    await client.add_message(ov_session_id, "assistant", content=content)
                    synced_count += 1

            elif isinstance(msg, ToolMessage):
                # ToolMessage 作为 assistant 的工具调用结果
                content = _format_tool_message(msg)
                if content:
                    role = "tool"
                    await client.add_message(ov_session_id, "assistant", content=content)
                    synced_count += 1

            # 打印每条消息的摘要（前 80 字符）
            if content and role:
                preview = content[:80].replace("\n", " ")
                logger.debug(
                    "[OpenViking] Sync [%s]: %s%s",
                    role,
                    preview,
                    "..." if len(content) > 80 else "",
                )

        logger.info(
            "[OpenViking] Synced %d/%d messages to session %s",
            synced_count,
            len(messages),
            ov_session_id,
        )

    except Exception as e:
        # 忽略关闭时的预期错误（event loop 已关闭）
        msg = str(e).lower()
        if "event loop is closed" in msg or "event loop stopped" in msg:
            logger.debug("[OpenViking] Sync skipped during shutdown")
        else:
            logger.warning(
                "[OpenViking] Failed to sync messages: %s: %s",
                type(e).__name__,
                e,
            )


async def commit_and_rotate_session(
    lambchat_session_id: str,
    user_id: str,
    synced_messages_count: int = 0,
) -> Optional[str]:
    """
    提交当前 OpenViking session 并创建新的 session。

    用于定期触发记忆提取，避免 session 过长导致记忆提取延迟。
    旧的 session 被 commit 后，新的 session 立即创建并映射。

    Args:
        lambchat_session_id: LambChat session ID
        user_id: 用户 ID（用于创建新 session）
        synced_messages_count: 本轮同步的消息数量（用于日志）

    Returns:
        新的 OpenViking session ID，失败返回 None
    """
    if not settings.ENABLE_OPENVIKING:
        return None

    # 获取并删除旧映射
    old_ov_session_id = await _del_mapping(lambchat_session_id)

    if old_ov_session_id:
        try:
            from src.infra.openviking.client import get_openviking_client

            client = await get_openviking_client()
            if client:
                await client.commit_session(old_ov_session_id)
                logger.info(
                    "[OpenViking] Session committed (rotated): %s | synced %d messages | triggering memory extraction",
                    old_ov_session_id,
                    synced_messages_count,
                )
        except Exception as e:
            logger.warning(
                "[OpenViking] Failed to commit old session: %s: %s",
                type(e).__name__,
                e,
            )

    # 创建新的 OV session
    new_ov_session_id = await ensure_ov_session(lambchat_session_id, user_id)

    if new_ov_session_id and old_ov_session_id:
        logger.info(
            "[OpenViking] Session rotated: %s → %s",
            old_ov_session_id[:8] + "...",
            new_ov_session_id[:8] + "...",
        )

    return new_ov_session_id


async def commit_ov_session(lambchat_session_id: str) -> None:
    """
    提交 OpenViking session，触发自动记忆提取。

    在 LambChat session 关闭/删除时调用。
    """
    if not settings.ENABLE_OPENVIKING:
        return

    ov_session_id = await _del_mapping(lambchat_session_id)
    if not ov_session_id:
        return

    try:
        from src.infra.openviking.client import get_openviking_client

        client = await get_openviking_client()
        if client is None:
            return

        await client.commit_session(ov_session_id)
        logger.info(
            "[OpenViking] Session committed: %s (memories extracted)",
            ov_session_id,
        )

    except Exception as e:
        # 忽略关闭时的错误（event loop 已关闭）
        msg = str(e).lower()
        if "event loop is closed" in msg or "event loop stopped" in msg:
            logger.debug("[OpenViking] Session commit skipped during shutdown")
        else:
            logger.warning(
                "[OpenViking] Failed to commit session: %s: %s",
                type(e).__name__,
                e,
            )
