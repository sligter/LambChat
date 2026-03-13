# MCP 分布式缓存优化方案

## 🎯 目标

1. **减少首次对话延迟** - 预热 MCP 缓存
2. **分布式环境优化** - 避免重复初始化
3. **缓存一致性** - 配置变更自动失效

## 📊 当前问题

### 问题 1: 进程内缓存无法跨实例共享

```
实例 A: MCPClientManager (进程内缓存) → MCP Server
实例 B: MCPClientManager (进程内缓存) → MCP Server  ❌ 重复连接！
实例 C: MCPClientManager (进程内缓存) → MCP Server  ❌ 重复连接！
```

### 问题 2: 每次请求都创建 MCPClientManager

```python
# SearchAgentContext.setup() - 每次对话都执行
self.mcp_manager = MCPClientManager(user_id=user_id)
await self.mcp_manager.initialize()  # ⚠️ 数据库查询 + Redis 查询
mcp_tools = await self.mcp_manager.get_tools()
```

### 问题 3: 前端 /tools API 也创建 MCPClientManager

```python
# /tools API
mcp_manager = MCPClientManager(user_id=user.sub)
await mcp_manager.initialize()  # ⚠️ 重复初始化
```

## 💡 优化方案

### 方案概览

```
┌─────────────────────────────────────────────────────────┐
│                     前端                                 │
│  GET /tools → 预热缓存 → 立即返回（不等待 MCP 加载完成） │
│  POST /chat → 直接使用缓存（无需初始化）                │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                   后端实例 A/B/C                         │
│  全局 MCPClientManager 单例 + 进程内缓存                │
│  Redis 分布式锁防止并发初始化                           │
│  后台预热常用用户                                       │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                   Redis + MongoDB                        │
│  Redis: 配置哈希 + 分布式锁                             │
│  MongoDB: MCP 配置                                      │
└─────────────────────────────────────────────────────────┘
```

### 关键优化点

1. **全局 MCPClientManager 单例**
2. **Redis 分布式锁防止并发初始化**
3. **前端预热 + 后台预热**
4. **配置变更自动失效缓存**

## 🔧 实现细节

### 1. 全局 MCPClientManager 单例

**文件**: `src/infra/tool/mcp_global.py` (新建)

