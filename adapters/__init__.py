"""Source adapters.

Each adapter returns normalised :class:`models.Document` objects plus a note
when something could not be fetched. Adapters never raise: a blocked source is
a fact about the brief, not a crash.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from ..models import Document

from .base import Policy, fetch, html_to_text, json_load, now_iso, published_at

SearchFn = Callable[[str, int], list[dict[str, Any]]]


def _document_from_html(
    url: str,
    source_type: str,
    *,
    policy: Optional[Policy] = None,
) -> tuple[Optional[Document], Optional[str]]:
    result = fetch(url, policy)
    if not result.ok and not result.text:
        return None, f"{url}: {result.error or 'unavailable'}"
    title, text, meta, times = html_to_text(result.text)
    if not text.strip():
        return None, f"{url}: no readable text"
    domain = url.split("/")[2].lower() if "://" in url else ""
    doc = Document(
        url=result.final_url or url,
        title=title or meta.get("og:title", "") or domain,
        text=text,
        source_type=source_type,
        retrieved_at=result.retrieved_at or now_iso(),
        published_at=published_at(result.text, times, meta),
        domain=domain.removeprefix("www."),
        note=result.error,
    )
    return doc, None


def collect(
    documents: Iterable[Document], notes: Iterable[str]
) -> dict[str, Any]:
    return {"documents": list(documents), "notes": list(notes)}
