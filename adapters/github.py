"""GitHub adapter: an organisation's public, self-published presence.

Uses the unauthenticated REST API, so no credentials exist to leak and nothing
sits behind a login. The document text is rendered from the API response
field by field; the quote we store is therefore a verbatim fragment of the
document we created, and the URL records where the facts came from. That is
disclosed in the README.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..models import Document

from .base import Policy, fetch, now_iso

API = "https://api.github.com"


def _get_json(path: str, policy: Optional[Policy]) -> Any:
    result = fetch(API + path, policy)
    if not result.text:
        return None
    try:
        return json.loads(result.text)
    except Exception:
        return None


def _slug_from_url(value: str) -> Optional[str]:
    match = re.search(r"github\.com/([A-Za-z0-9_.-]+)", value or "")
    return match.group(1) if match else None


def collect_github(
    slug: Optional[str],
    *,
    policy: Optional[Policy] = None,
    website: Optional[str] = None,
) -> dict[str, Any]:
    slug = slug or (_slug_from_url(website or "") if website else None)
    if not slug:
        return {"documents": [], "notes": ["github: no organisation slug known"]}

    org = _get_json(f"/orgs/{slug}", policy)
    if not isinstance(org, dict) or not org.get("login"):
        return {"documents": [], "notes": [f"github: no public organisation {slug!r}"]}

    repos = _get_json(f"/orgs/{slug}/repos?sort=pushed&direction=desc&per_page=5", policy)
    repos = repos if isinstance(repos, list) else []

    lines = [f"{org.get('name') or slug} is a GitHub organisation."]
    if org.get("description"):
        lines.append(f"It builds {str(org['description']).strip().rstrip('.')}.")
    location = (org.get("location") or "").strip()
    if location:
        lines.append(f"Headquartered in {location}.")
    if org.get("blog"):
        lines.append(f"Its website is {str(org['blog']).strip()}.")
    if org.get("public_repos") is not None:
        lines.append(f"It maintains {org['public_repos']} public repositories.")
    if repos:
        names = ", ".join(str(r.get("name")) for r in repos[:5] if r.get("name"))
        last = max((str(r.get("pushed_at") or r.get("updated_at") or "") for r in repos), default="")
        if names:
            lines.append(f"Its most recently updated repositories are {names}.")
        if last:
            lines.append(f"The newest push to those repositories was on {last[:10]}.")

    doc = Document(
        url=f"https://github.com/{org.get('login')}",
        title=f"{org.get('name') or slug} on GitHub",
        text="\n".join(lines),
        source_type="github",
        retrieved_at=now_iso(),
        published_at=None,
        domain="github.com",
        note="rendered from the public GitHub REST API",
    )
    return {"documents": [doc], "notes": []}
