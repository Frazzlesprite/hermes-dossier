"""Entity resolution: turn a name into exactly one entity, or refuse.

Name collisions are the failure mode this module exists to prevent. Two people
called Sarah Chen are two entities, and a brief built on the wrong one is worse
than no brief. So the resolver has three outcomes:

* one candidate, with a disambiguator to justify it;
* several candidates, which become a question for the user;
* none, which is an honest "I could not find this".

It never picks the "most likely" on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .models import Document

# Domains that are never an organisation's own site.
_NOT_OWN_SITE = (
    "wikipedia.org",
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "crunchbase.com",
    "glassdoor.com",
    "bloomberg.com",
    "reuters.com",
    "forbes.com",
    "github.com",
    "medium.com",
    "reddit.com")

_ORG_SUFFIXES = re.compile(
    r"\b(pty\.?\s*ltd|pty|limited|ltd|inc\.?|llc|llp|plc|corp\.?|corporation|company|co\.|gmbh|sa|bv|nv|ag)\b",
    re.IGNORECASE)


@dataclass
class Candidate:
    name: str
    kind: str  # org | person
    disambiguator: str = ""
    domain: Optional[str] = None
    github: Optional[str] = None
    registry_id: Optional[str] = None
    country: Optional[str] = None
    sources: list[str] = field(default_factory=list)
    score: float = 0.0
    domain_hit: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "disambiguator": self.disambiguator,
            "domain": self.domain,
            "github": self.github,
            "registry_id": self.registry_id,
            "country": self.country,
            "sources": list(self.sources),
        }


def looks_like_org(name: str) -> bool:
    return bool(_ORG_SUFFIXES.search(name or ""))


def normalise(text: str) -> str:
    """Collapse whitespace and case, for cheap containment checks."""
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def registrable_domain(url: str) -> str:
    """Host without a leading www. Not a full PSL implementation, by choice."""
    host = re.sub(r"^https?://", "", (url or "").strip().lower()).split("/")[0]
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def is_own_site(domain: str, candidate_domain: Optional[str]) -> bool:
    if not domain or not candidate_domain:
        return False
    if any(domain == d or domain.endswith("." + d) for d in _NOT_OWN_SITE):
        return False
    return domain == candidate_domain or domain.endswith("." + candidate_domain)


def name_tokens(name: str) -> list[str]:
    stop = {
        "the", "and", "pty", "ltd", "limited", "inc", "llc", "plc", "group", "company",
        "corp", "corporation", "incorporated", "holdings", "pbc",
    }
    return [
        token
        for token in re.findall(r"[a-z0-9]{3,}", (name or "").casefold())
        if token not in stop
    ]


def candidates_from_documents(name: str, docs: Iterable[Document], kind: str | None = None) -> list[Candidate]:
    """Build candidates from fetched documents, keyed by the site they live on.

    A page on the entity's own domain is the strongest signal we have without a
    registry, because it is the organisation describing itself.
    """
    wanted = name.strip().casefold()
    found: dict[str, Candidate] = {}
    for doc in docs:
        domain = doc.domain or registrable_domain(doc.url)
        if not domain:
            continue
        title = (doc.title or "").strip()
        title_match = wanted in title.casefold() or title.casefold() in wanted
        mentioned = wanted in normalise(doc.text)[:400]
        if not (title_match or mentioned):
            # A page that never names the entity is evidence about something
            # else; it must not create an identity.
            continue
        if any(domain == d or domain.endswith("." + d) for d in _NOT_OWN_SITE):
            # A profile page tells us the entity exists, but it is not its site.
            key = f"{domain}:{title.casefold()}"
            found.setdefault(
                key,
                Candidate(
                    name=title or name,
                    kind=kind or "org",
                    disambiguator=_profile_disambiguator(doc),
                    domain=None,
                    sources=[doc.url],
                    score=0.3))
            continue
        key = domain
        tokens = name_tokens(name)
        hit = any(token in domain for token in tokens)
        cand = found.setdefault(
            key,
            Candidate(
                name=title or name,
                kind=kind or "org",
                domain=domain,
                sources=[],
                score=0.0,
                domain_hit=hit))
        cand.sources.append(doc.url)
        cand.score += 0.5 if title_match else 0.1
        if hit:
            cand.score += 0.6
        if any(k.lower() in title.casefold() for k in ("about", "company", "who we are")):
            cand.score += 0.2

    return sorted(found.values(), key=lambda c: (-c.score, c.name))


def _profile_disambiguator(doc: Document) -> str:
    domain = doc.domain or registrable_domain(doc.url)
    return f"listed on {domain}" if domain else "profile page"


def _name_from_title(title: str, domain: str) -> Optional[str]:
    """The organisation's own name, dug out of a page title.

    A domain tells us *where* the entity is, not *what* it is called, so the
    title is the better source. Site titles are usually "Name | tagline", so
    take the first segment that is not the domain and not a long tagline.
    """
    if not title:
        return None
    parts = [p.strip(" -, ·|:·") for p in re.split(r"[|\u00b7]|\s+[\u2014\u2013-]\s+", title)]
    parts = [p for p in parts if p and len(p) <= 48 and domain.casefold() not in p.casefold()]
    if not parts:
        return None
    root = domain.split(".")[0].replace("-", " ").casefold()
    if root:
        for part in parts:
            if root in part.casefold():
                return part
    return parts[0]


def resolve(
    name: str,
    *,
    documents: Iterable[Document] = (),
    disambiguator: Optional[str] = None,
    kind: Optional[str] = None,
    domain: Optional[str] = None,
    github: Optional[str] = None) -> dict[str, Any]:
    """Resolve a reference to one candidate, or report why it cannot.

    Returns ``{"status": "resolved"|"ambiguous"|"not_found", ...}``. The caller
    is expected to stop on anything but ``resolved`` and ask the user.
    """
    name = (name or "").strip()
    if not name:
        return {"status": "not_found", "reason": "empty name", "candidates": []}

    # A supplied domain or GitHub slug *is* a disambiguator: the user has told
    # us which one they mean, so the web cannot pool two entities together.
    if domain:
        clean_domain = registrable_domain(domain)
        docs = list(documents)
        on_domain = [d for d in docs if (d.domain or "") == clean_domain]
        derived = _name_from_title(on_domain[0].title, clean_domain) if on_domain else None
        return {
            "status": "resolved",
            "candidate": Candidate(
                name=derived or name,
                kind=kind or ("org" if looks_like_org(derived or name) else "org"),
                disambiguator=disambiguator or f"domain {clean_domain}",
                domain=clean_domain,
                github=github,
                score=1.0).as_dict(),
            "candidates": [],
        }

    candidates = candidates_from_documents(name, documents, kind=kind)

    if disambiguator:
        needle = disambiguator.strip().casefold()
        narrowed = [
            c
            for c in candidates
            if needle in c.disambiguator.casefold()
            or needle in (c.domain or "").casefold()
            or needle in c.name.casefold()
        ]
        if narrowed:
            candidates = narrowed

    if github and len(candidates) <= 1:
        one = candidates[0] if candidates else Candidate(name=name, kind="org", score=1.0)
        one.github = github
        one.disambiguator = one.disambiguator or f"github {github}"
        return {"status": "resolved", "candidate": one.as_dict(), "candidates": []}

    if len(candidates) == 1:
        return {"status": "resolved", "candidate": candidates[0].as_dict(), "candidates": []}

    # A candidate whose domain carries a word from the name is the entity's own
    # site; an article *about* the entity is not a competing identity. Only
    # collapse when exactly one candidate looks like that, so a genuine
    # same-name clash (two "Sarah Chen" profiles) still stops and asks.
    own_site = [c for c in candidates if c.domain_hit]
    if len(own_site) == 1:
        return {"status": "resolved", "candidate": own_site[0].as_dict(), "candidates": []}

    if not candidates:
        return {
            "status": "not_found",
            "reason": f"no candidate for {name!r}",
            "candidates": [],
        }

    return {
        "status": "ambiguous",
        "reason": f"{len(candidates)} candidates for {name!r}; supply a disambiguator",
        "candidates": [c.as_dict() for c in candidates[:8]],
    }


def ambiguous_message(result: dict[str, Any]) -> str:
    """A short, printable list of candidates for a chat card."""
    lines = [f"Which one? {result.get('reason', 'several candidates')}"]
    for i, cand in enumerate(result.get("candidates", []), start=1):
        detail = cand.get("disambiguator") or cand.get("domain") or "no disambiguator"
        lines.append(f"{i}. {cand['name']}: {detail}")
    lines.append("Reply with the number, or pass `domain=` to pin it.")
    return "\n".join(lines)
