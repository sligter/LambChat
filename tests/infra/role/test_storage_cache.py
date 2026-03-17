"""Tests for role storage caching."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from src.infra.role.storage import RoleStorage
from src.kernel.schemas.role import Role

VALID_ROLE_ID = str(ObjectId())


@pytest.fixture
def mock_role_dict():
    return {
        "id": VALID_ROLE_ID,
        "name": "admin",
        "description": "Admin role",
        "permissions": ["chat:read", "chat:write"],
        "allowed_agents": [],
        "limits": None,
        "is_system": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def mock_role(mock_role_dict):
    return Role(**mock_role_dict)


def _mock_storage_with_collection():
    """Create a RoleStorage with a mocked MongoDB collection."""
    storage = RoleStorage()
    storage._collection = MagicMock()
    return storage


@pytest.mark.asyncio
async def test_get_by_name_cache_hit(mock_role, mock_role_dict):
    """get_by_name should return cached role on cache hit."""
    storage = _mock_storage_with_collection()

    with patch("src.infra.role.storage._get_redis", new_callable=AsyncMock) as mock_redis_getter:
        mock_redis = AsyncMock()
        mock_redis_getter.return_value = mock_redis

        # Version key returns "1", cache key has data
        mock_redis.get = AsyncMock(
            side_effect=lambda key: {
                "role:obj_ver:admin": "1",
                "role:obj:admin:v1": json.dumps(mock_role_dict),
            }.get(key)
        )

        result = await storage.get_by_name("admin")

        assert result is not None
        assert result.name == "admin"
        # Should NOT have queried MongoDB
        storage._collection.find_one.assert_not_called()


@pytest.mark.asyncio
async def test_get_by_name_cache_miss_then_fill(mock_role, mock_role_dict):
    """get_by_name should query DB on miss, then write to cache."""
    storage = _mock_storage_with_collection()

    with patch("src.infra.role.storage._get_redis", new_callable=AsyncMock) as mock_redis_getter:
        mock_redis = AsyncMock()
        mock_redis_getter.return_value = mock_redis

        # Cache miss: version "1", no data for v1
        mock_redis.get = AsyncMock(
            side_effect=lambda key: {
                "role:obj_ver:admin": "1",
                "role:obj:admin:v1": None,
            }.get(key)
        )
        mock_redis.set = AsyncMock()

        # DB returns role
        raw_db_doc = {**mock_role_dict, "_id": "test-id"}
        storage._collection.find_one = AsyncMock(return_value=raw_db_doc)

        result = await storage.get_by_name("admin")

        assert result is not None
        assert result.name == "admin"
        # Should have queried MongoDB
        storage._collection.find_one.assert_called_once()
        # Should have written to cache
        mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_get_by_name_none_result():
    """get_by_name for non-existent role should cache None sentinel."""
    storage = _mock_storage_with_collection()

    with patch("src.infra.role.storage._get_redis", new_callable=AsyncMock) as mock_redis_getter:
        mock_redis = AsyncMock()
        mock_redis_getter.return_value = mock_redis

        mock_redis.get = AsyncMock(
            side_effect=lambda key: {
                "role:obj_ver:unknown": "1",
                "role:obj:unknown:v1": None,
            }.get(key)
        )
        mock_redis.set = AsyncMock()

        # DB returns None
        storage._collection.find_one = AsyncMock(return_value=None)

        result = await storage.get_by_name("unknown")

        assert result is None
        mock_redis.set.assert_called_once()
        # Verify the cached value is the None sentinel
        call_args = mock_redis.set.call_args
        assert call_args[0][1] == "null"


@pytest.mark.asyncio
async def test_get_by_names_uses_cache(mock_role, mock_role_dict):
    """get_by_names should use cached roles where available, only query DB for misses."""
    storage = _mock_storage_with_collection()

    with patch("src.infra.role.storage._get_redis", new_callable=AsyncMock) as mock_redis_getter:
        mock_redis = AsyncMock()
        mock_redis_getter.return_value = mock_redis

        user_role_dict = {**mock_role_dict, "name": "user", "is_system": False}

        # admin cached, user not cached
        call_count = 0

        def redis_get_side_effect(key):
            nonlocal call_count
            call_count += 1
            mapping = {
                "role:obj_ver:admin": "1",
                "role:obj:admin:v1": json.dumps(mock_role_dict),
                "role:obj_ver:user": "1",
                "role:obj:user:v1": None,
            }
            return mapping.get(key)

        mock_redis.get = AsyncMock(side_effect=redis_get_side_effect)
        mock_redis.set = AsyncMock()

        # DB returns user role for "user" query
        user_db_doc = {**user_role_dict, "_id": "user-id"}
        storage._collection.find_one = AsyncMock(return_value=user_db_doc)

        results = await storage.get_by_names(["admin", "user"])

        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"admin", "user"}


@pytest.mark.asyncio
async def test_invalidate_called_on_update(mock_role_dict):
    """update() should invalidate cache for the updated role."""
    storage = _mock_storage_with_collection()

    with patch("src.infra.role.storage._get_redis", new_callable=AsyncMock) as mock_redis_getter:
        mock_redis = AsyncMock()
        mock_redis_getter.return_value = mock_redis

        # get_by_id: cache miss, DB returns non-system role
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.incr = AsyncMock()

        existing_doc = {**mock_role_dict, "_id": ObjectId(VALID_ROLE_ID), "is_system": False}
        updated_doc = {**existing_doc, "description": "updated"}
        storage._collection.find_one = AsyncMock(return_value=existing_doc)
        storage._collection.find_one_and_update = AsyncMock(return_value=updated_doc)

        from src.kernel.schemas.role import RoleUpdate

        await storage.update(VALID_ROLE_ID, RoleUpdate(description="updated"))

        mock_redis.incr.assert_called_once()
        incr_arg = mock_redis.incr.call_args[0][0]
        assert "admin" in incr_arg


@pytest.mark.asyncio
async def test_invalidate_called_on_delete(mock_role_dict):
    """delete() should invalidate cache for the deleted role."""
    storage = _mock_storage_with_collection()

    with patch("src.infra.role.storage._get_redis", new_callable=AsyncMock) as mock_redis_getter:
        mock_redis = AsyncMock()
        mock_redis_getter.return_value = mock_redis

        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.incr = AsyncMock()

        existing_doc = {**mock_role_dict, "_id": ObjectId(VALID_ROLE_ID), "is_system": False}
        storage._collection.find_one = AsyncMock(return_value=existing_doc)
        delete_result = MagicMock()
        delete_result.deleted_count = 1
        storage._collection.delete_one = AsyncMock(return_value=delete_result)

        await storage.delete(VALID_ROLE_ID)

        mock_redis.incr.assert_called_once()
        incr_arg = mock_redis.incr.call_args[0][0]
        assert "admin" in incr_arg
