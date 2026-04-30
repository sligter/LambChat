from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_monitor_marks_suspicious_growth_when_rss_keeps_rising() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    rss_values = iter([100 * 1024 * 1024, 150 * 1024 * 1024, 230 * 1024 * 1024])
    diagnostics_calls: list[int] = []

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=64 * 1024 * 1024,
        min_samples_for_alert=3,
        alert_cooldown_seconds=0.0,
    )

    def _fake_process_sample() -> dict[str, int]:
        return {
            "rss_bytes": next(rss_values),
            "vms_bytes": 400 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 3,
        }

    def _fake_capture_diagnostics() -> dict[str, object]:
        diagnostics_calls.append(1)
        return {
            "top_growth": [{"location": "src/example.py:10", "size_diff_bytes": 1024}],
            "top_allocations": [{"location": "src/example.py:10", "size_bytes": 2048}],
            "top_object_types": [{"type": "dict", "count": 42}],
        }

    monitor._collect_process_sample = _fake_process_sample  # type: ignore[method-assign]
    monitor._capture_diagnostics_snapshot = _fake_capture_diagnostics  # type: ignore[method-assign]

    await monitor._sample_once()
    await monitor._sample_once()
    await monitor._sample_once()

    summary = monitor.get_summary()
    diagnostics = monitor.get_diagnostics()

    assert summary["suspected_leak"] is True
    assert summary["growth_bytes"] == 130 * 1024 * 1024
    assert diagnostics_calls == [1]
    assert diagnostics["last_alert"]["top_growth"][0]["location"] == "src/example.py:10"


@pytest.mark.asyncio
async def test_monitor_logs_hotspot_summary_when_alert_fires(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    rss_values = iter([100 * 1024 * 1024, 150 * 1024 * 1024, 230 * 1024 * 1024])

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=64 * 1024 * 1024,
        min_samples_for_alert=3,
        alert_cooldown_seconds=0.0,
    )

    def _fake_process_sample() -> dict[str, int]:
        return {
            "rss_bytes": next(rss_values),
            "vms_bytes": 400 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 3,
        }

    def _fake_capture_diagnostics() -> dict[str, object]:
        return {
            "top_growth": [{"location": "src/leaky.py:88", "size_diff_bytes": 64 * 1024 * 1024}],
            "top_allocations": [{"location": "src/cache.py:21", "size_bytes": 32 * 1024 * 1024}],
            "top_object_types": [{"type": "dict", "count": 4200}],
        }

    monitor._collect_process_sample = _fake_process_sample  # type: ignore[method-assign]
    monitor._capture_diagnostics_snapshot = _fake_capture_diagnostics  # type: ignore[method-assign]

    with caplog.at_level("WARNING", logger="src.infra.monitoring.memory"):
        await monitor._sample_once()
        await monitor._sample_once()
        await monitor._sample_once()

    assert "src/leaky.py:88" in caplog.text
    assert "src/cache.py:21" in caplog.text
    assert "dict=4200" in caplog.text


@pytest.mark.asyncio
async def test_monitor_summary_reports_not_available_before_sampling() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor()

    assert monitor.get_summary()["available"] is False


@pytest.mark.asyncio
async def test_reset_baseline_reanchors_growth_window() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(interval_seconds=60.0, history_limit=10)

    first_timestamp = datetime(2026, 4, 30, 3, 20, tzinfo=timezone.utc)
    samples = iter(
        [
            {
                "timestamp": first_timestamp,
                "rss_bytes": 100 * 1024 * 1024,
                "vms_bytes": 400 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 3,
            },
            {
                "timestamp": first_timestamp + timedelta(minutes=1),
                "rss_bytes": 180 * 1024 * 1024,
                "vms_bytes": 420 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 3,
            },
            {
                "timestamp": first_timestamp + timedelta(minutes=2),
                "rss_bytes": 210 * 1024 * 1024,
                "vms_bytes": 430 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 3,
            },
        ]
    )

    monitor._collect_process_sample = lambda: next(samples)  # type: ignore[method-assign]

    await monitor._sample_once()
    await monitor._sample_once()

    assert monitor.get_summary()["growth_bytes"] == 80 * 1024 * 1024

    monitor.reset_baseline()
    summary = monitor.get_summary()

    assert summary["growth_bytes"] == 0
    assert summary["history_size"] == 1
    assert summary["baseline_reset_at"] == first_timestamp + timedelta(minutes=2)


@pytest.mark.asyncio
async def test_reset_baseline_clears_previous_alert_state() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(interval_seconds=60.0, history_limit=10)
    reset_timestamp = datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc)

    monitor._collect_process_sample = lambda: {
        "timestamp": reset_timestamp,
        "rss_bytes": 220 * 1024 * 1024,
        "vms_bytes": 440 * 1024 * 1024,
        "thread_count": 12,
        "open_file_count": 4,
    }  # type: ignore[method-assign]
    monitor._last_alert = {"captured_at": "2026-04-30T03:24:00+00:00"}
    monitor._last_alert_at = reset_timestamp - timedelta(minutes=1)

    monitor.reset_baseline()

    diagnostics = monitor.get_diagnostics()

    assert diagnostics["last_alert"] is None
    assert diagnostics["summary"]["baseline_reset_at"] == reset_timestamp


def test_get_diagnostics_skips_live_snapshot_when_refresh_is_false() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(interval_seconds=60.0, history_limit=10)
    monitor._history.append(
        {
            "timestamp": datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc),
            "rss_bytes": 220 * 1024 * 1024,
            "vms_bytes": 440 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 4,
        }
    )
    called = False

    def _capture() -> dict[str, object]:
        nonlocal called
        called = True
        return {"captured_at": "2026-04-30T03:26:00+00:00"}

    monitor._capture_diagnostics_snapshot = _capture  # type: ignore[method-assign]

    diagnostics = monitor.get_diagnostics(refresh=False)

    assert diagnostics["current_snapshot"] is None
    assert called is False


def test_get_diagnostics_refreshes_live_snapshot_when_requested() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(interval_seconds=60.0, history_limit=10)
    monitor._history.append(
        {
            "timestamp": datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc),
            "rss_bytes": 220 * 1024 * 1024,
            "vms_bytes": 440 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 4,
        }
    )

    monitor._capture_diagnostics_snapshot = lambda: {  # type: ignore[method-assign]
        "captured_at": "2026-04-30T03:26:00+00:00"
    }

    diagnostics = monitor.get_diagnostics(refresh=True)

    assert diagnostics["current_snapshot"] == {"captured_at": "2026-04-30T03:26:00+00:00"}
