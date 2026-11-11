"""The pipeline: resolve, plan, fan out, extract, verify, compose, store.

`build` is the only function the tools, the slash command and the dashboard all
call, so every surface produces the same brief from the same rules. Network,
model access and the database are all injected, which is what makes the whole
thing testable without an agent.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Optional

from . import contexts
from . import plan
from . import resolve as resolve_mod
from . import store
from .adapters.base import Policy, now_iso
from .adapters.github import collect_github
from .adapters.news import collect_news
from .adapters.official import collect_official
from .adapters.registry import collect_registry
from .adapters.search import SearchFn, collect_search
from .compose import compose
from .extract import ExtractionReport, extract, extract_with_llm
from .models import SINGLE_VALUED, SOURCE_TYPES, Claim, Document
from .render import render_card, render_html, render_pdf
from .verify import upgrade_source_type, verify

DEFAULTS = {
    "sources_per_brief": 12,
    "freshness_days": 90,
    "retention_days": 90,
    "allow_people": True,
    "user_agent": "Dossier/0.1 (+https://github.com/Frazzlesprite/hermes-dossier)",
    "country": "",
    "registry_contact": "",
}


@dataclass
class Config:
    sources_per_brief: int = 12
    freshness_days: int = 90
    retention_days: int = 90
    allow_people: bool = True
    user_agent: str = DEFAULTS["user_agent"]
    country: str = ""
    registry_contact: str = ""

    @classmethod
    def from_mapping(cls, values: Optional[dict[str, Any]]) -> "Config":
        values = {**DEFAULTS, **(values or {})}
        return cls(
            sources_per_brief=max(1, min(int(values["sources_per_brief"]), 40)),
            freshness_days=max(1, int(values["freshness_days"])),
            retention_days=max(1, int(values["retention_days"])),
            allow_people=bool(values["allow_people"]),
            user_agent=str(values["user_agent"]),
            country=str(values.get("country") or ""),
            registry_contact=str(values.get("registry_contact") or ""))

    def policy(self) -> Policy:
        return Policy(user_agent=self.user_agent)


def upsert_entity(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    *,
    purpose: Optional[str],
    retention_days: int,
    context: Optional[str] = None,
) -> int:
    existing = conn.execute(
        "SELECT id FROM entities WHERE lower(canonical_name) = lower(?) AND COALESCE(domain, '') = COALESCE(?, '')",
        (candidate["name"], candidate.get("domain"))).fetchone()
    stamp = now_iso()
    if existing:
        conn.execute(
            "UPDATE entities SET aliases = COALESCE(?, aliases), github = COALESCE(?, github), "
            "disambiguator = COALESCE(?, disambiguator), purpose = COALESCE(?, purpose), "
            "context = COALESCE(?, context), "
            "retention_days = COALESCE(?, retention_days), updated_at = ? WHERE id = ?",
            (
                json.dumps(candidate.get("aliases") or []) if candidate.get("aliases") else None,
                candidate.get("github"),
                candidate.get("disambiguator"),
                purpose,
                context,
                retention_days,
                stamp,
                existing["id"]))
        conn.commit()
        return int(existing["id"])

    cursor = conn.execute(
        "INSERT INTO entities (kind, canonical_name, aliases, domain, registry_id, country, "
        "disambiguator, purpose, context, retention_days, github, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            candidate.get("kind") or "org",
            candidate["name"],
            json.dumps(candidate.get("aliases") or []),
            candidate.get("domain"),
            candidate.get("registry_id"),
            candidate.get("country"),
            candidate.get("disambiguator"),
            purpose,
            context,
            retention_days,
            candidate.get("github"),
            stamp,
            stamp))
    conn.commit()
    return int(cursor.lastrowid)


def persist_claims(conn: sqlite3.Connection, entity_id: int, claims: list[Claim]) -> list[int]:
    stamp = now_iso()
    ids: list[int] = []
    for claim in claims:
        row = conn.execute(
            "SELECT id FROM claims WHERE entity_id = ? AND predicate = ? AND value = ?",
            (entity_id, claim.predicate, claim.value)).fetchone()
        if row:
            claim_id = int(row["id"])
            conn.execute(
                "UPDATE claims SET confidence = ?, status = ?, last_seen = ? WHERE id = ?",
                (claim.confidence, claim.status, stamp, claim_id))
        else:
            claim_id = int(
                conn.execute(
                    "INSERT INTO claims (entity_id, predicate, value, confidence, status, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (entity_id, claim.predicate, claim.value, claim.confidence, claim.status, stamp, stamp)).lastrowid
            )
        ids.append(claim_id)
        for item in claim.evidence:
            conn.execute(
                "INSERT INTO evidence (claim_id, source_url, source_type, published_at, retrieved_at, quote, quote_hash) "
                "SELECT ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS ("
                "  SELECT 1 FROM evidence WHERE claim_id = ? AND quote_hash = ? AND source_url = ?)",
                (
                    claim_id,
                    item.source_url,
                    item.source_type,
                    item.published_at,
                    item.retrieved_at,
                    item.quote,
                    item.quote_hash,
                    claim_id,
                    item.quote_hash,
                    item.source_url))
    conn.commit()
    return ids


def _dedupe_documents(documents: list[Document], limit: int) -> list[Document]:
    """One document per URL, keeping the strongest classification.

    The same page is often fetched twice, once by discovery, once by the news
    query. Keeping whichever arrived first made a dated article look like a
    generic search result, so the ranking order decides instead.
    """
    rank = {source_type: index for index, source_type in enumerate(SOURCE_TYPES)}
    best: dict[str, Document] = {}
    order: list[str] = []
    for doc in documents:
        key = doc.url.split("#")[0].rstrip("/")
        if not doc.text.strip():
            continue
        if key not in best:
            best[key] = doc
            order.append(key)
            continue
        if rank.get(doc.source_type, 0) > rank.get(best[key].source_type, 0):
            best[key] = doc

    out: list[Document] = []
    for key in order:
        out.append(best[key])
        if len(out) >= limit:
            break
    return out


def _guard_name_collisions(
    documents: list[Document], candidate: dict[str, Any], notes: list[str]
) -> list[Document]:
    """Drop third-party pages that only share a one-word name.

    A single-word name is the collision-prone case: "Kalamari" is a Canberra
    app studio, a Paris PR agency that renamed itself, a Greek restaurant and a
    song. For those names we require a page to name the entity's own domain, so
    a random homonym cannot contribute claims. Multi-word names ("Acme
    Robotics", "Valve Corporation") are distinctive enough to keep their
    coverage, and a legal suffix counts as a word here: `name_tokens` strips
    "Corporation", and stripping it made the guard throw away every news
    article about Valve for not containing its domain.
    """
    name = candidate.get("name") or ""
    if len([word for word in re.split(r"\s+", name.strip()) if word]) >= 2:
        return documents

    domain = (candidate.get("domain") or "").casefold()
    kept: list[Document] = []
    dropped = 0
    for doc in documents:
        if doc.source_type in ("official", "registry") or (domain and doc.domain == domain):
            kept.append(doc)
        elif domain and domain in doc.text.casefold():
            kept.append(doc)
        else:
            dropped += 1

    if dropped:
        notes.append(
            f"collision guard: dropped {dropped} source(s) that mention {name!r} but not "
            f"{domain or 'its own domain'}; a one-word name is ambiguous"
        )
    return kept


_WALL_MARKERS = (
    "making sure you're not a bot",
    "checking your browser",
    "verify you are human",
    "enable javascript and cookies",
    "protect the server against",
    "just a moment",
)


def _drop_interstitials(documents: list[Document], notes: list[str]) -> list[Document]:
    """An anti-bot wall is not a source.

    Anubis, Cloudflare and friends answer a 200 with a short page about proving
    you are human. Parsed like an article, that page yielded a one-line such as
    "You are seeing this because the administrator of this website has set up
    Anubis", which is a quote about a captcha. Dropped and counted instead.
    """
    kept: list[Document] = []
    dropped = 0
    for doc in documents:
        blob = f"{doc.title} {doc.text}".casefold()
        if len(doc.text) < 2000 and any(marker in blob for marker in _WALL_MARKERS):
            dropped += 1
            continue
        kept.append(doc)
    if dropped:
        notes.append(
            f"dropped {dropped} anti-bot interstitial page(s): a challenge page is not a source"
        )
    return kept


def _registry_id_from(documents: list[Document]) -> Optional[str]:
    """The first statutory identifier the registry pages state, if any."""
    for doc in documents:
        if doc.source_type != "registry":
            continue
        for pattern in (r"\bCIK\s+(\d{5,12})", r"\bABN\s+([\d ]{11,17})", r"company number\s+([A-Z0-9]{6,10})"):
            match = re.search(pattern, doc.text)
            if match:
                return match.group(1).strip()
    return None


def build(
    name: str,
    *,
    conn: sqlite3.Connection,
    search_fn: Optional[SearchFn] = None,
    llm: Any = None,
    config: Optional[Config] = None,
    disambiguator: Optional[str] = None,
    domain: Optional[str] = None,
    github: Optional[str] = None,
    kind: Optional[str] = None,
    purpose: Optional[str] = None,
    context: Optional[str] = None,
    memory_context: Optional[str] = None,
    abn_guid: str = "",
    companies_house_key: str = "",
    registry_contact: str = "") -> dict[str, Any]:
    config = config or Config()
    policy = config.policy()
    notes: list[str] = []

    if kind == "person":
        if not config.allow_people:
            return {
                "status": "refused",
                "error": "Dossiers on people are disabled (allow_people=false).",
            }
        if not (purpose or "").strip():
            return {
                "status": "refused",
                "error": (
                    "A dossier on a person needs a stated purpose, the professional context "
                    "(e.g. purpose='interview for the platform role on Thursday'). "
                    "Without one it is surveillance, not research."
                ),
            }

    # 1. Resolve. Only fetch enough to tell one entity from another.
    discovery: list[Document] = []
    if domain:
        official = collect_official(domain, policy)
        discovery = official["documents"]
        notes.extend(official["notes"])
    elif search_fn is not None:
        found = collect_search(f'"{name}"', search_fn, limit=5, policy=policy)
        discovery = found["documents"]
        notes.extend(found["notes"])

    resolution = resolve_mod.resolve(
        name,
        documents=discovery,
        disambiguator=disambiguator,
        kind=kind,
        domain=domain,
        github=github)
    if resolution["status"] != "resolved":
        return {
            "status": resolution["status"],
            "error": resolve_mod.ambiguous_message(resolution),
            "candidates": resolution.get("candidates", []),
            "notes": notes,
        }

    candidate = resolution["candidate"]
    context_id = contexts.normalise(context) or contexts.infer(purpose, candidate.get("kind") or "org")
    entity_id = upsert_entity(
        conn,
        candidate,
        purpose=purpose,
        retention_days=config.retention_days,
        context=context_id,
    )

    # 2. Plan and fan out.
    queries = plan.search_queries(candidate["name"], kind=candidate.get("kind", "org"), domain=candidate.get("domain"))
    collected: list[Document] = list(discovery)

    if candidate.get("domain"):
        official = collect_official(candidate["domain"], policy)
        collected.extend(official["documents"])
        notes.extend(official["notes"])

    if search_fn is None:
        # Say it once, plainly, instead of letting every adapter repeat it.
        notes.append(
            "no search backend in this context: only the official site and GitHub were read; "
            "run /dossier refresh in a session for search and news"
        )
    else:
        for query in queries[:2]:
            found = collect_search(query, search_fn, limit=3, policy=policy)
            collected.extend(found["documents"])
            notes.extend(found["notes"])

        news = collect_news(
            candidate["name"],
            search_fn,
            limit=3,
            freshness_days=config.freshness_days,
            policy=policy)
        collected.extend(news["documents"])
        notes.extend(news["notes"])

    if candidate.get("github") or candidate.get("domain"):
        gh = collect_github(candidate.get("github"), policy=policy, website=candidate.get("domain"))
        collected.extend(gh["documents"])
        notes.extend(gh["notes"])

    registry = collect_registry(
        candidate["name"],
        country=(candidate.get("country") or config.country) or None,
        policy=policy,
        abn_guid=abn_guid,
        companies_house_key=companies_house_key,
        contact=registry_contact or config.registry_contact)
    collected.extend(registry["documents"])
    notes.extend(registry["notes"])

    documents = _dedupe_documents(collected, config.sources_per_brief)
    documents = _drop_interstitials(documents, notes)
    documents = _guard_name_collisions(documents, candidate, notes)
    documents = [upgrade_source_type(d, candidate.get("domain")) for d in documents]

    # 3. Extract and verify.
    report: ExtractionReport = extract(
        documents,
        kind=candidate.get("kind") or "org",
        entity_name=candidate.get("name") or "",
        entity_domain=candidate.get("domain") or "",
    )
    if llm is not None:
        for doc in documents[:6]:
            extract_with_llm(doc, llm, report)

    verification = verify(report.claims)
    notes.extend(verification.notes)

    # 4. Compose, render, store.
    stamp = now_iso()
    entity = dict(conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone())
    brief = compose(
        entity,
        verification.claims,
        generated_at=stamp,
        freshness_days=config.freshness_days,
        memory_context=memory_context,
        notes=notes,
        purpose=purpose,
        context=context_id)
    html = render_html(brief)
    pdf = render_pdf(brief)
    persist_claims(conn, entity_id, verification.claims)

    registry_id = _registry_id_from(registry["documents"])
    if registry_id:
        conn.execute(
            "UPDATE entities SET registry_id = COALESCE(registry_id, ?), updated_at = ? WHERE id = ?",
            (registry_id, stamp, entity_id))
        conn.commit()

    snapshot_id = store.save_snapshot(
        conn, entity_id, stamp, html, verification.claims, pdf,
        brief_json=json.dumps(brief.as_dict(), ensure_ascii=False),
    )
    conn.execute("UPDATE watchlist SET last_run = ? WHERE entity_id = ?", (stamp, entity_id))
    conn.commit()
    diff = store.latest_diff(conn, entity_id)

    return {
        "status": "ok",
        "entity_id": entity_id,
        "snapshot_id": snapshot_id,
        "entity": {"id": entity_id, "name": entity["canonical_name"], "kind": entity["kind"], "domain": entity.get("domain")},
        "headline": brief.headline,
        "purpose": purpose or "",
        "context": context_id,
        "context_label": contexts.label(context_id),
        "questions": brief.questions,
        "claims": [c.as_dict() for c in verification.claims],
        "html": html,
        "pdf": pdf,
        "card": render_card(brief),
        "diff": diff,
        "notes": notes,
        "rejected": report.rejected[:20],
        "counts": {
            "documents": len(documents),
            "claims": len(verification.claims),
            "contested": verification.contested,
            "rejected": len(report.rejected),
        },
    }
