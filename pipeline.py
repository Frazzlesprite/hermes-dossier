"""The pipeline: resolve, plan, fan out, extract, verify, compose, store.

`build` is the only function the tools, the slash command and the dashboard all
call, so every surface produces the same brief from the same rules. Network,
model access and the database are all injected, which is what makes the whole
thing testable without an agent.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Optional

from . import plan
from . import resolve as resolve_mod
from . import store
from .adapters.base import Policy, now_iso
from .adapters.github import collect_github
from .adapters.news import collect_news
from .adapters.official import collect_official
from .adapters.search import SearchFn, collect_search
from .compose import compose
from .extract import ExtractionReport, extract, extract_with_llm
from .models import SINGLE_VALUED, SOURCE_TYPES, Claim, Document
from .render import render_card, render_html
from .verify import upgrade_source_type, verify

DEFAULTS = {
    "sources_per_brief": 12,
    "freshness_days": 90,
    "retention_days": 90,
    "allow_people": True,
    "user_agent": "Dossier/0.1 (+https://github.com/Frazzlesprite/dossier-plugin)",
}


@dataclass
class Config:
    sources_per_brief: int = 12
    freshness_days: int = 90
    retention_days: int = 90
    allow_people: bool = True
    user_agent: str = DEFAULTS["user_agent"]

    @classmethod
    def from_mapping(cls, values: Optional[dict[str, Any]]) -> "Config":
        values = {**DEFAULTS, **(values or {})}
        return cls(
            sources_per_brief=max(1, min(int(values["sources_per_brief"]), 40)),
            freshness_days=max(1, int(values["freshness_days"])),
            retention_days=max(1, int(values["retention_days"])),
            allow_people=bool(values["allow_people"]),
            user_agent=str(values["user_agent"]),
        )

    def policy(self) -> Policy:
        return Policy(user_agent=self.user_agent)


def upsert_entity(conn: sqlite3.Connection, candidate: dict[str, Any], *, purpose: Optional[str], retention_days: int) -> int:
    existing = conn.execute(
        "SELECT id FROM entities WHERE lower(canonical_name) = lower(?) AND COALESCE(domain, '') = COALESCE(?, '')",
        (candidate["name"], candidate.get("domain")),
    ).fetchone()
    stamp = now_iso()
    if existing:
        conn.execute(
            "UPDATE entities SET aliases = COALESCE(?, aliases), github = COALESCE(?, github), "
            "disambiguator = COALESCE(?, disambiguator), purpose = COALESCE(?, purpose), "
            "retention_days = COALESCE(?, retention_days), updated_at = ? WHERE id = ?",
            (
                json.dumps(candidate.get("aliases") or []) if candidate.get("aliases") else None,
                candidate.get("github"),
                candidate.get("disambiguator"),
                purpose,
                retention_days,
                stamp,
                existing["id"],
            ),
        )
        conn.commit()
        return int(existing["id"])

    cursor = conn.execute(
        "INSERT INTO entities (kind, canonical_name, aliases, domain, registry_id, country, "
        "disambiguator, purpose, retention_days, github, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            candidate.get("kind") or "org",
            candidate["name"],
            json.dumps(candidate.get("aliases") or []),
            candidate.get("domain"),
            candidate.get("registry_id"),
            candidate.get("country"),
            candidate.get("disambiguator"),
            purpose,
            retention_days,
            candidate.get("github"),
            stamp,
            stamp,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def persist_claims(conn: sqlite3.Connection, entity_id: int, claims: list[Claim]) -> list[int]:
    stamp = now_iso()
    ids: list[int] = []
    for claim in claims:
        row = conn.execute(
            "SELECT id FROM claims WHERE entity_id = ? AND predicate = ? AND value = ?",
            (entity_id, claim.predicate, claim.value),
        ).fetchone()
        if row:
            claim_id = int(row["id"])
            conn.execute(
                "UPDATE claims SET confidence = ?, status = ?, last_seen = ? WHERE id = ?",
                (claim.confidence, claim.status, stamp, claim_id),
            )
        else:
            claim_id = int(
                conn.execute(
                    "INSERT INTO claims (entity_id, predicate, value, confidence, status, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (entity_id, claim.predicate, claim.value, claim.confidence, claim.status, stamp, stamp),
                ).lastrowid
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
                    item.source_url,
                ),
            )
    conn.commit()
    return ids


def _dedupe_documents(documents: list[Document], limit: int) -> list[Document]:
    """One document per URL, keeping the strongest classification.

    The same page is often fetched twice — once by discovery, once by the news
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
    memory_context: Optional[str] = None,
) -> dict[str, Any]:
    config = config or Config()
    policy = config.policy()
    notes: list[str] = []

    if kind == "person" and not config.allow_people:
        return {
            "status": "refused",
            "error": "Dossiers on people are disabled (allow_people=false).",
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
        github=github,
    )
    if resolution["status"] != "resolved":
        return {
            "status": resolution["status"],
            "error": resolve_mod.ambiguous_message(resolution),
            "candidates": resolution.get("candidates", []),
            "notes": notes,
        }

    candidate = resolution["candidate"]
    entity_id = upsert_entity(conn, candidate, purpose=purpose, retention_days=config.retention_days)

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
            policy=policy,
        )
        collected.extend(news["documents"])
        notes.extend(news["notes"])

    if candidate.get("github") or candidate.get("domain"):
        gh = collect_github(candidate.get("github"), policy=policy, website=candidate.get("domain"))
        collected.extend(gh["documents"])
        notes.extend(gh["notes"])

    documents = _dedupe_documents(collected, config.sources_per_brief)
    documents = [upgrade_source_type(d, candidate.get("domain")) for d in documents]

    # 3. Extract and verify.
    report: ExtractionReport = extract(documents)
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
    )
    html = render_html(brief)
    persist_claims(conn, entity_id, verification.claims)
    snapshot_id = store.save_snapshot(conn, entity_id, stamp, html, verification.claims)
    diff = store.latest_diff(conn, entity_id)

    return {
        "status": "ok",
        "entity_id": entity_id,
        "snapshot_id": snapshot_id,
        "entity": {"id": entity_id, "name": entity["canonical_name"], "kind": entity["kind"], "domain": entity.get("domain")},
        "headline": brief.headline,
        "questions": brief.questions,
        "claims": [c.as_dict() for c in verification.claims],
        "html": html,
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