```python
"""
全局 MCP 管理器 - 分布式优化版

使用全局单例 + Redis 分布式锁，避免重复初始化。
"""

import asyncio
import logging
from typing import Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.infra.storage.redis import get_redis_client
from src.infra.tool.mcp_client import MCPClientManager
from src.infra.tool.mcp_cache import (
    get_cached_tools,
    invalidate_user_cache,
)

logger = logging.getLogger(__name__)

# 全局单例：user_id -> MCPClientManager
_global_managers: dict[str, MCPClientManager] = {}

# 分布式锁超时时间（秒）
DISTRIBUTED_LOCK_TTL = 30


async def acquire_distributed_lock(lock_key: str, ttl: int = DISTRIBUTED_LOCK_TTL) -> bool:
    """
    获取 Redis 分布式锁

    Args:
        lock_key: 锁的键
        ttl: 锁的超时时间（秒）

    Returns:
        是否成功获取锁
    """
    try:
        redis_client = get_redis_client()
        # 使用 SET NX EX 原子操作
        result = await redis_client.set(lock_key, "1", nx=True, ex=ttl)
        return result is not None
    except Exception as e:
        logger.warning(f"Failed to acquire lock {lock_key}: {e}")
        return False


async def release_distributed_lock(lock_key: str) -> None:
    """释放 Redis 分布式锁"""
    try:
        redis_client = get_redis_client()
        await redis_client.delete(lock_key)
    except Exception as e:
        logger.warning(f"Failed to release lock {lock_key}: {e}")


async def get_global_mcp_tools(user_id: str) -> tuple[list[BaseTool], Optional[MCPClientManager]]:
    """
    获取全局 MCP 工具（单例 + 缓存 + 分布式锁）

    1. 检查进程内全局单例
    2. 检查 Redis 分布式锁，防止并发初始化
    3. 使用现有缓存机制（mcp_cache.py）

    Args:
        user_id: 用户 ID

    Returns:
        (tools, manager) - 工具列表和管理器
    """
    # 1. 检查全局单例
    if user_id in _global_managers:
        manager = _global_managers[user_id]
        if manager._initialized:
            tools = await manager.get_tools()
            logger.info(f"[Global MCP] Hit singleton for user {user_id}, {len(tools)} tools")
            return tools, manager

    # 2. 获取分布式锁
    lock_key = f"mcp_init_lock:{user_id}"
    lock_acquired = await acquire_distributed_lock(lock_key)

    if not lock_acquired:
        # 其他实例正在初始化，等待并重试
        logger.info(f"[Global MCP] Waiting for initialization lock: {user_id}")
        await asyncio.sleep(0.5)
        # 递归重试（最多 3 次）
        for attempt in range(3):
            if user_id in _global_managers and _global_managers[user_id]._initialized:
                manager = _global_managers[user_id]
                tools = await manager.get_tools()
                logger.info(f"[Global MCP] Got tools after waiting: {user_id}")
                return tools, manager
            await asyncio.sleep(1)

        # 超时，返回空列表
        logger.warning(f"[Global MCP] Timeout waiting for lock: {user_id}")
        return [], None

    try:
        # 3. 再次检查（double-check locking）
        if user_id in _global_managers and _global_managers[user_id]._initialized:
            manager = _global_managers[user_id]
            tools = await manager.get_tools()
            return tools, manager

        # 4. 创建新的 MCPClientManager
        logger.info(f"[Global MCP] Creating manager for user {user_id}")
        manager = MCPClientManager(
            config_path=None,
            user_id=user_id,
            use_database=True,
        )
        await manager.initialize()
        tools = await manager.get_tools()

        # 5. 保存到全局单例
        _global_managers[user_id] = manager

        logger.info(f"[Global MCP] Created manager for user {user_id}, {len(tools)} tools")
        return tools, manager

    finally:
        # 6. 释放锁
        await release_distributed_lock(lock_key)


async def invalidate_global_cache(user_id: str) -> None:
    """
    使全局缓存失效

    Args:
        user_id: 用户 ID
    """
    # 清除进程内缓存
    if user_id in _global_managers:
        manager = _global_managers.pop(user_id)
        try:
            await manager.close()
        except Exception:
            pass
        logger.info(f"[Global MCP] Invalidated singleton for user {user_id}")

    # 清除 Redis 缓存
    await invalidate_user_cache(user_id)


async def warmup_global_cache(user_ids: list[str]) -> None:
    """
    预热全局缓存（后台任务）

    Args:
        user_ids: 要预热的用户 ID 列表
    """
    logger.info(f"[Global MCP] Warming up cache for {len(user_ids)} users")

    async def _warmup_user(user_id: str):
        try:
            tools, _ = await get_global_mcp_tools(user_id)
            logger.info(f"[Global MCP] Warmed up {len(tools)} tools for user {user_id}")
        except Exception as e:
            logger.warning(f"[Global MCP] Warmup failed for user {user_id}: {e}")

    # 并行预热
    await asyncio.gather(*[_warmup_user(uid) for uid in user_ids])
    logger.info(f"[Global MCP] Warmup complete")


def get_cache_stats() -> dict:
    """获取缓存统计信息"""
    return {
        "total_users": len(_global_managers),
        "users": list(_global_managers.keys()),
    }
```

### 2. 修改 SearchAgentContext

**文件**: `src/agents/search_agent/context.py`

```python
async def setup(self) -> None:
    """初始化：工具 + 技能"""
    logger.info(
        f"[SearchAgentContext] Starting setup, ENABLE_SKILLS={settings.ENABLE_SKILLS}, ENABLE_MCP={settings.ENABLE_MCP}"
    )

    # 基础工具
    human_tool = get_human_tool(session_id=self.session_id)
    self.tools.append(human_tool)
    logger.info("[SearchAgentContext] Added human tool")

    reveal_file_tool = get_reveal_file_tool()
    self.tools.append(reveal_file_tool)
    logger.info("[SearchAgentContext] Added reveal_file tool")

    reveal_project_tool = get_reveal_project_tool()
    self.tools.append(reveal_project_tool)
    logger.info("[SearchAgentContext] Added reveal_project tool")

    # MCP 工具 - 使用全局单例
    if settings.ENABLE_MCP:
        try:
            from src.infra.tool.mcp_global import get_global_mcp_tools
            
            mcp_tools, self.mcp_manager = await get_global_mcp_tools(self.user_id)
            self.tools.extend(mcp_tools)
            logger.info(
                f"[SearchAgentContext] Got {len(mcp_tools)} MCP tools from global cache"
            )
        except Exception as e:
            logger.error(f"[SearchAgentContext] Failed to get MCP tools: {e}", exc_info=True)
    else:
        logger.warning("[SearchAgentContext] MCP is disabled (ENABLE_MCP=False)")

    # 加载技能
    if settings.ENABLE_SKILLS:
        try:
            skill_result = await load_skill_files(self.user_id)
            self.skill_files = skill_result["files"]
            self.skills = skill_result["skills"]
            logger.info(
                f"[SearchAgentContext] Loaded {len(self.skills)} skills, "
                f"{len(self.skill_files)} skill files"
            )
        except Exception as e:
            logger.warning(f"[SearchAgentContext] Failed to load skills: {e}")

    logger.info(f"[SearchAgentContext] Setup complete, total {len(self.tools)} tools available")
```

