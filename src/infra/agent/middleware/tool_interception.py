"""Tool call interception middleware — MCP quota, deferred tool search, binary upload."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import shlex
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from src.infra.tool.deferred_manager import DeferredToolManager

from src.infra.agent.middleware._helpers import (
    _append_system_text_blocks,
    _tool_sort_key,
)
from src.kernel.config import settings

logger = logging.getLogger(__name__)


# MCP content block types that may carry binary data
_BINARY_BLOCK_TYPES = frozenset(("image", "file"))

# Binary file extensions — read_file should upload these to S3 instead of returning garbled text
_BINARY_EXTENSIONS = frozenset(
    (
        # Images
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".ico",
        ".svg",
        ".avif",
        ".tiff",
        ".tif",
        # Videos
        ".mp4",
        ".webm",
        ".mov",
        ".avi",
        ".wmv",
        ".mkv",
        ".ogv",
        # Audio
        ".mp3",
        ".wav",
        ".ogg",
        ".aac",
        ".flac",
        ".m4a",
        ".opus",
        # Documents
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
    )
)


# ---------------------------------------------------------------------------
# MCP Quota Middleware
# ---------------------------------------------------------------------------


def _extract_mcporter_call_target(command: str) -> str | None:
    """Extract the target from a mcporter call command."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    for index, token in enumerate(tokens):
        if token == "mcporter" and index + 2 < len(tokens) and tokens[index + 1] == "call":
            return tokens[index + 2]
        if "mcporter call " in token:
            nested = _extract_mcporter_call_target(token)
            if nested:
                return nested
    return None


def _server_from_mcporter_target(target: str) -> str | None:
    for separator in (".", ":"):
        if separator in target:
            server = target.split(separator, 1)[0]
            return server or None
    return target or None


class MCPQuotaMiddleware(AgentMiddleware):
    """Enforce quotas for sandbox MCP calls routed through execute/mcporter."""

    def __init__(self, *, user_id: str | None) -> None:
        super().__init__()
        self._user_id = user_id

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        tool_name = request.tool_call.get("name", "")
        tool_args = request.tool_call.get("args", {})
        if tool_name != "execute" or not isinstance(tool_args, dict):
            return await handler(request)

        command = tool_args.get("command")
        if not isinstance(command, str):
            return await handler(request)

        target = _extract_mcporter_call_target(command)
        server_name = _server_from_mcporter_target(target) if target else None
        if not server_name:
            return await handler(request)

        from src.infra.mcp.quota import (
            check_and_consume_system_mcp_quota,
            quota_error_json,
        )

        quota_result = await check_and_consume_system_mcp_quota(
            user_id=self._user_id,
            server_name=server_name,
        )
        if quota_result.allowed:
            return await handler(request)

        return ToolMessage(
            content=quota_error_json(server_name, quota_result),
            tool_call_id=request.tool_call.get("id", ""),
            name=tool_name,
        )


# ---------------------------------------------------------------------------
# Tool Result Binary Middleware
# ---------------------------------------------------------------------------


