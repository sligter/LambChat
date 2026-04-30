from __future__ import annotations

from types import SimpleNamespace


class _FakeSkillStorage:
    def __init__(self) -> None:
        self.files = {
            "visible": {
                "SKILL.md": "visible skill",
                "notes.txt": "needle in visible notes",
            },
        }

    async def get_effective_skills(self, user_id: str) -> dict:
        return {
            "skills": {
                name: {
                    "name": name,
                    "description": f"Skill: {name}",
                    "files": files,
                    "enabled": True,
                }
                for name, files in self.files.items()
            }
        }

    async def get_skill_file(self, skill_name: str, file_name: str, user_id: str) -> str | None:
        return self.files.get(skill_name, {}).get(file_name)

    async def list_skill_file_paths(self, skill_name: str, user_id: str) -> list[str]:
        return list(self.files.get(skill_name, {}).keys())

    async def batch_get_skill_files(self, skill_keys: list[tuple[str, str]]) -> dict:
        return {
            (skill_name, user_id): self.files.get(skill_name, {})
            for skill_name, user_id in skill_keys
        }


class _FakeFilesAPI:
    def __init__(self, responses: dict[str, list[SimpleNamespace]]) -> None:
        self.responses = responses

    def list(self, path: str):
        return self.responses.get(path, [])


class _FakeE2BSandbox:
    def __init__(self, files_api: _FakeFilesAPI) -> None:
        self.sandbox_id = "e2b-test"
        self.files = files_api


def test_skills_store_backend_supports_current_deepagents_protocol() -> None:
    from src.infra.backend import SkillsStoreBackend

    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeSkillStorage()

    entries = backend.ls_info("/skills/")
    assert entries == [{"path": "/visible/", "is_dir": True}]

    content = backend.read("/skills/visible/SKILL.md")
    assert "visible skill" in content

    matches = backend.glob_info("*", "/skills/")
    assert matches == [{"path": "/visible/", "is_dir": True}]


def test_e2b_backend_supports_current_deepagents_protocol() -> None:
    from src.infra.backend.e2b import E2BBackend

    files_api = _FakeFilesAPI(
        {
            "/home/user": [
                SimpleNamespace(path="/home/user/project", is_dir=True, size=0),
                SimpleNamespace(path="/home/user/readme.md", is_dir=False, size=12),
            ],
            "/home/user/project": [
                SimpleNamespace(path="/home/user/project/app.py", is_dir=False, size=42),
            ],
        }
    )
    backend = E2BBackend(sandbox=_FakeE2BSandbox(files_api))

    entries = backend.ls_info("/home/user")
    assert entries == [
        {"path": "/home/user/project", "is_dir": True, "size": 0},
        {"path": "/home/user/readme.md", "size": 12},
    ]

    matches = backend.glob_info("*.py", path="/")
    assert matches == [{"path": "/home/user/project/app.py", "size": 42}]
