# Distributed Memory Health Design

## Goal

Make `/api/health/memory` useful in multi-instance deployments.

Today the endpoint only exposes diagnostics from the current Python process. After this change, the endpoint should still work for single-instance deployments, but in distributed deployments it should expose cluster-aware memory health by aggregating per-instance diagnostics that are published through shared Redis infrastructure.

The first version should prioritize operational safety and backward compatibility over perfectly synchronous cross-instance refresh.

## Problem Summary

`MemoryMonitor` is intentionally process-local. Its sampling history, leak baseline, tracemalloc snapshot, and object counts all describe one Python worker only:

- `_history`
- `_last_alert`
- `_baseline_snapshot`
- `_baseline_reset_at`

That is correct for collection, but it means `/health/memory` currently answers "what does this instance look like right now?" rather than "what does the deployment look like right now?"

In a multi-instance deployment this creates two operational problems:

- the UI can miss a leaking instance if the request lands on a healthy one
- operators cannot compare instances without hitting different pods manually

## Recommended Approach

Keep sampling local and make reporting distributed.

Each instance should continue to run its own `MemoryMonitor`. After sampling or explicit refresh, that instance should publish a serialized diagnostics snapshot to Redis with a short TTL. The health route should then aggregate all live instance snapshots from Redis and present:

- a cluster view
- a selected instance view
- top-level compatibility fields that continue to satisfy the current frontend

This preserves the correct ownership boundary:

- process memory is measured locally
- cluster health is assembled centrally from local measurements

## Alternatives Considered

### 1. Cross-instance synchronous refresh RPC

Ask every instance to run heavy diagnostics when one request arrives.

This would produce fresher data, but it adds routing, correlation IDs, timeout handling, partial failure logic, and the risk of triggering expensive tracemalloc snapshots across all instances at once. That is too heavy for the first version.

### 2. Pure local endpoint

Leave `/health/memory` instance-local and add documentation.

This is the smallest change, but it does not solve the distributed visibility problem that motivated the work.

### 3. Distributed snapshots with local refresh

This is the recommended option.

Default reads use the most recent Redis snapshots for all instances. `refresh=true` refreshes only the current instance, republishes that result, and then returns the aggregated cluster view. This gives us a safe and understandable first step.

## Architecture

### Local Monitor

`MemoryMonitor` remains the source of truth for one process. It should continue to own:

- periodic sampling
- leak detection
- heavy diagnostics capture
- summary generation

It should not try to hold cluster state.

### Distributed Publisher

Add a small distribution layer for memory health snapshots, similar in spirit to existing Redis-backed distributed helpers elsewhere in the codebase.

Responsibilities:

- derive a stable per-process `instance_id`
- serialize local diagnostics into a Redis-safe payload
- write the payload to Redis with TTL
- read all current instance payloads from Redis

### Aggregating Route

`/health/memory` should stop treating the local monitor response as the whole system response. Instead it should:

1. optionally refresh local diagnostics when `refresh=true`
2. ensure the local instance snapshot is published
3. fetch all live instance snapshots from Redis
4. compute cluster-level aggregate fields
5. expose a selected instance view at the top level for backward compatibility

## Data Model

### Redis Keys

Use one key per instance:

- `health:memory:instance:{instance_id}`

TTL should be slightly larger than the sampling cadence so instances disappear naturally after restart or failure. A good default is roughly `max(2 * interval_seconds, 120)`.

### Snapshot Shape

Each instance snapshot should contain only serialized, operator-facing data:

- `instance_id`
- `captured_at`
- `summary`
- `overview`
- `highlights`
- `top_growth`
- `top_allocations`
- `top_objects`

Do not attempt to store:

- raw `tracemalloc.Snapshot`
- deque objects
- locks
- in-memory baseline state

Those remain process-local implementation detail.

## API Behavior

### Request Semantics

`GET /api/health/memory`

- returns aggregated cluster diagnostics when Redis snapshots are available
- returns local-only diagnostics when Redis is unavailable or no distributed data exists

`GET /api/health/memory?refresh=true`

- forces a fresh local `get_diagnostics(refresh=True)`
- republishes the current instance snapshot
- still aggregates peer snapshots from Redis
- does not force other instances to run heavy diagnostics

An optional future extension may add `instance_id` query selection, but the first version does not need to expose that if the frontend is still single-panel.

### Response Shape

Add cluster-aware fields:

- `local_instance_id`
- `cluster_overview`
- `instances`
- `selected_instance`

Also keep the existing top-level fields:

- `overview`
- `highlights`
- `top_growth`
- `top_allocations`
- `top_objects`

These compatibility fields should mirror `selected_instance`, which should default to the local instance when present.

### Cluster Overview

The aggregate section should include enough information for a summary panel:

- `instance_count`
- `stable_count`
- `suspected_leak_count`
- `unavailable_count`
- `total_rss_bytes`
- `total_rss`
- `latest_sample_at`

The exact list can stay modest, but it should be deterministic and derived from live instance snapshots only.

## Compatibility Strategy

The current frontend expects one diagnostics object. We should not break it.

For the first rollout:

- keep existing top-level fields populated
- add new distributed fields without removing the old ones

This allows the backend to ship before the frontend grows per-instance navigation.

## Error Handling

### Redis Unavailable

If Redis read/write fails:

- log the failure at warning or debug level as appropriate
- return local diagnostics only
- never fail the endpoint solely because distributed aggregation is unavailable

### Missing or Expired Instance Snapshots

If an instance snapshot expires, aggregation should simply omit that instance. TTL-based disappearance is the normal stale-instance cleanup mechanism.

### Heavy Diagnostics Disabled

If heavy diagnostics are disabled on an instance:

- publish the instance anyway
- allow `overview` and summary data to appear
- leave detail tables empty or carry through the existing disabled reason payload

## Testing

Add tests for:

- local snapshot serialization from memory diagnostics
- Redis snapshot publish and read helpers
- cluster aggregation with multiple instance payloads
- route behavior when Redis returns multiple instances
- route fallback when Redis is unavailable
- `refresh=true` refreshing only the local instance and preserving remote cached snapshots
- compatibility fields matching the selected instance payload

## Files In Scope

- `src/infra/monitoring/memory.py`
- `src/api/routes/health.py`
- `src/infra/storage/redis.py`
- `tests/infra/test_memory_monitor.py`
- `tests/api/routes/test_health.py`

Potential new module:

- `src/infra/monitoring/distributed_memory_health.py`
