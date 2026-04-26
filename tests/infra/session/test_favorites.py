from src.infra.session.favorites import (
    is_session_favorite,
    normalize_session_metadata,
)


def test_explicit_favorite_flag_wins():
    assert is_session_favorite(
        {"is_favorite": True, "project_id": "project-1"},
        favorites_project_id="favorites-project",
    )
    assert not is_session_favorite(
        {"is_favorite": False, "project_id": "favorites-project"},
        favorites_project_id="favorites-project",
    )


def test_legacy_favorites_project_is_treated_as_favorite():
    assert is_session_favorite(
        {"project_id": "favorites-project"},
        favorites_project_id="favorites-project",
    )


def test_normalize_session_metadata_sets_explicit_favorite_for_legacy_data():
    assert normalize_session_metadata(
        {"project_id": "favorites-project"},
        favorites_project_id="favorites-project",
    ) == {
        "project_id": "favorites-project",
        "is_favorite": True,
    }
