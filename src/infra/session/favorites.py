"""Helpers for decoupled session favorites."""

from typing import Any, Mapping


def is_session_favorite(
    metadata: Mapping[str, Any] | None,
    favorites_project_id: str | None = None,
) -> bool:
    """Return whether a session should be treated as favorited.

    New data uses ``metadata.is_favorite``.
    Legacy data stored favorites by moving the session into the special
    favorites project, so we still recognize that shape while migrating.
    """

    data = metadata or {}
    explicit = data.get("is_favorite")
    if isinstance(explicit, bool):
        return explicit

    return bool(
        favorites_project_id
        and isinstance(data.get("project_id"), str)
        and data.get("project_id") == favorites_project_id
    )


def normalize_session_metadata(
    metadata: Mapping[str, Any] | None,
    favorites_project_id: str | None = None,
) -> dict[str, Any]:
    """Return session metadata with a normalized favorite flag."""

    normalized = dict(metadata or {})
    if is_session_favorite(normalized, favorites_project_id):
        normalized["is_favorite"] = True
    return normalized
