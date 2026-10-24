import html

HIGHLIGHT_START = "\x02"
HIGHLIGHT_STOP = "\x03"
FRAGMENT_SEPARATOR = "\x1f"
TAG_SEPARATOR = "\x1e"
MARK_START = "<mark>"
MARK_STOP = "</mark>"


def render_highlight(text: str | None) -> str:
    escaped = html.escape(text or "", quote=False)
    return escaped.replace(HIGHLIGHT_START, MARK_START).replace(HIGHLIGHT_STOP, MARK_STOP)


def render_snippets(text: str | None, fallback: str | None = None) -> list[str]:
    if HIGHLIGHT_START not in (text or ""):
        text = fallback
    fragments = (fragment.strip() for fragment in (text or "").split(FRAGMENT_SEPARATOR))
    return [render_highlight(fragment) for fragment in fragments if HIGHLIGHT_START in fragment]


def highlighted_tags(text: str | None) -> set[str]:
    return {
        tag.replace(HIGHLIGHT_START, "").replace(HIGHLIGHT_STOP, "").strip()
        for tag in (text or "").split(TAG_SEPARATOR)
        if HIGHLIGHT_START in tag
    }


def serialize_search_highlights(row: dict) -> dict:
    return {
        "title": render_highlight(row["title_highlight"]),
        "description": render_highlight(row["description_highlight"]),
        "content": render_snippets(row["content_highlight"], row.get("content_highlight_en")),
        "matched_tags": highlighted_tags(row["tags_highlight"]),
    }