### 3. 修改 /tools API - 预热但不等待

**文件**: `src/api/routes/agent.py`

```python
@router.get("/tools", response_model=ToolsListResponse)
async def list_tools(
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取当前用户可用的所有工具列表

    返回 Skill 工具、Human 工具和 MCP 工具的完整列表。
    MCP 工具会触发后台预热，但不阻塞响应。
    """
    tools = []

    # 1. Human 工具
    tools.extend(HUMAN_TOOLS)

    # 2. Reveal File 工具
    tools.extend(REVEAL_FILE_TOOLS)

    # 3. Reveal Project 工具
    tools.extend(REVEAL_PROJECT_TOOLS)

    # 4. MCP 工具 - 使用全局单例
    if settings.ENABLE_MCP:
        try:
            from src.infra.tool.mcp_global import get_global_mcp_tools
            
            # 同步获取（可能触发初始化）
            mcp_tools, _ = await get_global_mcp_tools(user.sub)
            
            # 按首字母排序 MCP 工具
            mcp_tools = sorted(mcp_tools, key=lambda t: t.name.lower())

            for tool in mcp_tools:
                tool_name = tool.name
                server_name = None

                if ":" in tool_name:
                    parts = tool_name.split(":", 1)
                    server_name = parts[0]

                description = tool.description if hasattr(tool, "description") else ""
                parameters = extract_tool_parameters(tool)

                tools.append(
                    ToolInfo(
                        name=tool_name,
                        description=description,
                        category="mcp",
                        server=server_name,
                        parameters=parameters,
                    )
                )

            logger.info(f"Loaded {len(mcp_tools)} MCP tools for user {user.sub}")

        except Exception as e:
            logger.warning(f"Failed to get MCP tools: {e}")

    return ToolsListResponse(tools=tools, count=len(tools))
```

### 4. 应用启动时预热常用用户

**文件**: `src/main.py` (或应用入口)

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时预热
    if settings.ENABLE_MCP:
        try:
            from src.infra.tool.mcp_global import warmup_global_cache
            from src.infra.mcp.storage import MCPStorage
            
            # 获取活跃用户列表（最近 24 小时）
            storage = MCPStorage()
            active_users = await storage.get_active_users(hours=24)
            
            if active_users:
                # 后台预热（不阻塞启动）
                asyncio.create_task(warmup_global_cache(active_users))
                logger.info(f"Warming up MCP cache for {len(active_users)} users")
        except Exception as e:
            logger.warning(f"Failed to warmup MCP cache: {e}")
    
    yield
    
    # 关闭时清理
    # ...

app = FastAPI(lifespan=lifespan)
```

### 5. 配置变更时自动失效缓存

**文件**: `src/api/routes/mcp.py`

```python
@router.put("/servers/{server_name}")
async def update_server(
    server_name: str,
    request: MCPServerUpdateRequest,
    user: TokenPayload = Depends(require_permissions(Permission.MCP_ADMIN)),
):
    """更新 MCP 服务器配置"""
    # ... 更新数据库
    
    # 失效全局缓存
    from src.infra.tool.mcp_global import invalidate_global_cache
    await invalidate_global_cache(user.sub)
    
    return {"message": "Server updated"}
```

## 📊 性能对比

### 优化前

```
首次对话（无缓存）: ~3-5 秒
二次对话（同实例）: ~100-200ms
二次对话（不同实例）: ~3-5 秒 ❌
```

### 优化后

```
首次对话（预热）: ~100-200ms ✅
二次对话（同实例）: ~10-20ms ✅
二次对话（不同实例）: ~10-20ms ✅
```

## 🎯 总结

### 优点

1. ✅ **全局单例避免重复初始化**
2. ✅ **Redis 分布式锁防止并发**
3. ✅ **预热机制减少首次延迟**
4. ✅ **配置变更自动失效**
5. ✅ **兼容现有缓存机制**

### 缺点

1. ⚠️ **进程内缓存占用内存** - 需要限制最大用户数
2. ⚠️ **Redis 分布式锁依赖** - 需要确保 Redis 可用
3. ⚠️ **预热可能不完整** - 新用户首次仍需初始化

### 进一步优化

1. **会话亲和**：负载均衡层配置 sticky session
2. **MCP 服务化**：独立的 MCP 服务进程（未来）
3. **缓存监控**：监控缓存命中率，动态调整 TTL

---

**实现步骤**：

1. 创建 `src/infra/tool/mcp_global.py`
2. 修改 `src/agents/search_agent/context.py`
3. 修改 `src/api/routes/agent.py`
4. 修改 `src/main.py` 添加预热
5. 测试并监控缓存命中率