class ToolResultBinaryMiddleware(AgentMiddleware):
    """Upload base64 binary data and replace with URL before sending ToolMessage to LLM.

    Handles two scenarios:
    1. MCP tools returning image/file type base64 data → upload and replace with URL
    2. read_file tool reading binary files → download and upload to S3, return file link
    """

    def __init__(self, *, base_url: str = "") -> None:
        super().__init__()
        self._base_url = base_url

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        tool_name = request.tool_call.get("name", "")
        tool_args = request.tool_call.get("args", {})

        # --- read_file binary interception ---
        if tool_name == "read_file":
            file_path = tool_args.get("file_path", "") if isinstance(tool_args, dict) else ""
            if file_path and self._is_binary_file(file_path):
                uploaded = await self._handle_read_file_binary(request, file_path)
                if uploaded is not None:
                    return uploaded

        result = await handler(request)

        # Only process ToolMessage results
        if not isinstance(result, ToolMessage):
            return result

        content = result.content
        if not isinstance(content, list):
            return result

        # Quick check: any base64 blocks?
        if not any(
            isinstance(b, dict) and b.get("base64") and b.get("type") in _BINARY_BLOCK_TYPES
            for b in content
        ):
            return result

        # Upload and replace base64 with URL, keeping original block structure
        new_blocks: list[str | dict[str, Any]] = []
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("base64")
                and block.get("type") in _BINARY_BLOCK_TYPES
            ):
                url = await self._upload_block(block)
                if url:
                    # Keep original structure, replace base64 with url
                    new_block = {k: v for k, v in block.items() if k != "base64"}
                    new_block["url"] = url
                    new_blocks.append(new_block)
                else:
                    new_blocks.append(block)
            else:
                new_blocks.append(block)

        return ToolMessage(
            content=new_blocks,
            tool_call_id=result.tool_call_id,
            name=getattr(result, "name", None),
            status=getattr(result, "status", None),
            artifact=getattr(result, "artifact", None),
        )

    @staticmethod
    def _is_binary_file(file_path: str) -> bool:
        """Check if a file path has a binary extension."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in _BINARY_EXTENSIONS

    async def _handle_read_file_binary(self, request: Any, file_path: str) -> ToolMessage | None:
        """Download a binary file from the sandbox, upload to S3, return URL info."""
        try:
            from src.infra.storage.s3.service import get_or_init_storage
            from src.infra.tool.backend_utils import get_backend_from_runtime

            backend = get_backend_from_runtime(request.runtime)
            if backend is None:
                return None

            # Download from sandbox backend
            file_bytes: bytes | None = None
            if hasattr(backend, "adownload_files"):
                try:
                    responses = await backend.adownload_files([file_path])
                    if responses and responses[0].content:
                        file_bytes = responses[0].content
                except Exception:
                    pass

            if file_bytes is None and hasattr(backend, "download_files"):
                try:
                    responses = await asyncio.to_thread(backend.download_files, [file_path])
                    if responses and responses[0].content:
                        file_bytes = responses[0].content
                except Exception:
                    pass

            if file_bytes is None:
                return None

            # Upload to storage
            storage = await get_or_init_storage()
            filename = file_path.rsplit("/", 1)[-1]
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            upload_result = await storage.upload_bytes(
                data=file_bytes,
                folder="revealed_files",
                filename=filename,
                content_type=mime_type,
            )

            base_url = self._base_url or getattr(settings, "APP_BASE_URL", "").rstrip("/")
            proxy_url = (
                f"{base_url}/api/upload/file/{upload_result.key}"
                if base_url
                else f"/api/upload/file/{upload_result.key}"
            )

            result_data = json.dumps(
                {
                    "key": upload_result.key,
                    "url": proxy_url,
                    "name": filename,
                    "mime_type": upload_result.content_type or mime_type,
                    "size": len(file_bytes),
                    "_meta": {
                        "path": file_path,
                        "source": "read_file_binary_upload",
                    },
                },
                ensure_ascii=False,
            )

            logger.info(
                "read_file binary upload: %s → %s (%d bytes)",
                file_path,
                upload_result.key,
                len(file_bytes),
            )

            return ToolMessage(
                content=result_data,
                tool_call_id=request.tool_call.get("id", ""),
                name="read_file",
            )
        except Exception as e:
            logger.warning("read_file binary upload failed: %s", e)
            return None

    async def _upload_block(self, block: dict) -> str | None:
        """Upload a single binary block to storage, return the access URL."""
        try:
            from src.infra.storage.s3.service import get_or_init_storage

            storage = await get_or_init_storage()
        except Exception as e:
            logger.warning("Failed to initialize storage for binary upload: %s", e)
            return None

        b64_data = block.get("base64")
        if not b64_data or not isinstance(b64_data, str):
            return None

        try:
            raw_bytes = base64.b64decode(b64_data)
            mime_type = block.get("mime_type", "application/octet-stream")
            ext = mimetypes.guess_extension(mime_type) or ".bin"
            ext = ext.lstrip(".")
            filename = f"binary_{uuid.uuid4().hex[:8]}.{ext}"

            upload_result = await storage.upload_bytes(
                data=raw_bytes,
                folder="tool_binaries",
                filename=filename,
                content_type=mime_type,
            )

            base_url = self._base_url
            if not base_url:
                base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")

            url = (
                f"{base_url}/api/upload/file/{upload_result.key}"
                if base_url
                else f"/api/upload/file/{upload_result.key}"
            )
            logger.info(
                "Middleware uploaded binary block: %s (%d bytes)", upload_result.key, len(raw_bytes)
            )
            return url
        except Exception as e:
            logger.warning("Failed to upload binary block in middleware: %s", e)
            return None


# ---------------------------------------------------------------------------
# Deferred Tool Search Middleware
# ---------------------------------------------------------------------------


class ToolSearchMiddleware(AgentMiddleware):
    """Deferred tool loading middleware — manages on-demand MCP tool discovery and dynamic injection.

    Two core hooks:

    * ``awrap_model_call`` — before each LLM call:
      1. Injects the undiscovered deferred tool name list into the system prompt tail
      2. Injects ``search_tools`` tool + discovered tool schemas into ``request.tools``

    * ``awrap_tool_call`` — during tool execution:
      If the tool name is in the discovered set but not in the ToolNode registry,
      execute directly and return ToolMessage (factory skips validation for these tools).
    """

    def __init__(
        self,
        *,
        deferred_manager: "DeferredToolManager",
        search_limit: int = 10,
    ) -> None:
        super().__init__()
        self._deferred_manager = deferred_manager
        self._search_limit = search_limit

        # Lazy init for search_tools (avoid importing potentially missing modules in __init__)
        self._search_tool: "BaseTool | None" = None

    def _get_search_tool(self) -> "BaseTool":
        """Lazily create search_tools tool instance."""
        if self._search_tool is None:
            from src.infra.tool.tool_search_tool import ToolSearchTool

            self._search_tool = ToolSearchTool(
                manager=self._deferred_manager,
                search_limit=self._search_limit,
            )
        return self._search_tool

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        """Inject deferred tool prompt and dynamic tool schemas."""
        # 1. Inject deferred tool name list + discovered tool state (uses manager's dirty flag cache)
        prompt_sections = self._deferred_manager.get_deferred_prompt_blocks()
        if prompt_sections:
            new_system_message = _append_system_text_blocks(request.system_message, prompt_sections)
            request = request.override(system_message=new_system_message)

        # 2. Inject search_tools itself and discovered tools (ensures sub-agents share the same dynamic loading path)
        search_tool = self._get_search_tool()
        discovered = self._deferred_manager.get_discovered_tools()
        existing_names = {
            t.name if hasattr(t, "name") else t.get("name", "") for t in request.tools
        }
        new_tools = []
        if search_tool.name not in existing_names:
            new_tools.append(search_tool)
        new_tools.extend(t for t in discovered if t.name not in existing_names)
        if new_tools:
            combined = list(request.tools) + sorted(new_tools, key=_tool_sort_key)
            request = request.override(tools=combined)

        return await handler(request)

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Intercept deferred tool and search_tools calls, execute directly.

        Handles two tool types:
        1. search_tools — search and discover deferred tools (may not be registered in ToolNode)
        2. Discovered deferred MCP tools — execute directly and return ToolMessage
        """
        tool_name = request.tool_call.get("name", "")

        # Handle search_tools call (safety net: even if registered to ToolNode, no side effects)
        search_tool = self._get_search_tool()
        if tool_name == search_tool.name and request.tool is None:
            try:
                args = request.tool_call.get("args", {})
                result = await search_tool.ainvoke(args)
                content = (
                    result
                    if isinstance(result, str)
                    else json.dumps(result, ensure_ascii=False, default=str)
                )
                return ToolMessage(
                    content=content,
                    tool_call_id=request.tool_call.get("id", ""),
                    name=tool_name,
                )
            except Exception as e:
                logger.warning(
                    "[ToolSearchMiddleware] Error executing search_tools: %s", e, exc_info=True
                )
                return ToolMessage(
                    content=f"Error executing tool {tool_name}: {e}",
                    tool_call_id=request.tool_call.get("id", ""),
                    name=tool_name,
                    status="error",
                )

        # Check if it's a discovered deferred tool
        if self._deferred_manager.is_discovered(tool_name) and request.tool is None:
            tool = self._deferred_manager.get_tool(tool_name)
            if tool is not None:
                try:
                    args = request.tool_call.get("args", {})
                    result = await tool.ainvoke(args)

                    # MCP tools with response_format="content_and_artifact"
                    # ainvoke() returns tuple (content, artifact), need to unpack
                    if isinstance(result, tuple) and len(result) == 2:
                        result = result[0]

                    # MCP content blocks ([{"type":"text","text":"..."}]) passed directly as list,
                    # preserving ToolMessage.content str | list[dict] format
                    if isinstance(result, list):
                        msg_content: str | list[Any] = result
                    elif isinstance(result, str):
                        msg_content = result
                    elif isinstance(result, dict):
                        msg_content = json.dumps(result, ensure_ascii=False, default=str)
                    elif result is not None:
                        msg_content = str(result)
                    else:
                        msg_content = ""

                    return ToolMessage(
                        content=msg_content,
                        tool_call_id=request.tool_call.get("id", ""),
                        name=tool_name,
                    )
                except Exception as e:
                    logger.warning(
                        "[ToolSearchMiddleware] Error executing discovered tool %s: %s",
                        tool_name,
                        e,
                        exc_info=True,
                    )
                    return ToolMessage(
                        content=f"Error executing tool {tool_name}: {e}",
                        tool_call_id=request.tool_call.get("id", ""),
                        name=tool_name,
                        status="error",
                    )

        # Non-deferred tool, pass through to original handler
        return await handler(request)
