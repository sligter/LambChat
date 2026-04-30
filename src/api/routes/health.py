"""
健康检查路由
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.deps import require_permissions
from src.infra.monitoring import get_memory_monitor
from src.kernel.config import settings
from src.kernel.schemas.agent import HealthResponse, MemoryHealthSummary

router = APIRouter()


def _format_mb(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{round(value / 1024 / 1024, 2)}MB"


def _build_memory_overview(summary: dict) -> dict:
    status = "unavailable"
    if summary.get("available"):
        status = "suspected_leak" if summary.get("suspected_leak") else "stable"

    return {
        "status": status,
        "rss": _format_mb(summary.get("rss_bytes")),
        "vms": _format_mb(summary.get("vms_bytes")),
        "growth": _format_mb(summary.get("growth_bytes")),
        "threads": summary.get("thread_count"),
        "open_files": summary.get("open_file_count"),
        "history_size": summary.get("history_size"),
        "last_sample_at": summary.get("last_sample_at"),
    }


def _build_highlight_items(summary: dict, last_alert: dict | None) -> list[dict]:
    if not summary.get("available"):
        reason = summary.get("reason", "unknown")
        return [{"kind": "unavailable", "reason": reason}]

    highlights = [
        {
            "kind": "status",
            "status": "suspected_leak" if summary.get("suspected_leak") else "stable",
        }
    ]
    if summary.get("suspected_leak"):
        highlights[0]["severity"] = "warning"
    else:
        highlights[0]["severity"] = "info"

    growth_rows = (last_alert or {}).get("top_growth") or []
    if growth_rows:
        top = growth_rows[0]
        highlights.append(
            {
                "kind": "top_growth",
                "location": top["location"],
                "size_diff": _format_mb(top["size_diff_bytes"]) or "N/A",
            }
        )

    allocation_rows = (last_alert or {}).get("top_allocations") or []
    if allocation_rows:
        top = allocation_rows[0]
        highlights.append(
            {
                "kind": "top_allocation",
                "location": top["location"],
                "size": _format_mb(top["size_bytes"]) or "N/A",
            }
        )

    object_rows = (last_alert or {}).get("top_object_types") or []
    if object_rows:
        top = object_rows[0]
        highlights.append(
            {
                "kind": "top_object_type",
                "type": top["type"],
                "count": top["count"],
            }
        )

    return highlights


def _format_growth_rows(rows: list[dict] | None) -> list[dict]:
    return [
        {
            **row,
            "size_diff": _format_mb(row.get("size_diff_bytes")),
        }
        for row in (rows or [])
    ]


def _format_allocation_rows(rows: list[dict] | None) -> list[dict]:
    return [
        {
            **row,
            "size": _format_mb(row.get("size_bytes")),
        }
        for row in (rows or [])
    ]


def _format_object_rows(rows: list[dict] | None) -> list[dict]:
    return [
        {
            **row,
            "label": f"{row['type']}={row['count']}",
        }
        for row in (rows or [])
    ]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查"""
    summary = await get_memory_monitor().get_summary()
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        memory=MemoryHealthSummary.model_validate(summary),
    )


@router.get("/ready")
async def readiness_check():
    """就绪检查"""
    return {"status": "ready"}


@router.get("/health/memory")
async def memory_health_check(
    refresh: bool = False,
    _=Depends(require_permissions("settings:manage")),
):
    """详细内存诊断"""
    diagnostics = await get_memory_monitor().get_diagnostics(refresh=refresh)
    summary = diagnostics.get("summary", {})
    last_alert = diagnostics.get("last_alert") or diagnostics.get("current_snapshot") or {}

    return {
        **diagnostics,
        "overview": _build_memory_overview(summary),
        "highlights": _build_highlight_items(summary, last_alert),
        "top_growth": _format_growth_rows(last_alert.get("top_growth")),
        "top_allocations": _format_allocation_rows(last_alert.get("top_allocations")),
        "top_objects": _format_object_rows(last_alert.get("top_object_types")),
    }
