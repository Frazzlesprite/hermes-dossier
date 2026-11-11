"""Plain data types shared by the Dossier pipeline.

Nothing here touches the network, the database or Hermes. That keeps the
pipeline testable without an agent, which is the whole point: the parts that
decide *what counts as evidence* should not need a running harness.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Predicates the schema is allowed to store. Anything else is dropped at
# extraction. Deliberately a closed set: an open predicate space is how a
# dossier turns into a rumour file.
PREDICATES = (
    "founded",
    "employees",
    "hq",
    "ceo",
    "role",  # a person's professional role; the person-kind counterpart to `ceo`
    "funding",
    "product",
    "news",
)

# Predicates that describe one value at a time. Two sources disagreeing on one
# of these is a contradiction worth printing; two sources disagreeing on
# "product" is just two products.
SINGLE_VALUED = frozenset({"founded", "employees", "hq", "ceo", "role", "funding"})

# Source types, weakest to strongest. `search` means "found through search,
# then fetched"; a search result whose page we never fetched is not stored at
# all, so a bare snippet can never appear as evidence.
SOURCE_TYPES = ("search", "news", "github", "official", "registry")

PRIMARY_SOURCES = frozenset({"registry", "official"})

# Sensitive categories. The spec forbids inference or storage of these, so the
# check runs at extraction, before a claim can reach the database.
SENSITIVE_TERMS = frozenset(
    {
        "health",
        "medical",
        "diagnosis",
        "disability",
        "religion",
        "religious",
        "christian",
        "muslim",
        "jewish",
        "hindu",
        "sexual orientation",
        "gay",
        "lesbian",
        "bisexual",
        "transgender",
        "political affiliation",
        "party member",
        "voted for",
        "ethnicity",
        "ethnic",
        "race",
        "racial",
        "trade union",
        "union membership",
    }
)

MAX_QUOTE_CHARS = 500
MIN_QUOTE_CHARS = 12

_WS = re.compile(r"\s+")


def normalise_space(text: str) -> str:
    """Collapse all whitespace so a quote can be matched against page text."""
    return _WS.sub(" ", text or "").strip()


def quote_hash(quote: str) -> str:
    """Stable hash of the normalised quote, used to spot edited evidence."""
    return hashlib.sha256(normalise_space(quote).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Document:
    """A fetched source, normalised. Never a search snippet."""

    url: str
    title: str
    text: str
    source_type: str
    retrieved_at: str
    published_at: Optional[str] = None
    domain: str = ""
    note: Optional[str] = None
    description: Optional[str] = None

    @property
    def is_fetched(self) -> bool:
        return bool(self.text)


@dataclass(frozen=True)
class Evidence:
    source_url: str
    source_type: str
    quote: str
    retrieved_at: str
    published_at: Optional[str] = None

    @property
    def quote_hash(self) -> str:
        return quote_hash(self.quote)

    def as_row(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "source_type": self.source_type,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at,
            "quote": self.quote,
            "quote_hash": self.quote_hash,
        }


@dataclass(frozen=True)
class ClaimDraft:
    """A claim before verification: one value, one quote, one source."""

    predicate: str
    value: str
    evidence: Evidence

    @property
    def key(self) -> tuple[str, str]:
        return (self.predicate, normalise_space(self.value).casefold())


@dataclass
class Claim:
    """A verified claim: one value with every source that supports it."""

    predicate: str
    value: str
    confidence: float
    status: str  # supported | contested | unconfirmed
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.predicate, normalise_space(self.value).casefold())

    @property
    def evidence_ids(self) -> list[int]:
        return [e.get("id", 0) for e in self.evidence]  # type: ignore[union-attr]

    def as_dict(self) -> dict[str, Any]:
        return {
            "predicate": self.predicate,
            "value": self.value,
            "confidence": round(self.confidence, 2),
            "status": self.status,
            "evidence": [
                {
                    "source_url": e.source_url,
                    "source_type": e.source_type,
                    "published_at": e.published_at,
                    "retrieved_at": e.retrieved_at,
                    "quote": e.quote,
                    "quote_hash": e.quote_hash,
                }
                for e in self.evidence
            ],
        }


@dataclass(frozen=True)
class Bullet:
    """One printable line. It cannot exist without evidence."""

    text: str
    evidence: tuple[Evidence, ...]

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError("a bullet with no evidence is not printable")


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    bullets: tuple[Bullet, ...] = ()
    note: Optional[str] = None


@dataclass
class Brief:
    """A complete, print-ready brief."""

    entity: dict[str, Any]
    headline: str
    sections: list[Section]
    questions: list[str]
    sources: list[Evidence]
    generated_at: str
    notes: list[str] = field(default_factory=list)
    purpose: str = ""
    context: str = "general"

    @property
    def claim_count(self) -> int:
        return sum(len(s.bullets) for s in self.sections)

    def as_dict(self) -> dict[str, Any]:
        """Flat, JSON-safe view. Stored with the snapshot so the dashboard can
        serve a brief without importing the pipeline."""
        return {
            "headline": self.headline,
            "questions": list(self.questions),
            "generated_at": self.generated_at,
            "purpose": self.purpose,
            "context": self.context,
            "notes": list(self.notes),
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "note": section.note,
                    "bullets": [
                        {
                            "text": bullet.text,
                            "sources": sorted({e.source_url for e in bullet.evidence}),
                        }
                        for bullet in section.bullets
                    ],
                }
                for section in self.sections
            ],
        }
