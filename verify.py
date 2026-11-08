"""Verification: confidence, deduplication, contradictions.

The rules are the spec's table, implemented literally, because the table is the
product. A contested claim is never resolved to a winner, both values survive
with their own sources and dates, and composition prints both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .models import (
    PRIMARY_SOURCES,
    SINGLE_VALUED,
    Claim,
    ClaimDraft,
    Document,
    Evidence,
    normalise_space)

TWO_PRIMARY = 0.95
ONE_PRIMARY = 0.80
ONE_SECONDARY = 0.60
CONTESTED = 0.50
UNCONFIRMED = 0.40

SECONDARY_SOURCES = frozenset({"news", "github", "search"})

_ORDER = {p: i for i, p in enumerate(("product", "hq", "founded", "employees", "ceo", "funding", "news"))}


@dataclass
class VerificationReport:
    claims: list[Claim]
    contested: int = 0
    notes: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = []


def upgrade_source_type(doc: Document, entity_domain: Optional[str]) -> Document:
    """A search result on the entity's own domain *is* their own site."""
    if not entity_domain or doc.source_type != "search" or not doc.domain:
        return doc
    domain = doc.domain
    if domain == entity_domain or domain.endswith("." + entity_domain):
        return Document(
            url=doc.url,
            title=doc.title,
            text=doc.text,
            source_type="official",
            retrieved_at=doc.retrieved_at,
            published_at=doc.published_at,
            domain=doc.domain,
            note=doc.note)
    return doc


def _confidence(evidence: list[Evidence]) -> float:
    primary = {(e.source_type, _host(e.source_url)) for e in evidence if e.source_type in PRIMARY_SOURCES}
    if len(primary) >= 2:
        return TWO_PRIMARY
    if len(primary) == 1:
        # Two independent pages on the same primary site still count as one
        # primary source: they share an author.
        return ONE_PRIMARY
    secondary = {(e.source_type, _host(e.source_url)) for e in evidence if e.source_type in SECONDARY_SOURCES}
    if len(secondary) >= 2:
        return ONE_SECONDARY + 0.1
    if len(secondary) == 1:
        return ONE_SECONDARY
    return UNCONFIRMED


def _host(url: str) -> str:
    return url.split("/")[2].lower() if "://" in url else url


def _dedupe(evidence: Iterable[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str]] = set()
    out: list[Evidence] = []
    for item in evidence:
        key = (normalise_space(item.source_url), item.quote_hash)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    out.sort(key=lambda e: (e.published_at or "", e.retrieved_at or ""), reverse=True)
    return out


def verify(drafts: Iterable[ClaimDraft]) -> VerificationReport:
    grouped: dict[tuple[str, str], list[Evidence]] = {}
    values_by_predicate: dict[str, list[str]] = {}
    display_value: dict[tuple[str, str], str] = {}
    urls_by_value: dict[tuple[str, str], set[str]] = {}

    for draft in drafts:
        grouped.setdefault(draft.key, []).append(draft.evidence)
        display_value.setdefault(draft.key, draft.value)
        urls_by_value.setdefault(draft.key, set()).add(draft.evidence.source_url)
        bucket = values_by_predicate.setdefault(draft.predicate, [])
        if draft.key[1] not in {normalise_space(v).casefold() for v in bucket}:
            bucket.append(draft.value)

    # Disagreement means *different sources* disagree. One page quoting a
    # headcount for 2003, 2012 and 2021 is a timeline, not a contradiction.
    contested_predicates = set()
    historical_predicates = set()
    for predicate, values in values_by_predicate.items():
        if predicate not in SINGLE_VALUED or len(values) < 2:
            continue
        keys = [
            (predicate, normalise_space(value).casefold())
            for value in values
        ]
        sources = set().union(*(urls_by_value.get(key, set()) for key in keys))
        if len(sources) >= 2:
            contested_predicates.add(predicate)
        else:
            historical_predicates.add(predicate)

    # A product value contained in another product value is the same claim said
    # shorter ("warehouse robots" inside "Acme Robotics builds warehouse
    # robots"). Keep the fuller one and fold the evidence in.
    product_keys = [key for key in grouped if key[0] == "product"]
    dropped: set[tuple[str, str]] = set()
    for short in product_keys:
        short_value = normalise_space(display_value[short]).casefold()
        for long in product_keys:
            if short == long or long in dropped or short in dropped:
                continue
            long_value = normalise_space(display_value[long]).casefold()
            if len(long_value) > len(short_value) and short_value in long_value:
                grouped[long].extend(grouped[short])
                dropped.add(short)
                break
    for key in dropped:
        grouped.pop(key, None)

    claims: list[Claim] = []
    for key, evidence in grouped.items():
        predicate, _ = key
        merged = _dedupe(evidence)
        confidence = _confidence(merged)
        status = "unconfirmed" if confidence <= UNCONFIRMED else "supported"
        if predicate in contested_predicates:
            status = "contested"
            confidence = CONTESTED
        elif predicate in historical_predicates:
            # One source, several values: a series, not a disagreement.
            status = "unconfirmed"
            confidence = UNCONFIRMED
        claims.append(
            Claim(
                predicate=predicate,
                value=display_value[key],
                confidence=confidence,
                status=status,
                evidence=merged)
        )

    claims.sort(key=lambda c: (-c.confidence, _ORDER.get(c.predicate, 99), c.value.casefold()))
    notes = []
    for predicate in sorted(contested_predicates):
        notes.append(f"contested: {predicate} has {len(values_by_predicate[predicate])} conflicting values")
    for predicate in sorted(historical_predicates):
        notes.append(
            f"unconfirmed: {predicate} has {len(values_by_predicate[predicate])} values from a single source "
            "(read as a series, not agreement)"
        )
    return VerificationReport(claims=claims, contested=len(contested_predicates), notes=notes)


def contested_groups(claims: Iterable[Claim]) -> dict[str, list[Claim]]:
    groups: dict[str, list[Claim]] = {}
    for claim in claims:
        if claim.status == "contested":
            groups.setdefault(claim.predicate, []).append(claim)
    return groups
