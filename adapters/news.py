"""News adapter: dated third-party coverage.

Built on the search adapter, because a news source with no date is not news.
Items published outside the freshness window are dropped from the Recent
section, but a failure to reach one is still noted.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import Policy
from .search import SearchFn, collect_search


def collect_news(
    name: str,
    search_fn: Optional[SearchFn],
    *,
    limit: int = 5,
    freshness_days: int = 90,
    policy: Optional[Policy] = None,
) -> dict[str, Any]:
    query = f"{name} news"
    result = collect_search(
        query, search_fn, limit=limit, policy=policy, source_type="news"
    )
    kept = []
    stale = 0
    undated = 0
    for doc in result["documents"]:
        if not doc.published_at:
            # A page with no publication date is not a dated news item, and the
            # Recent section needs dates. Leave it to the search adapter.
            undated += 1
            continue
        age = _age_days(doc.published_at)
        if age is not None and age > freshness_days:
            stale += 1
            continue
        kept.append(doc)
    notes = list(result["notes"])
    if undated:
        notes.append(f"news: {undated} page(s) had no publication date and were not treated as news")
    if stale:
        notes.append(f"news: dropped {stale} item(s) older than {freshness_days} days")
    return {"documents": kept, "notes": notes}


def _age_days(iso_date: str) -> Optional[int]:
    import time

    try:
        then = time.strptime(iso_date[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return int((time.time() - time.mktime(then)) // 86400)
