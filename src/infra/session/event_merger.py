"""
Event Merger - 事件合并器

定期合并 trace 中的流式事件，减少事件数量，提升前后端性能。

合并策略:
- 相同类型的连续流式事件（如 message:chunk, thinking）合并为一个完整事件
- 保留原始时间戳范围（started_at, ended_at）
- 合并后的事件标记为 merged=True
- 只合并已完成的 trace（status != "running"）

分布式支持:
- 使用 Redis 分布式锁确保只有一个实例执行合并任务
- 锁超时时间为合并间隔的 2 倍，防止死锁
- 使用 asyncio.timeout 防止单次合并操作超时
- 批量处理，每批最多处理 50 个 trace，避免长时间阻塞

性能优化:
- 非阻塞设计，合并任务在后台独立运行
- 超时保护，单次合并最多 4 分钟
- 批量处理，避免一次性处理过多数据
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings

logger = get_logger(__name__)

# 可合并的事件类型
MERGEABLE_EVENT_TYPES = frozenset(["message:chunk", "thinking"])

# Redis 分布式锁配置
MERGE_LOCK_KEY = "event_merger:lock"

# 单次合并超时时间（秒）- 设置为 4 分钟，留 1 分钟缓冲
MERGE_TIMEOUT = 240.0

# 每批处理的 trace 数量
BATCH_SIZE = 50

# 单批内并发合并的最大 trace 数量
_MERGE_CONCURRENCY = 10


def _get_merge_interval() -> float:
    """获取合并间隔"""
    return settings.EVENT_MERGE_INTERVAL


def _get_lock_timeout() -> int:
    """获取锁超时时间（合并间隔的 2 倍）"""
    return int(_get_merge_interval() * 2)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventMerger:
    """
    事件合并器

    定期扫描已完成的 trace，合并连续的流式事件。
    支持分布式环境，使用 Redis 分布式锁。

    特性:
    - 非阻塞设计，不影响主事件循环
    - 超时保护，防止卡死
    - 批量处理，避免长时间占用资源
    - 分布式锁，确保只有一个实例执行合并
    """

    def __init__(self, trace_storage):
        self.trace_storage = trace_storage
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._redis = get_redis_client()
        self._lock_value: Optional[str] = None  # 锁的唯一标识

    def start(self):
        """启动后台合并任务"""
        if self._running:
            return
        self._running = True
        self._redis = get_redis_client()
        self._task = asyncio.create_task(self._merge_loop())
        self._task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        logger.info("EventMerger started with distributed lock support")

    async def stop(self):
        """停止后台合并任务，等待当前操作完成"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("EventMerger stopped")

    async def _merge_loop(self):
        """后台合并循环 - 非阻塞设计"""
        while self._running:
            try:
                # 等待到下一个合并时间点
                await asyncio.sleep(_get_merge_interval())

                # 尝试获取分布式锁
                if await self._acquire_lock():
                    try:
                        # 使用 asyncio.timeout 防止合并操作超时
                        async with asyncio.timeout(MERGE_TIMEOUT):
                            await self._merge_completed_traces()
                    except TimeoutError:
                        logger.warning(
                            f"Merge operation timed out after {MERGE_TIMEOUT}s, will retry next round"
                        )
                    except Exception as e:
                        logger.error(f"Merge operation failed: {e}", exc_info=True)
                    finally:
                        # 确保释放锁
                        await self._release_lock()
                else:
                    logger.debug(
                        "Failed to acquire merge lock (another instance is merging), skipping this round"
                    )
            except asyncio.CancelledError:
                logger.info("EventMerger loop cancelled, shutting down gracefully")
                break
            except Exception as e:
                logger.error(f"EventMerger loop error: {e}", exc_info=True)
                # 发生错误后等待一段时间再继续
                await asyncio.sleep(60)

    async def _acquire_lock(self) -> bool:
        """
        获取分布式锁

        使用 SET NX EX 原子操作获取锁，并生成唯一的锁标识。
        这样可以确保只有持有锁的实例才能释放锁。
        """
        if not self._redis:
            return True  # 如果没有 Redis，直接执行

        try:
            import uuid

            # 生成唯一的锁标识
            self._lock_value = str(uuid.uuid4())

            # 使用 SET NX EX 原子操作获取锁
            result = await self._redis.set(
                MERGE_LOCK_KEY,
                self._lock_value,
                ex=_get_lock_timeout(),
                nx=True,
            )

            if result:
                logger.debug(f"Acquired merge lock with value: {self._lock_value[:8]}...")
                return True
            else:
                logger.debug("Lock already held by another instance")
                return False

        except Exception as e:
            logger.warning(f"Failed to acquire lock: {e}")
            return False

    async def _release_lock(self):
        """
        释放分布式锁

        使用 Lua 脚本确保只有持有锁的实例才能释放锁，避免误删其他实例的锁。
        """
        if not self._redis or not self._lock_value:
            return

        try:
            # 使用 Lua 脚本原子性地检查并删除锁
            # 只有当锁的值匹配时才删除
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """

            # 执行 Lua 脚本
            result = await self._redis.eval(lua_script, 1, MERGE_LOCK_KEY, self._lock_value)  # type: ignore[misc]

            if result == 1:
                logger.debug(f"Released merge lock with value: {self._lock_value[:8]}...")
            else:
                logger.debug("Lock was already released or taken by another instance")

            self._lock_value = None

        except Exception as e:
            logger.warning(f"Failed to release lock: {e}")
            self._lock_value = None

    async def _merge_completed_traces(self):
        """
        合并已完成的 traces - 批量处理，避免阻塞

        使用批量处理策略：
        1. 每批最多处理 BATCH_SIZE 个 trace
        2. 每批之间 yield 控制权，避免阻塞事件循环
        3. 使用 asyncio.gather 并发处理单个 trace
        """
        try:
            collection = self.trace_storage.collection

            # 查询最近完成的 traces（未合并的）
            # 使用投影减少数据传输
            cursor = collection.find(
                {
                    "status": {"$ne": "running"},
                    "metadata.merged": {"$ne": True},
                },
                {"trace_id": 1, "events": 1},
            ).limit(BATCH_SIZE)

            traces = await cursor.to_list(length=BATCH_SIZE)

            if not traces:
                logger.debug("No traces to merge")
                return

            logger.info(f"Found {len(traces)} traces to merge")

            # 批量处理 traces
            merge_tasks = []
            for trace in traces:
                trace_id = trace.get("trace_id")
                events = trace.get("events", [])

                if not events:
                    continue

                # 创建合并任务（不立即执行）
                task = self._merge_single_trace(trace_id, events)
                merge_tasks.append(task)

            # 并发执行所有合并任务，但限制并发数
            if merge_tasks:
                # 使用 Semaphore 限制并发，避免 MongoDB 突发压力
                sem = asyncio.Semaphore(_MERGE_CONCURRENCY)

                async def _limited(coro):
                    async with sem:
                        return await coro

                limited_tasks = [_limited(t) for t in merge_tasks]
                results = await asyncio.gather(*limited_tasks, return_exceptions=True)

                # 统计结果
                success_count = sum(1 for r in results if r is True)
                error_count = sum(1 for r in results if isinstance(r, Exception))

                logger.info(
                    f"Merge batch completed: {success_count} succeeded, {error_count} failed, "
                    f"{len(results) - success_count - error_count} skipped"
                )

        except Exception as e:
            logger.error(f"Failed to merge completed traces: {e}", exc_info=True)

    async def _merge_single_trace(self, trace_id: str, events: List[Dict[str, Any]]) -> bool:
        """
        合并单个 trace 的事件

        Args:
            trace_id: Trace ID
            events: 事件列表

        Returns:
            是否合并成功
        """
        try:
            # 合并事件
            merged_events = self._merge_events(events)

            # 如果事件数量减少了，更新数据库
            if len(merged_events) < len(events):
                collection = self.trace_storage.collection
                now = _utc_now()
                result = await collection.update_one(
                    {"trace_id": trace_id},
                    {
                        "$set": {
                            "events": merged_events,
                            "event_count": len(merged_events),
                            "metadata.merged": True,
                            "metadata.merged_at": now,
                            "updated_at": now,
                        }
                    },
                )

                if result.modified_count > 0:
                    logger.debug(
                        f"Merged trace {trace_id}: {len(events)} -> {len(merged_events)} events "
                        f"(reduced {len(events) - len(merged_events)} events)"
                    )
                    return True
                else:
                    logger.warning(f"Failed to update trace {trace_id} in database")
                    return False
            else:
                # 没有可合并的事件，标记为已检查
                collection = self.trace_storage.collection
                now = _utc_now()
                await collection.update_one(
                    {"trace_id": trace_id},
                    {
                        "$set": {
                            "metadata.merged": True,
                            "metadata.merged_at": now,
                        }
                    },
                )
                logger.debug(f"Trace {trace_id} has no events to merge")
                return False

        except Exception as e:
            logger.error(f"Failed to merge trace {trace_id}: {e}")
            return False

    def _merge_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并事件列表

        策略:
        - 相同类型的连续事件合并为一个
        - 保留第一个事件的时间戳作为 started_at
        - 保留最后一个事件的时间戳作为 ended_at
        - 合并 content 字段
        """
        if not events:
            return []

        merged = []
        current_group: List[Dict[str, Any]] = []
        current_type: Optional[str] = None

        for event in events:
            event_type = event.get("event_type")
            data = event.get("data", {})

            # 检查是否可以合并
            if event_type in MERGEABLE_EVENT_TYPES:
                # 检查是否与当前组相同类型且相同 agent_id/depth
                if current_type == event_type and current_group:
                    # 检查 agent_id 和 depth 是否一致
                    last_data = current_group[-1].get("data", {})
                    if (
                        data.get("agent_id") == last_data.get("agent_id")
                        and data.get("depth") == last_data.get("depth")
                        and data.get("thinking_id") == last_data.get("thinking_id")
                    ):
                        # 可以合并
                        current_group.append(event)
                        continue

                # 不能合并，先处理当前组
                if current_group:
                    merged.append(self._merge_group(current_group))

                # 开始新组
                current_group = [event]
                current_type = event_type
            else:
                # 不可合并的事件类型，先处理当前组
                if current_group:
                    merged.append(self._merge_group(current_group))
                    current_group = []
                    current_type = None

                # 直接添加
                merged.append(event)

        # 处理最后一组
        if current_group:
            merged.append(self._merge_group(current_group))

        return merged

    def _merge_group(self, group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        合并一组事件

        Args:
            group: 相同类型的连续事件列表

        Returns:
            合并后的事件
        """
        if len(group) == 1:
            return group[0]

        # 提取公共字段
        first = group[0]
        last = group[-1]
        event_type = first.get("event_type")

        # 合并 content
        contents = []
        for event in group:
            data = event.get("data", {})
            content = data.get("content", "")
            if content:
                contents.append(content)

        merged_content = "".join(contents)

        # 构建合并后的事件
        merged_data = first.get("data", {}).copy()
        merged_data["content"] = merged_content
        merged_data["merged"] = True
        merged_data["merged_count"] = len(group)
        merged_data["started_at"] = first.get("timestamp")
        merged_data["ended_at"] = last.get("timestamp")

        return {
            "event_type": event_type,
            "data": merged_data,
            "timestamp": first.get("timestamp"),  # 使用第一个事件的时间戳
        }


# Singleton
_event_merger: Optional[EventMerger] = None


def get_event_merger(trace_storage) -> EventMerger:
    """获取 EventMerger 单例"""
    global _event_merger
    if _event_merger is None:
        _event_merger = EventMerger(trace_storage)
    return _event_merger
