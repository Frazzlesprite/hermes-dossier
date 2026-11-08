"""Composition: the brief, assembled only from verified claims.

There is no generative step here on purpose. Every line is a template applied to
a claim that already has evidence, so an unsourced sentence is impossible by
construction rather than by prompt discipline. `Bullet` refuses to exist without
evidence, and `compose` never catches that.

The one thing that is not a claim is the "why they matter to you" line, which
comes from Hermes memory. It is quoted as memory, never as fact.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from .models import Brief, Bullet, Claim, Evidence, Section
from .verify import contested_groups

FACT_ORDER = ("founded", "employees", "hq", "ceo", "funding", "product")
FACT_LABEL = {
    "founded": "Founded",
    "employees": "Size",
    "hq": "HQ",
    "ceo": "Leadership",
    "funding": "Funding",
    "product": "What they do",
}

RISK_WORDS = (
    "layoff",
    "lawsuit",
    "sued",
    "investigation",
    "recall",
    "strike",
    "loss",
    "downgrade",
    "resigned",
    "stepped down",
    "fraud",
    "insolven",
    "administration",
)


def _source_ref(evidence: Evidence, index: dict[str, int]) -> str:
    number = index.setdefault(evidence.source_url, len(index) + 1)
    date = evidence.published_at or evidence.retrieved_at[:10]
    return f"[{number}, {date}]"


def source_index(claims: Iterable[Claim]) -> dict[str, int]:
    index: dict[str, int] = {}
    for claim in claims:
        for item in claim.evidence:
            _source_ref(item, index)
    return index


def _bullet(text: str, evidence: Sequence[Evidence]) -> Bullet:
    return Bullet(text=text, evidence=tuple(evidence))


def _facts(claims: Sequence[Claim], index: dict[str, int]) -> list[Bullet]:
    out: list[Bullet] = []
    for predicate in FACT_ORDER:
        for claim in claims:
            if claim.predicate != predicate or claim.status == "contested":
                continue
            refs = " ".join(_source_ref(e, index) for e in claim.evidence[:2])
            out.append(_bullet(f"**{FACT_LABEL[predicate]}:** {claim.value} {refs}".strip(), claim.evidence[:2]))
    return out


def _recent(claims: Sequence[Claim], index: dict[str, int], freshness_days: int) -> list[Bullet]:
    import time

    cutoff = time.time() - freshness_days * 86400
    out: list[Bullet] = []
    for claim in claims:
        if claim.predicate != "news":
            continue
        dated = [e for e in claim.evidence if e.published_at]
        if not dated:
            continue
        newest = max(dated, key=lambda e: e.published_at or "")
        try:
            when = time.strptime((newest.published_at or "")[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if time.mktime(when) < cutoff:
            continue
        refs = " ".join(_source_ref(e, index) for e in dated[:2])
        out.append(_bullet(f"{claim.value} — {newest.published_at} {refs}", dated[:2]))
    out.sort(key=lambda b: b.text, reverse=True)
    return out


def _contested(claims: Sequence[Claim], index: dict[str, int]) -> list[Bullet]:
    out: list[Bullet] = []
    for predicate, group in sorted(contested_groups(claims).items()):
        pieces = []
        evidence: list[Evidence] = []
        for claim in group:
            for item in claim.evidence[:1]:
                date = item.published_at or item.retrieved_at[:10]
                pieces.append(f"{claim.value} ({item.source_url}, {date})")
                evidence.append(item)
        if not pieces:
            continue
        out.append(_bullet(f"**{predicate.title()} — sources disagree:** " + "; ".join(pieces), evidence))
    return out


def _risks(claims: Sequence[Claim], index: dict[str, int]) -> list[Bullet]:
    out: list[Bullet] = []
    seen: set[str] = set()
    for claim in claims:
        if claim.status == "contested" and claim.predicate in {"ceo", "funding", "employees", "founded"}:
            key = f"contested-{claim.predicate}"
            if key in seen:
                continue
            seen.add(key)
            evidence = [e for c in claims if c.predicate == claim.predicate for e in c.evidence][:2]
            out.append(_bullet(f"Sources disagree about {claim.predicate}; confirm it before relying on it.", evidence))
            continue
        blob = claim.value.casefold()
        if claim.predicate == "news" and any(word in blob for word in RISK_WORDS):
            out.append(_bullet(f"Reported: {claim.value}", claim.evidence[:2]))
    return out


def _questions(
    name: str,
    claims: Sequence[Claim],
    *,
    contested: dict[str, list[Claim]],
    freshness_days: int,
) -> list[str]:
    present = {c.predicate for c in claims if c.status != "unconfirmed"}
    questions: list[str] = []

    for predicate, group in sorted(contested.items()):
        values = ", ".join(sorted({c.value for c in group}))
        questions.append(f"Why do sources disagree about {predicate} ({values})?")
        if len(questions) == 3:
            return questions

    for predicate, question in (
        ("ceo", f"Who currently runs {name}, and since when?"),
        ("employees", f"How many people work at {name} today?"),
        ("funding", f"Has {name} raised money, and on what terms?"),
        ("founded", f"When was {name} actually founded?"),
        ("product", f"What exactly does {name} sell, and to whom?"),
        ("hq", f"Where is {name} actually based?"),
    ):
        if predicate not in present:
            questions.append(question)
        if len(questions) == 3:
            return questions

    if len(questions) < 3:
        questions.append(f"What has changed at {name} in the last {freshness_days} days?")
    return questions[:3]


def _headline(name: str, claims: Sequence[Claim]) -> str:
    for predicate in ("product", "hq", "founded"):
        for claim in claims:
            if claim.predicate == predicate and claim.status != "contested":
                if claim.value.casefold().startswith(name.casefold()) or name.casefold() in claim.value.casefold()[:40]:
                    return claim.value
                return f"{name} — {claim.value}"
    return f"{name} — no supported one-line description yet"


def compose(
    entity: dict,
    claims: Sequence[Claim],
    *,
    generated_at: str,
    freshness_days: int = 90,
    memory_context: Optional[str] = None,
    notes: Optional[Iterable[str]] = None,
) -> Brief:
    name = entity.get("canonical_name") or "This entity"
    index = source_index(claims)
    claims = list(claims)

    sections: list[Section] = []

    headline = _headline(name, claims)
    best = next((c for c in claims if c.predicate in {"product", "hq", "founded"}), None)
    sections.append(
        Section(
            id="one_line",
            title="One line",
            bullets=(_bullet(headline, best.evidence[:1]),) if best else (),
        )
    )

    sections.append(
        Section(
            id="why",
            title="Why they matter to you",
            note=memory_context or "Nothing in your Hermes memory connects this entity to current work.",
        )
    )

    facts = _facts(claims, index)
    sections.append(Section(id="facts", title="Facts", bullets=tuple(facts)))

    recent = _recent(claims, index, freshness_days)
    sections.append(Section(id="recent", title="Recent", bullets=tuple(recent)))

    contested = _contested(claims, index)
    sections.append(
        Section(
            id="contested",
            title="Contested or unconfirmed",
            bullets=tuple(contested),
            note=None if contested else "No contradictions found across the sources fetched.",
        )
    )

    risks = _risks(claims, index)
    sections.append(
        Section(id="risks", title="Risks", bullets=tuple(risks), note=None if risks else "No risk-bearing claim was supported.")
    )

    groups = contested_groups(claims)
    sections.append(
        Section(
            id="questions",
            title="Three questions to ask",
            note="\n".join(f"{i}. {q}" for i, q in enumerate(_questions(name, claims, contested=groups, freshness_days=freshness_days), start=1)),
        )
    )

    sources: list[Evidence] = []
    seen: set[tuple[str, str]] = set()
    for claim in claims:
        for item in claim.evidence:
            key = (item.source_url, item.quote_hash)
            if key in seen:
                continue
            seen.add(key)
            sources.append(item)

    return Brief(
        entity=entity,
        headline=headline,
        sections=sections,
        questions=_questions(name, claims, contested=groups, freshness_days=freshness_days),
        sources=sources,
        generated_at=generated_at,
        notes=list(notes or []),
    )
