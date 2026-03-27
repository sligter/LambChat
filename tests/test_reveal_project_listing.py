import os

import pytest

os.environ["DEBUG"] = "false"

from src.infra.tool.reveal_project_tool import _list_project_files, _upload_file


class _ExecuteResult:
    def __init__(self, output: str):
        self.output = output


class BackendWithRecursiveLsInfo:
    def __init__(self):
        self.tree = {
            "/home/user/personal-blog": [
                {"path": "/home/user/personal-blog/index.html", "is_dir": False},
                {"path": "/home/user/personal-blog/package.json", "is_dir": False},
                {"path": "/home/user/personal-blog/src", "is_dir": True},
            ],
            "/home/user/personal-blog/src": [
                {"path": "/home/user/personal-blog/src/main.jsx", "is_dir": False},
                {"path": "/home/user/personal-blog/src/App.jsx", "is_dir": False},
                {"path": "/home/user/personal-blog/src/pages", "is_dir": True},
            ],
            "/home/user/personal-blog/src/pages": [
                {"path": "/home/user/personal-blog/src/pages/Home.jsx", "is_dir": False},
            ],
        }

    def ls_info(self, path: str):
        return self.tree.get(path, [])

    async def aexecute(self, command: str):
        return _ExecuteResult(
            "/home/user/personal-blog/index.html\n/home/user/personal-blog/SPEC.md"
        )


class BackendWithPartialLsInfo:
    def ls_info(self, path: str):
        if path == "/home/user/personal-blog":
            return [
                {"path": "/home/user/personal-blog/index.html", "is_dir": False},
                {"path": "/home/user/personal-blog/src", "is_dir": True},
            ]
        if path == "/home/user/personal-blog/src":
            raise RuntimeError("transient ls failure")
        return []

    async def aexecute(self, command: str):
        return _ExecuteResult(
            "\n".join(
                [
                    "/home/user/personal-blog/index.html",
                    "/home/user/personal-blog/package.json",
                    "/home/user/personal-blog/src/main.jsx",
                ]
            )
        )


class DownloadBackend:
    async def adownload_files(self, paths: list[str]):
        class Response:
            def __init__(self, path: str, content: bytes | None, error: str | None = None):
                self.path = path
                self.content = content
                self.error = error

        return [Response(paths[0], b"", None)]


class StorageStub:
    class UploadResult:
        def __init__(self):
            self.key = "revealed_projects/personal-blog/file.css"
            self.size = 0
            self.content_type = "text/plain"

    async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
        assert data == b""
        return self.UploadResult()


@pytest.mark.asyncio
async def test_list_project_files_prefers_backend_file_api_over_partial_find_output():
    backend = BackendWithRecursiveLsInfo()

    files = await _list_project_files(backend, "/home/user/personal-blog")

    assert files == [
        "/home/user/personal-blog/index.html",
        "/home/user/personal-blog/package.json",
        "/home/user/personal-blog/src/App.jsx",
        "/home/user/personal-blog/src/main.jsx",
        "/home/user/personal-blog/src/pages/Home.jsx",
    ]


@pytest.mark.asyncio
async def test_list_project_files_falls_back_to_find_when_backend_listing_is_partial():
    backend = BackendWithPartialLsInfo()

    files = await _list_project_files(backend, "/home/user/personal-blog")

    assert files == [
        "/home/user/personal-blog/index.html",
        "/home/user/personal-blog/package.json",
        "/home/user/personal-blog/src/main.jsx",
    ]


@pytest.mark.asyncio
async def test_upload_file_keeps_empty_text_files():
    result = await _upload_file(
        StorageStub(),
        DownloadBackend(),
        "/home/user/personal-blog/src/empty.css",
        "/src/empty.css",
        "revealed_projects/personal-blog_12345678",
        "",
        semaphore=__import__("asyncio").Semaphore(1),
    )

    assert result == (
        "/src/empty.css",
        {
            "url": "/api/upload/file/revealed_projects/personal-blog/file.css",
            "is_binary": False,
            "size": 0,
        },
        None,
        None,
    )
