"""Official-site adapter: the organisation describing itself.

Fetches the homepage plus at most two pages it links to that look like an about
or company page. Its own domain is the strongest non-registry signal we have,
and it is *primary*: this is the entity speaking about itself, not a third party
summarising it.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..models import Document
from ..resolve import registrable_domain

from .base import Policy, fetch, html_to_text, now_iso, published_at

_ABOUT = re.compile(r'href=["\']([^"\']*(?:about|company|who-we-are|our-story|contact)[^"\']*)["\']', re.I)
MAX_ABOUT_PAGES = 2
# When the front page does not link an about page, these are the usual paths.
# Tried only after the links, and a miss is silent: guessing a path is a probe,
# not a failure of the entity.
FALLBACK_PATHS = ("/about", "/about-us", "/company", "/our-story")


def _page(url: str, policy: Optional[Policy]) -> tuple[Optional[Document], list[str]]:
    result = fetch(url, policy)
    if not result.ok and not result.text:
        return None, [f"{url}: {result.error or 'unavailable'}"]
    title, text, meta, times = html_to_text(result.text)
    if not text.strip():
        return None, [f"{url}: no readable text"]
    domain = registrable_domain(result.final_url or url)
    doc = Document(
        url=result.final_url or url,
        title=(title or meta.get("og:title") or domain).strip(),
        text=text,
        source_type="official",
        retrieved_at=result.retrieved_at or now_iso(),
        published_at=published_at(result.text, times, meta),
        domain=domain,
        note=result.error,
        description=(meta.get("description") or meta.get("og:description") or "").strip() or None,
    )
    links = []
    for href in _ABOUT.findall(result.text):
        if href.startswith("/"):
            base = f"https://{domain}"
            links.append(base + href)
        elif href.startswith("http"):
            links.append(href)
    return doc, links


def collect_official(
    domain: str, policy: Optional[Policy] = None
) -> dict[str, Any]:
    domain = registrable_domain(domain)
    if not domain:
        return {"documents": [], "notes": ["official: no domain supplied"]}

    notes: list[str] = []
    documents: list[Document] = []
    seen: set[str] = set()

    for candidate in (f"https://{domain}/", f"https://www.{domain}/"):
        doc, links = _page(candidate, policy)
        if doc:
            documents.append(doc)
            seen.add(registrable_domain(doc.url))
            origin = doc.url.rstrip("/")
            same_site = [link for link in links if registrable_domain(link).endswith(domain)]
            for link in same_site[:MAX_ABOUT_PAGES]:
                if link.rstrip("/") in {d.url.rstrip("/") for d in documents}:
                    continue
                extra, _ = _page(link, policy)
                if extra:
                    documents.append(extra)
            break
        notes.extend(links)

    if len(documents) == 1:
        # A homepage that links no about page still usually has /about. Without
        # this, a company whose front page is all marketing gave a brief with no
        # founding year and no headcount, because the prose lives one click
        # further on.
        seen = {d.url.rstrip("/") for d in documents}
        for path in FALLBACK_PATHS:
            if len(documents) > MAX_ABOUT_PAGES:
                break
            url = f"https://{domain}{path}"
            if url.rstrip("/") in seen:
                continue
            extra, _ = _page(url, policy)
            if extra:
                documents.append(extra)
                seen.add(extra.url.rstrip("/"))

    if not documents:
        notes.append(f"official: could not read {domain}")
    return {"documents": documents, "notes": notes}
