"""
OpenViking Backend

实现 deepagents BackendProtocol，将文件系统操作代理到 OpenViking HTTP API。

路径映射：
- /memories/xxx → viking://user/{user_id}/memories/xxx
- /resources/xxx → viking://resources/xxx
"""

import asyncio
import logging
import threading
from typing import Any

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在同步上下文中安全地运行异步协程。"""
    try:
        asyncio.get_running_loop()
        result = None
        exception = None

        def run_in_thread():
            nonlocal result, exception
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                new_loop.close()
            except Exception as e:
                exception = e

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        if exception:
            raise exception
        return result
    except RuntimeError:
        return asyncio.run(coro)


# CompositeBackend 路由时会去掉前缀（如 /memories/），
# 这里需要重新映射到 viking:// URI
MEMORIES_PREFIX = "/memories/"
RESOURCES_PREFIX = "/resources/"


class OpenVikingBackend(BackendProtocol):
    """
    OpenViking 存储后端

    将 deepagents 文件系统操作代理到 OpenViking HTTP API。
    支持 /memories/ 和 /resources/ 两个路由前缀。
    """

    def __init__(
        self,
        user_id: str,
        route_prefix: str = "/memories/",
        runtime: Any = None,
    ):
        self._user_id = user_id
        self._route_prefix = route_prefix
        self._runtime = runtime

    def _to_viking_uri(self, path: str) -> str:
        """将内部路径转换为 viking:// URI。"""
        # 清理路径
        if not path or path == "/":
            path = ""
        path = path.strip("/")

        if self._route_prefix == MEMORIES_PREFIX:
            base = f"viking://user/{self._user_id}/memories"
        elif self._route_prefix == RESOURCES_PREFIX:
            base = "viking://resources"
        else:
            base = f"viking://user/{self._user_id}"

        if path:
            return f"{base}/{path}"
        return base

    async def _get_client(self):
        """获取 OpenViking 客户端。"""
        from src.infra.openviking.client import get_openviking_client

        client = await get_openviking_client()
        if client is None:
            raise RuntimeError("OpenViking client not available")
        return client

    def _format_content(self, content: str, offset: int = 0, limit: int = 2000) -> str:
        """格式化内容为带行号的格式。"""
        lines = content.split("\n")
        start = offset
        end = min(offset + limit, len(lines))
        result_lines = []
        for i in range(start, end):
            line_content = lines[i]
            if len(line_content) > 2000:
                line_content = line_content[:2000] + "..."
            result_lines.append(f"{i + 1:6d}\t{line_content}")
        return "\n".join(result_lines)

    # ==========================================
    # 读取
    # ==========================================

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return _run_async(self.aread(file_path, offset, limit))

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        uri = self._to_viking_uri(file_path)
        try:
            client = await self._get_client()
            content = await client.read(uri)
            return self._format_content(content, offset, limit)
        except Exception as e:
            logger.error("[OpenViking] read %s failed: %s", uri, e)
            return f"Error: {e}"

    # ==========================================
    # 写入
    # ==========================================

    def write(self, file_path: str, content: str) -> WriteResult:
        return _run_async(self.awrite(file_path, content))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        uri = self._to_viking_uri(file_path)
        try:
            client = await self._get_client()
            # 确保父目录存在
            parent_uri = "/".join(uri.split("/")[:-1])
            if parent_uri and parent_uri != uri:
                try:
                    await client.mkdir(parent_uri)
                except Exception:
                    pass  # 目录可能已存在
            # 使用 add_resource 写入文本内容到指定 URI
            await client.add_resource(content, to=uri, wait=True)
            return WriteResult(path=file_path, files_update=None)
        except Exception as e:
            logger.error("[OpenViking] write %s failed: %s", uri, e)
            return WriteResult(error=str(e))

    # ==========================================
    # 编辑
    # ==========================================

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return _run_async(self.aedit(file_path, old_string, new_string, replace_all))

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(
            error="Edit is not supported for OpenViking backend. Use read() to view content."
        )

    # ==========================================
    # 列表
    # ==========================================

    def ls_info(self, path: str) -> list[FileInfo]:
        return _run_async(self.als_info(path))

    async def als_info(self, path: str) -> list[FileInfo]:
        uri = self._to_viking_uri(path)
        try:
            client = await self._get_client()
            items = await client.ls(uri, simple=True)
            entries: list[FileInfo] = []
            for item in items:
                if isinstance(item, dict):
                    item_path = item.get("name", item.get("uri", "")) or ""
                    is_dir = item.get("is_dir", item_path.endswith("/"))
                    size = item.get("size", 0)
                elif isinstance(item, str):
                    item_path = item
                    is_dir = item.endswith("/")
                    size = 0
                else:
                    continue
                # 返回相对路径（不含 viking:// 前缀）
                name = item_path.rstrip("/").split("/")[-1] if item_path else ""
                if is_dir:
                    entries.append(FileInfo(path=f"/{name}/", is_dir=True))
                else:
                    entries.append(FileInfo(path=f"/{name}", is_dir=False, size=size))
            return entries
        except Exception as e:
            logger.error("[OpenViking] ls %s failed: %s", uri, e)
            return []

    # ==========================================
    # 搜索
    # ==========================================

    def grep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> list[GrepMatch] | str:
        return _run_async(self.agrep_raw(pattern, path, glob))

    async def agrep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> list[GrepMatch] | str:
        uri = self._to_viking_uri(path or "/")
        try:
            client = await self._get_client()
            results = await client.grep(uri, pattern)
            if isinstance(results, str):
                return results
            matches = []
            for r in results:
                if isinstance(r, dict):
                    matches.append(
                        GrepMatch(
                            path=r.get("path", ""),
                            line=r.get("line", 0),
                            text=r.get("text", ""),
                        )
                    )
            return matches
        except Exception as e:
            logger.error("[OpenViking] grep %s failed: %s", uri, e)
            return f"Error: {e}"

    # ==========================================
    # Glob
    # ==========================================

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return _run_async(self.aglob_info(pattern, path))

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        uri = self._to_viking_uri(path)
        try:
            client = await self._get_client()
            results = await client.glob(pattern, uri)
            entries: list[FileInfo] = []
            for item in results:
                if isinstance(item, dict):
                    item_path = item.get("uri", item.get("path", "")) or ""
                    is_dir = item.get("is_dir", False)
                elif isinstance(item, str):
                    item_path = item
                    is_dir = item.endswith("/")
                else:
                    continue
                name = item_path.rstrip("/").split("/")[-1]
                entries.append(FileInfo(path=f"/{name}", is_dir=is_dir))
            return entries
        except Exception as e:
            logger.error("[OpenViking] glob %s failed: %s", uri, e)
            return []

    # ==========================================
    # 批量操作
    # ==========================================

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return _run_async(self.adownload_files(paths))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        results = []
        for path in paths:
            try:
                client = await self._get_client()
                uri = self._to_viking_uri(path)
                content = await client.read(uri)
                content_bytes = (
                    content.encode("utf-8") if isinstance(content, str) else content
                )
                results.append(
                    FileDownloadResponse(path=path, content=content_bytes, error=None)
                )
            except Exception:
                results.append(
                    FileDownloadResponse(
                        path=path, content=None, error="file_not_found"
                    )
                )
        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return _run_async(self.aupload_files(files))

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        results = []
        for path, content in files:
            content_str = (
                content.decode("utf-8") if isinstance(content, bytes) else content
            )
            result = await self.awrite(path, content_str)
            if result.error:
                results.append(FileUploadResponse(path=path, error="permission_denied"))
            else:
                results.append(FileUploadResponse(path=path, error=None))
        return results

    def close(self) -> None:
        pass


def create_openviking_backend(
    user_id: str,
    route_prefix: str = "/memories/",
    runtime: Any = None,
) -> OpenVikingBackend:
    """创建 OpenViking Backend 实例。"""
    return OpenVikingBackend(
        user_id=user_id, route_prefix=route_prefix, runtime=runtime
    )
