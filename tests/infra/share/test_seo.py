from src.infra.share.seo import build_shared_page_seo, inject_share_seo_into_html


def test_build_shared_page_seo_uses_share_specific_metadata() -> None:
    seo = build_shared_page_seo(
        base_url="https://lambchat.com",
        share_id="ssehSOzUgKnX",
        session={
            "name": "🤖 创意Agent专利",
            "agent_name": "Search Agent",
            "created_at": "2026-04-29T18:51:10.499000",
        },
        owner={"username": "clivia.yang"},
        events=[
            {
                "event_type": "thinking",
                "data": {"content": "内部推理内容不应该出现在 SEO 摘要里"},
            },
            {
                "event_type": "tool:result",
                "data": {"result": "/home/user/outputs/secret.docx"},
            },
            {
                "event_type": "user:message",
                "data": {
                    "content": "帮我写一个创意agent的训练方法的专利，并根据工具调用能力来组织方案。"
                },
            },
            {
                "event_type": "message:chunk",
                "data": {"content": "技术交底书已完整生成，包含技术方案、保护点和实施例摘要。"},
            },
        ],
    )

    assert seo.title == "🤖 创意Agent专利 - LambChat Shared Session"
    assert seo.canonical_url == "https://lambchat.com/shared/ssehSOzUgKnX"
    assert seo.robots == "noindex, follow, max-image-preview:large"
    assert "帮我写一个创意agent的训练方法的专利" in seo.description
    assert "技术交底书已完整生成" in seo.description
    assert "内部推理内容" not in seo.description
    assert "/home/user/outputs/secret.docx" not in seo.description


def test_inject_share_seo_into_html_replaces_default_meta_and_adds_preview() -> None:
    html = """
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
""".strip()

    seo = build_shared_page_seo(
        base_url="https://lambchat.com",
        share_id="ssehSOzUgKnX",
        session={
            "name": "🤖 创意Agent专利",
            "agent_name": "Search Agent",
            "created_at": "2026-04-29T18:51:10.499000",
        },
        owner={"username": "clivia.yang"},
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
    )

    rendered = inject_share_seo_into_html(html, seo)

    assert "<title>🤖 创意Agent专利 - LambChat Shared Session</title>" in rendered
    assert 'rel="canonical" href="https://lambchat.com/shared/ssehSOzUgKnX"' in rendered
    assert 'meta name="robots" content="noindex, follow, max-image-preview:large"' in rendered
    assert 'property="og:type" content="article"' in rendered
    assert 'property="og:url" content="https://lambchat.com/shared/ssehSOzUgKnX"' in rendered
    assert "Shared session preview" in rendered
    assert "clivia.yang" in rendered
    assert "技术交底书已完整生成" in rendered
