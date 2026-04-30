from __future__ import annotations

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    ExecuteResponse,
    FileData,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    WriteResult,
)
from deepagents.backends.protocol import (
    ReadResult as _UpstreamReadResult,
)


class ReadResult(str, _UpstreamReadResult):
    file_data: FileData | None
    error: str | None

    def __new__(
        cls,
        *,
        file_data: FileData | None = None,
        error: str | None = None,
        rendered_content: str | None = None,
    ) -> "ReadResult":
        if rendered_content is None:
            if error is not None:
                rendered_content = error if error.startswith("Error:") else f"Error: {error}"
            else:
                rendered_content = str((file_data or {}).get("content", ""))  # type: ignore[call-overload]

        obj = str.__new__(cls, rendered_content)
        obj.file_data = file_data
        obj.error = error
        return obj


# Re-export upstream protocol types so that mypy treats our aliases as
# identical to the ones used in BaseSandbox / BackendProtocol signatures.
__all__ = [
    "BackendProtocol",
    "EditResult",
    "ExecuteResponse",
    "FileDownloadResponse",
    "FileInfo",
    "FileUploadResponse",
    "GlobResult",
    "GrepMatch",
    "GrepResult",
    "LsResult",
    "ReadResult",
    "WriteResult",
]
