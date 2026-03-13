"""
OpenViking 记忆工具

提供 4 个 LangChain 工具，让 Agent 主动管理记忆：
- search_memory: 语义搜索记忆和知识库
- save_memory: 显式保存记忆笔记
- browse_memory: 浏览记忆树（L0 摘要）
- read_knowledge: 读取特定资源的完整内容
"""

import logging
from typing import Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.kernel.config import settings

logger = logging.getLogger(__name__)


async def _get_client():
    """获取 OpenViking 客户端。"""
    from src.infra.openviking.client import get_openviking_client

    client = await get_openviking_client()
    if client is None:
        raise RuntimeError("OpenViking client not available")
    return client


def _get_user_id(runtime: Optional[ToolRuntime]) -> str:
    """从 ToolRuntime 中提取 user_id。"""
    if runtime and hasattr(runtime, "config") and isinstance(runtime.config, dict):
        configurable = runtime.config.get("configurable", {})
        context = configurable.get("context")
        if context and hasattr(context, "user_id") and context.user_id:
            return context.user_id
    return "default"


@tool
async def search_memory(
    query: str,
    limit: int = 5,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """搜索用户的记忆和知识库，返回与查询最相关的内容。

    当你需要回忆之前的对话、查找用户偏好、或检索相关知识时使用此工具。

    Args:
        query: 搜索查询，描述你想找的信息
        limit: 最大返回条数（默认 5）
    """
    if not settings.ENABLE_OPENVIKING:
        return "记忆系统未启用。"

    try:
        client = await _get_client()

        results = await client.find(query, limit=limit)
        if not results:
            return f"未找到与 '{query}' 相关的记忆。"

        sections = []
        for item in results:
            if isinstance(item, dict):
                uri = item.get("uri", item.get("path", ""))
                abstract = item.get("abstract", item.get("content", ""))
                score = item.get("score", 0)
                try:
                    score_str = f"{float(score):.2f}"
                except (TypeError, ValueError):
                    score_str = str(score)
                sections.append(f"[{uri}] (相关度: {score_str})\n{abstract}")
            elif isinstance(item, str):
                sections.append(item)

        return "\n\n---\n\n".join(sections) if sections else "未找到相关记忆。"

    except Exception as e:
        logger.warning("[OpenViking] search_memory failed: %s", e)
        return f"记忆搜索失败: {e}"


@tool
async def save_memory(
    content: str,
    category: str = "general",
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """将重要信息保存到用户的长期记忆中。

    当用户明确要求你记住某些信息，或你发现值得长期保存的关键信息时使用此工具。
    例如：用户偏好、重要决策、项目约定等。

    Args:
        content: 要保存的记忆内容
        category: 记忆分类（如 general, preference, decision, project）
    """
    if not settings.ENABLE_OPENVIKING:
        return "记忆系统未启用。"

    try:
        client = await _get_client()
        user_id = _get_user_id(runtime)

        uri = f"viking://user/{user_id}/memories/{category}"
        await client.add_resource(content, to=uri, wait=True)
        return f"已保存到 {category} 分类。"

    except Exception as e:
        logger.warning("[OpenViking] save_memory failed: %s", e)
        return f"保存记忆失败: {e}"


@tool
async def browse_memory(
    path: str = "/",
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """浏览用户的记忆树结构，查看有哪些记忆和知识资源。

    返回指定路径下的目录和文件列表（含 L0 摘要）。
    先用此工具了解记忆结构，再用 read_knowledge 读取具体内容。

    Args:
        path: 要浏览的路径（默认根目录 "/"）
    """
    if not settings.ENABLE_OPENVIKING:
        return "记忆系统未启用。"

    try:
        client = await _get_client()
        user_id = _get_user_id(runtime)

        # 构建 viking URI
        clean_path = path.strip("/")
        base = f"viking://user/{user_id}/memories"
        uri = f"{base}/{clean_path}" if clean_path else base

        items = await client.ls(uri, simple=True)
        if not items:
            return f"路径 {path} 下没有内容。"

        lines = []
        for item in items:
            if isinstance(item, dict):
                name = item.get("name", item.get("uri", ""))
                is_dir = item.get("is_dir", name.endswith("/") if name else False)
                abstract = item.get("abstract", "")
                prefix = "[DIR] " if is_dir else "[FILE]"
                line = f"{prefix} {name}"
                if abstract:
                    line += f"\n  → {abstract}"
                lines.append(line)
            elif isinstance(item, str):
                lines.append(f"  {item}")

        return "\n".join(lines) if lines else "目录为空。"

    except Exception as e:
        logger.warning("[OpenViking] browse_memory failed: %s", e)
        return f"浏览记忆失败: {e}"


@tool
async def read_knowledge(
    uri: str,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """读取特定记忆或知识资源的完整内容。

    当 search_memory 或 browse_memory 返回了感兴趣的 URI 后，
    使用此工具获取该资源的完整内容。

    Args:
        uri: 资源的 URI（如 viking://user/xxx/memories/general）
    """
    if not settings.ENABLE_OPENVIKING:
        return "记忆系统未启用。"

    try:
        client = await _get_client()
        content = await client.read(uri)
        if not content:
            return f"未找到内容: {uri}"
        return content

    except Exception as e:
        logger.warning("[OpenViking] read_knowledge failed: %s", e)
        return f"读取失败: {e}"


def get_openviking_tools() -> list[BaseTool]:
    """获取所有 OpenViking 记忆工具。"""
    if not settings.ENABLE_OPENVIKING:
        return []
    return [search_memory, save_memory, browse_memory, read_knowledge]
