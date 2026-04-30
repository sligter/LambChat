"""Process memory monitoring and diagnostics."""

from __future__ import annotations

import asyncio
import gc
import os
import tracemalloc
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Any

from src.infra.logging import get_logger
from src.kernel.config import settings

try:
    import psutil
except ImportError:  # pragma: no cover - dependency is expected to be installed
    psutil = None

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_trace_location(trace: tracemalloc.Frame) -> str:
    return f"{trace.filename}:{trace.lineno}"


def _format_bytes_as_mb(value: int) -> str:
    return f"{round(value / 1024 / 1024, 2)}MB"


class MemoryMonitor:
    """Background process memory sampler with on-demand diagnostics."""

    def __init__(
        self,
        *,
        interval_seconds: float | None = None,
        history_limit: int | None = None,
        leak_threshold_bytes: int | None = None,
        min_samples_for_alert: int | None = None,
        alert_cooldown_seconds: float | None = None,
        traceback_limit: int | None = None,
        top_stats_limit: int | None = None,
        gc_object_limit: int | None = None,
    ) -> None:
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else settings.MEMORY_MONITOR_INTERVAL_SECONDS
        )
        self.history_limit = (
            history_limit if history_limit is not None else settings.MEMORY_MONITOR_HISTORY_LIMIT
        )
        self.leak_threshold_bytes = (
            leak_threshold_bytes
            if leak_threshold_bytes is not None
            else settings.MEMORY_MONITOR_LEAK_THRESHOLD_MB * 1024 * 1024
        )
        self.min_samples_for_alert = (
            min_samples_for_alert
            if min_samples_for_alert is not None
            else settings.MEMORY_MONITOR_MIN_SAMPLES
        )
        self.alert_cooldown_seconds = (
            alert_cooldown_seconds
            if alert_cooldown_seconds is not None
            else settings.MEMORY_MONITOR_ALERT_COOLDOWN_SECONDS
        )
        self.traceback_limit = (
            traceback_limit
            if traceback_limit is not None
            else settings.MEMORY_MONITOR_TRACEBACK_LIMIT
        )
        self.top_stats_limit = (
            top_stats_limit
            if top_stats_limit is not None
            else settings.MEMORY_MONITOR_TOP_STATS_LIMIT
        )
        self.gc_object_limit = (
            gc_object_limit
            if gc_object_limit is not None
            else settings.MEMORY_MONITOR_GC_OBJECT_LIMIT
        )

        self._history: deque[dict[str, Any]] = deque(maxlen=max(1, self.history_limit))
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._process = psutil.Process(os.getpid()) if psutil is not None else None
        self._baseline_snapshot: tracemalloc.Snapshot | None = None
        self._baseline_reset_at: datetime | None = None
        self._started_tracemalloc = False
        self._last_alert: dict[str, Any] | None = None
        self._last_alert_at: datetime | None = None
        self._last_error: str | None = None

    async def start(self) -> None:
        """Start the background monitor if enabled."""
        if self._running or not settings.MEMORY_MONITOR_ENABLED:
            return
        self._running = True

        if psutil is None:
            self._last_error = "psutil is not installed"
            logger.warning("[MemoryMonitor] psutil is unavailable; monitoring disabled")
            return

        if not tracemalloc.is_tracing():
            tracemalloc.start(self.traceback_limit)
            self._started_tracemalloc = True

        self.reset_baseline()
        self._task = asyncio.create_task(self._run_loop())
        self._task.add_done_callback(
            lambda task: task.exception() if not task.cancelled() else None
        )
        logger.info(
            "[MemoryMonitor] started interval=%ss threshold=%sMB",
            self.interval_seconds,
            round(self.leak_threshold_bytes / 1024 / 1024, 2),
        )

    async def stop(self) -> None:
        """Stop the background monitor."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._started_tracemalloc and tracemalloc.is_tracing():
            tracemalloc.stop()
            self._started_tracemalloc = False

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                await self._sample_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive logging path
                self._last_error = str(exc)
                logger.warning("[MemoryMonitor] sampling failed: %s", exc, exc_info=True)

    async def _sample_once(self) -> None:
        sample = self._collect_process_sample()
        sample.setdefault("timestamp", _utc_now())
        self._history.append(sample)

        if self._is_suspicious_growth(sample["timestamp"]):
            now = sample["timestamp"]
            if self._should_emit_alert(now):
                self._last_alert = self._capture_diagnostics_snapshot()
                self._last_alert_at = now
                logger.warning(
                    "[MemoryMonitor] suspicious memory growth detected rss=%s growth=%s top_growth=%s top_allocations=%s top_objects=%s",
                    _format_bytes_as_mb(sample["rss_bytes"]),
                    _format_bytes_as_mb(self._growth_bytes()),
                    self._format_growth_summary(self._last_alert),
                    self._format_allocation_summary(self._last_alert),
                    self._format_object_summary(self._last_alert),
                )

    def _collect_process_sample(self) -> dict[str, Any]:
        if self._process is None:
            raise RuntimeError("psutil process is unavailable")

        memory = self._process.memory_info()
        try:
            open_file_count = self._process.num_fds()  # type: ignore[attr-defined]
        except (AttributeError, NotImplementedError):
            open_file_count = len(self._process.open_files())

        return {
            "timestamp": _utc_now(),
            "rss_bytes": int(memory.rss),
            "vms_bytes": int(memory.vms),
            "thread_count": int(self._process.num_threads()),
            "open_file_count": int(open_file_count),
        }

    def _capture_diagnostics_snapshot(self) -> dict[str, Any]:
        return {
            "captured_at": _utc_now().isoformat(),
            "top_growth": self._build_growth_stats(),
            "top_allocations": self._build_allocation_stats(),
            "top_object_types": self._build_object_type_stats(),
        }

    def reset_baseline(self) -> None:
        """Re-anchor growth tracking to the current process state."""
        sample = self._collect_process_sample()
        sample.setdefault("timestamp", _utc_now())

        if tracemalloc.is_tracing():
            try:
                self._baseline_snapshot = tracemalloc.take_snapshot()
            except RuntimeError:
                self._baseline_snapshot = None
        else:
            self._baseline_snapshot = None

        self._baseline_reset_at = sample["timestamp"]
        self._history = deque([sample], maxlen=max(1, self.history_limit))
        self._last_alert = None
        self._last_alert_at = None

    def _format_growth_summary(self, diagnostics: dict[str, Any] | None) -> str:
        if not diagnostics:
            return "none"
        rows = diagnostics.get("top_growth") or []
        if not rows:
            return "none"
        return ", ".join(
            f"{row['location']} (+{_format_bytes_as_mb(int(row['size_diff_bytes']))})"
            for row in rows[:3]
        )

    def _format_allocation_summary(self, diagnostics: dict[str, Any] | None) -> str:
        if not diagnostics:
            return "none"
        rows = diagnostics.get("top_allocations") or []
        if not rows:
            return "none"
        return ", ".join(
            f"{row['location']} ({_format_bytes_as_mb(int(row['size_bytes']))})" for row in rows[:3]
        )

    def _format_object_summary(self, diagnostics: dict[str, Any] | None) -> str:
        if not diagnostics:
            return "none"
        rows = diagnostics.get("top_object_types") or []
        if not rows:
            return "none"
        return ", ".join(f"{row['type']}={int(row['count'])}" for row in rows[:3])

    def _build_growth_stats(self) -> list[dict[str, Any]]:
        if self._baseline_snapshot is None or not tracemalloc.is_tracing():
            return []

        snapshot = tracemalloc.take_snapshot()
        growth_stats = snapshot.compare_to(self._baseline_snapshot, "lineno")
        rows: list[dict[str, Any]] = []

        for stat in growth_stats:
            if stat.size_diff <= 0:
                continue
            rows.append(
                {
                    "location": _format_trace_location(stat.traceback[0]),
                    "size_diff_bytes": int(stat.size_diff),
                    "count_diff": int(stat.count_diff),
                }
            )
            if len(rows) >= self.top_stats_limit:
                break

        return rows

    def _build_allocation_stats(self) -> list[dict[str, Any]]:
        if not tracemalloc.is_tracing():
            return []

        snapshot = tracemalloc.take_snapshot()
        rows: list[dict[str, Any]] = []

        for stat in snapshot.statistics("lineno")[: self.top_stats_limit]:
            rows.append(
                {
                    "location": _format_trace_location(stat.traceback[0]),
                    "size_bytes": int(stat.size),
                    "count": int(stat.count),
                }
            )

        return rows

    def _build_object_type_stats(self) -> list[dict[str, Any]]:
        counts = Counter(type(obj).__name__ for obj in gc.get_objects())
        return [
            {"type": object_type, "count": count}
            for object_type, count in counts.most_common(self.gc_object_limit)
        ]

    def _growth_bytes(self) -> int:
        if len(self._history) < 2:
            return 0
        return int(self._history[-1]["rss_bytes"] - self._history[0]["rss_bytes"])

    def _is_suspicious_growth(self, sampled_at: datetime) -> bool:
        del sampled_at
        if len(self._history) < self.min_samples_for_alert:
            return False

        growth_bytes = self._growth_bytes()
        if growth_bytes < self.leak_threshold_bytes:
            return False

        rss_series = [sample["rss_bytes"] for sample in self._history]
        return all(current >= previous for previous, current in zip(rss_series, rss_series[1:]))

    def _should_emit_alert(self, now: datetime) -> bool:
        if self._last_alert_at is None:
            return True
        elapsed = (now - self._last_alert_at).total_seconds()
        return elapsed >= self.alert_cooldown_seconds

    def get_summary(self) -> dict[str, Any]:
        if not settings.MEMORY_MONITOR_ENABLED:
            return {"available": False, "reason": "disabled"}

        if psutil is None:
            return {
                "available": False,
                "reason": "psutil_unavailable",
                "last_error": self._last_error,
            }

        if not self._history:
            return {"available": False, "reason": "no_samples", "last_error": self._last_error}

        latest = self._history[-1]
        return {
            "available": True,
            "rss_bytes": latest["rss_bytes"],
            "vms_bytes": latest["vms_bytes"],
            "thread_count": latest["thread_count"],
            "open_file_count": latest["open_file_count"],
            "history_size": len(self._history),
            "growth_bytes": self._growth_bytes(),
            "suspected_leak": self._is_suspicious_growth(latest["timestamp"]),
            "sample_interval_seconds": self.interval_seconds,
            "baseline_reset_at": self._baseline_reset_at,
            "last_sample_at": latest["timestamp"],
            "last_error": self._last_error,
        }

    def get_diagnostics(self, refresh: bool = False) -> dict[str, Any]:
        diagnostics = {
            "summary": self.get_summary(),
            "last_alert": self._last_alert,
            "last_error": self._last_error,
            "current_snapshot": self._last_alert,
        }

        if refresh and self._history:
            diagnostics["current_snapshot"] = self._capture_diagnostics_snapshot()

        return diagnostics


_memory_monitor: MemoryMonitor | None = None


def get_memory_monitor() -> MemoryMonitor:
    global _memory_monitor
    if _memory_monitor is None:
        _memory_monitor = MemoryMonitor()
    return _memory_monitor
