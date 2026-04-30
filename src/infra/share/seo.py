from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

DEFAULT_SHARE_ROBOTS = "noindex, follow, max-image-preview:large"
DEFAULT_SHARE_PREVIEW_LABEL = "Shared session preview"
DEFAULT_SHARE_DESCRIPTION = "View this shared session on LambChat."

_WHITESPACE_RE = re.compile(r"\s+")
_ROOT_DIV_RE = re.compile(r'<div id="root"></div>')
_SHARED_PREVIEW_RE = re.compile(
    r'(<div id="shared-server-preview">.*?</div>\s*)?<div id="root"></div>', re.S
)


@dataclass(frozen=True)
class SharedPageSeo:
    title: str
    description: str
    canonical_url: str
    robots: str
    og_type: str
    preview_label: str
    preview_title: str
    preview_summary: str
    author_name: str
    published_date: str


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


def _truncate_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value

    clipped = value[: max_length + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    if not clipped:
        clipped = value[:max_length]
    return f"{clipped}..."


def _extract_preview_lines(events: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    first_user = ""
    first_assistant = ""

    for event in events:
        event_type = event.get("event_type", "")
        data = event.get("data") or {}
        content = _normalize_text(data.get("content"))
        if not content:
            continue

        if event_type == "user:message" and not first_user:
            first_user = content
            continue

        if event_type in {"message:chunk", "assistant:message"} and not first_assistant:
            first_assistant = content

        if first_user and first_assistant:
            break

    return first_user, first_assistant


def _format_date(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def build_shared_page_seo(
    *,
    base_url: str,
    share_id: str,
    session: Mapping[str, Any],
    owner: Mapping[str, Any] | None,
    events: Sequence[Mapping[str, Any]],
    app_name: str = "LambChat",
    indexable: bool = False,
) -> SharedPageSeo:
    first_user, first_assistant = _extract_preview_lines(events)

    raw_title = _normalize_text(session.get("name")) or _truncate_text(
        first_user or "Shared session",
        60,
    )
    preview_title = raw_title or "Shared session"
    title = f"{preview_title} - {app_name} Shared Session"

    description_parts = [
        _truncate_text(first_user, 140) if first_user else "",
        _truncate_text(first_assistant, 140) if first_assistant else "",
    ]
    description = " ".join(part for part in description_parts if part).strip()
    if not description:
        description = DEFAULT_SHARE_DESCRIPTION

    summary = description
    if summary == DEFAULT_SHARE_DESCRIPTION and _normalize_text(session.get("agent_name")):
        summary = f"{summary} Agent: {_normalize_text(session.get('agent_name'))}."

    robots = "index, follow, max-image-preview:large" if indexable else DEFAULT_SHARE_ROBOTS
    canonical_url = f"{base_url.rstrip('/')}/shared/{share_id}"

    return SharedPageSeo(
        title=title,
        description=description,
        canonical_url=canonical_url,
        robots=robots,
        og_type="article",
        preview_label=DEFAULT_SHARE_PREVIEW_LABEL,
        preview_title=preview_title,
        preview_summary=summary,
        author_name=_normalize_text((owner or {}).get("username")),
        published_date=_format_date(session.get("created_at")),
    )


def build_shared_page_error_seo(
    *,
    base_url: str,
    share_id: str,
    app_name: str = "LambChat",
    reason: str,
) -> SharedPageSeo:
    messages = {
        "not_found": (
            "Shared session not found",
            "This shared session was not found or is no longer available.",
        ),
        "auth_required": (
            "Login required for shared session",
            "Sign in to view this shared session.",
        ),
    }
    preview_title, description = messages.get(
        reason,
        ("Shared session unavailable", "This shared session is currently unavailable."),
    )

    return SharedPageSeo(
        title=f"{preview_title} - {app_name}",
        description=description,
        canonical_url=f"{base_url.rstrip('/')}/shared/{share_id}",
        robots=DEFAULT_SHARE_ROBOTS,
        og_type="article",
        preview_label=DEFAULT_SHARE_PREVIEW_LABEL,
        preview_title=preview_title,
        preview_summary=description,
        author_name="",
        published_date="",
    )


def _replace_title(html_doc: str, value: str) -> str:
    replacement = f"<title>{html.escape(value, quote=True)}</title>"
    return re.sub(r"<title>.*?</title>", replacement, html_doc, count=1, flags=re.S)


def _replace_link(html_doc: str, rel: str, href: str) -> str:
    escaped_href = html.escape(href, quote=True)
    replacement = f'<link rel="{rel}" href="{escaped_href}" />'
    pattern = re.compile(rf'<link\s+rel="{re.escape(rel)}"\s+href="[^"]*"\s*/?>', re.I)
    if pattern.search(html_doc):
        return pattern.sub(replacement, html_doc, count=1)
    return html_doc.replace("</head>", f"    {replacement}\n  </head>", 1)


def _replace_meta(html_doc: str, attr: str, name: str, content: str) -> str:
    escaped = html.escape(content, quote=True)
    replacement = f'<meta {attr}="{name}" content="{escaped}" />'
    pattern = re.compile(
        rf'<meta\s+[^>]*{attr}="{re.escape(name)}"[^>]*content="[^"]*"[^>]*>',
        re.I,
    )
    if pattern.search(html_doc):
        return pattern.sub(replacement, html_doc, count=1)
    return html_doc.replace("</head>", f"    {replacement}\n  </head>", 1)


def inject_share_seo_into_html(html_doc: str, seo: SharedPageSeo) -> str:
    rendered = html_doc
    rendered = _replace_title(rendered, seo.title)
    rendered = _replace_link(rendered, "canonical", seo.canonical_url)
    rendered = _replace_meta(rendered, "name", "description", seo.description)
    rendered = _replace_meta(rendered, "name", "robots", seo.robots)
    rendered = _replace_meta(rendered, "property", "og:type", seo.og_type)
    rendered = _replace_meta(rendered, "property", "og:title", seo.title)
    rendered = _replace_meta(rendered, "property", "og:description", seo.description)
    rendered = _replace_meta(rendered, "property", "og:url", seo.canonical_url)
    rendered = _replace_meta(rendered, "name", "twitter:title", seo.title)
    rendered = _replace_meta(rendered, "name", "twitter:description", seo.description)
    rendered = _replace_meta(rendered, "property", "og:image:alt", seo.preview_title)
    rendered = _replace_meta(rendered, "name", "twitter:image:alt", seo.preview_title)

    byline_parts = [part for part in [seo.author_name, seo.published_date] if part]
    byline = " · ".join(byline_parts)
    summary_html = html.escape(seo.preview_summary, quote=True)
    byline_html = html.escape(byline, quote=True)

    preview_markup = f"""<div id="shared-server-preview">
  <main data-shared-preview="server" style="max-width: 760px; margin: 0 auto; padding: 48px 24px; font-family: 'Source Sans 3', sans-serif; color: #1c1917; background: #faf9f7; min-height: 100vh;">
    <p style="margin: 0 0 12px; font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: #78716c;">{html.escape(seo.preview_label, quote=True)}</p>
    <h1 style="margin: 0 0 16px; font-size: 40px; line-height: 1.15; color: #1c1917;">{html.escape(seo.preview_title, quote=True)}</h1>
    <p style="margin: 0 0 16px; font-size: 18px; line-height: 1.7; color: #44403c;">{summary_html}</p>
    <p style="margin: 0; font-size: 14px; color: #78716c;">{byline_html}</p>
  </main>
</div>"""

    replacement = f'{preview_markup}\n<div id="root"></div>'
    if _SHARED_PREVIEW_RE.search(rendered):
        return _SHARED_PREVIEW_RE.sub(replacement, rendered, count=1)
    if _ROOT_DIV_RE.search(rendered):
        return _ROOT_DIV_RE.sub(replacement, rendered, count=1)
    return rendered
