from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import main as api_main


class _FakeOwner:
    def __init__(self, username: str) -> None:
        self.username = username

    def model_dump(self) -> dict[str, str]:
        return {"username": self.username}


@pytest.mark.asyncio
async def test_shared_page_route_injects_share_specific_seo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        """
<!doctype html>
<html lang="en">
  <head>
    <link rel="canonical" href="https://lambchat.com/" />
    <title>LambChat - AI Agent Platform</title>
    <meta name="description" content="Default description" />
    <meta name="robots" content="index, follow, max-image-preview:large" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content="Default og title" />
    <meta property="og:description" content="Default og description" />
    <meta property="og:url" content="https://lambchat.com/" />
    <meta name="twitter:title" content="Default twitter title" />
    <meta name="twitter:description" content="Default twitter description" />
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    async def _fake_get_shared_content(share_id: str, user=None):
        assert share_id == "ssehSOzUgKnX"
        assert user is None
        return SimpleNamespace(
            session={
                "name": "🤖 创意Agent专利",
                "agent_name": "Search Agent",
                "created_at": "2026-04-29T18:51:10.499000",
            },
            events=[
                {
                    "event_type": "user:message",
                    "data": {"content": "帮我写一个创意agent的训练方法的专利。"},
                },
                {
                    "event_type": "message:chunk",
                    "data": {"content": "技术交底书已完整生成。"},
                },
            ],
            owner=_FakeOwner("clivia.yang"),
        )

    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )
    monkeypatch.setattr(api_main.share, "get_shared_content", _fake_get_shared_content)
    monkeypatch.setattr(api_main.settings, "APP_BASE_URL", "https://lambchat.com")

    app = api_main.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://lambchat.com") as client:
        response = await client.get("/shared/ssehSOzUgKnX")

    assert response.status_code == 200
    assert "<title>🤖 创意Agent专利 - LambChat Shared Session</title>" in response.text
    assert 'rel="canonical" href="https://lambchat.com/shared/ssehSOzUgKnX"' in response.text
    assert 'content="noindex, follow, max-image-preview:large"' in response.text
    assert "Shared session preview" in response.text
