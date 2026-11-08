"""Web-search adapter.

The search backend only *finds* pages. Every result is fetched in full before
it can become evidence, because a snippet has no reliable date and no reliable
quote. A result we cannot fetch is recorded as a note, never used.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..models import Document
from ..resolve import registrable_domain

from .base import Policy, fetch, html_to_text, now_iso, published_at

SearchFn = Callable[[str, int], list[dict[str, Any]]]


_LIST_KEYS = ("results", "items", "organic", "web", "data", "pages", "documents", "hits")


def _find_list(node: Any, depth: int = 0) -> Optional[list]:
    """Dig a list of results out of whatever envelope the backend uses.

    Hermes' own `web_search` returns ``{"success": bool, "data": {"web": [...]}}``;
    other backends return ``{"results": [...]}`` or a bare list. Walking the
    known containers is cheaper than one branch per provider.
    """
    if isinstance(node, list):
        return node
    if isinstance(node, dict) and depth < 4:
        for key in _LIST_KEYS:
            if key in node:
                found = _find_list(node[key], depth + 1)
                if found is not None:
                    return found
    return None


def normalise_results(raw: Any) -> list[dict[str, str]]:
    """Accept the several shapes a search backend may return."""
    items: list[dict[str, str]] = []
    if isinstance(raw, str):
        from .base import json_load

        raw = json_load(raw) or {}
    found = _find_list(raw)
    if found is None:
        return items
    for entry in found:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url") or entry.get("link") or entry.get("href") or ""
        if not url.startswith("http"):
            continue
        items.append(
            {
                "url": url,
                "title": str(entry.get("title") or entry.get("name") or ""),
                "published_at": str(
                    entry.get("published_at")
                    or entry.get("date")
                    or entry.get("published")
                    or entry.get("publishedDate")
                    or ""
                ),
            }
        )
    return items


def collect_search(
    query: str,
    search_fn: Optional[SearchFn],
    *,
    limit: int = 5,
    policy: Optional[Policy] = None,
    source_type: str = "search",
    skip_domains: set[str] | None = None) -> dict[str, Any]:
    notes: list[str] = []
    if search_fn is None:
        return {"documents": [], "notes": [f"search: no search backend configured for {query!r}"]}

    try:
        results = normalise_results(search_fn(query, limit))
    except Exception as exc:
        return {"documents": [], "notes": [f"search: backend failed for {query!r}: {exc}"]}

    if not results:
        return {"documents": [], "notes": [f"search: no results for {query!r}"]}

    skip = skip_domains or set()
    documents: list[Document] = []
    seen: set[str] = set()
    for result in results[:limit]:
        domain = registrable_domain(result["url"])
        if any(domain == d or domain.endswith("." + d) for d in skip):
            continue
        key = result["url"].split("#")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        page = fetch(result["url"], policy)
        if not page.text:
            notes.append(f"search: {result['url']}, {page.error or 'unavailable'}")
            continue
        title, text, meta, times = html_to_text(page.text)
        if not text.strip():
            notes.append(f"search: {result['url']}, no readable text")
            continue
        documents.append(
            Document(
                url=page.final_url or result["url"],
                title=(title or result["title"] or domain).strip(),
                text=text,
                source_type=source_type,
                retrieved_at=page.retrieved_at or now_iso(),
                published_at=published_at(page.text, times, meta) or (result["published_at"] or None),
                domain=domain,
                note=page.error)
        )

    if not documents:
        notes.append(f"search: found {len(results)} result(s) for {query!r}, none fetchable")
    return {"documents": documents, "notes": notes}
