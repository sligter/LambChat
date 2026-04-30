from __future__ import annotations

import pytest

from src.api.routes import health as health_routes


class _FakeMonitor:
    def get_summary(self) -> dict[str, object]:
        return {
            "available": True,
            "rss_bytes": 123 * 1024 * 1024,
            "vms_bytes": 456 * 1024 * 1024,
            "thread_count": 7,
            "open_file_count": 2,
            "history_size": 3,
            "suspected_leak": True,
            "growth_bytes": 77 * 1024 * 1024,
            "baseline_reset_at": "2026-04-30T12:05:00+00:00",
        }

    def get_diagnostics(self) -> dict[str, object]:
        return {
            "summary": self.get_summary(),
            "last_alert": {
                "captured_at": "2026-04-30T12:00:00+00:00",
                "top_growth": [
                    {"location": "src/leaky.py:88", "size_diff_bytes": 999 * 1024 * 1024}
                ],
                "top_allocations": [
                    {"location": "src/cache.py:21", "size_bytes": 222 * 1024 * 1024}
                ],
                "top_object_types": [{"type": "dict", "count": 4200}],
            },
        }


@pytest.mark.asyncio
async def test_health_route_returns_memory_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.health_check()

    assert response.status == "ok"
    assert response.memory is not None
    assert response.memory.rss_bytes == 123 * 1024 * 1024
    assert response.memory.suspected_leak is True


@pytest.mark.asyncio
async def test_memory_health_route_returns_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.memory_health_check()

    assert response["summary"]["rss_bytes"] == 123 * 1024 * 1024
    assert response["last_alert"]["top_growth"][0]["location"] == "src/leaky.py:88"


@pytest.mark.asyncio
async def test_memory_health_route_returns_human_readable_overview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.memory_health_check()

    assert response["overview"]["status"] == "suspected_leak"
    assert response["overview"]["rss"] == "123.0MB"
    assert response["overview"]["growth"] == "77.0MB"
    assert response["highlights"][0]["kind"] == "status"
    assert response["highlights"][0]["status"] == "suspected_leak"
    assert response["top_growth"][0]["size_diff"] == "999.0MB"
    assert response["top_allocations"][0]["size"] == "222.0MB"
    assert response["top_objects"][0]["label"] == "dict=4200"


@pytest.mark.asyncio
async def test_memory_health_route_returns_structured_highlights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.memory_health_check()

    assert response["highlights"] == [
        {
            "kind": "status",
            "status": "suspected_leak",
            "severity": "warning",
        },
        {
            "kind": "top_growth",
            "location": "src/leaky.py:88",
            "size_diff": "999.0MB",
        },
        {
            "kind": "top_allocation",
            "location": "src/cache.py:21",
            "size": "222.0MB",
        },
        {
            "kind": "top_object_type",
            "type": "dict",
            "count": 4200,
        },
    ]


@pytest.mark.asyncio
async def test_memory_health_route_returns_baseline_reset_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.memory_health_check()

    assert response["summary"]["baseline_reset_at"] == "2026-04-30T12:05:00+00:00"
