"""Composition: a bullet without evidence cannot exist."""

from __future__ import annotations

import pytest

from dossier.compose import compose
from dossier.models import Bullet, Claim, ClaimDraft, Evidence
from dossier.verify import verify


def _evidence(url: str = "https://acme.example/about", source_type: str = "official") -> Evidence:
    return Evidence(
        source_url=url,
        source_type=source_type,
        quote="Acme employs 120 employees.",
        retrieved_at="2026-11-08T00:00:00Z",
        published_at="2026-10-01",
    )


def test_a_bullet_requires_evidence():
    with pytest.raises(ValueError):
        Bullet(text="Acme is probably fine.", evidence=())


def test_composition_never_emits_an_unsourced_bullet():
    drafts = [
        ClaimDraft(predicate="employees", value="120", evidence=_evidence()),
        ClaimDraft(predicate="hq", value="Canberra", evidence=_evidence()),
    ]
    claims = verify(drafts).claims
    brief = compose({"canonical_name": "Acme Robotics"}, claims, generated_at="2026-11-08T00:00:00Z")

    for section in brief.sections:
        for bullet in section.bullets:
            assert bullet.evidence, f"section {section.id} produced an unsourced bullet"


def test_headline_comes_from_a_supported_claim():
    claims = verify([ClaimDraft(predicate="product", value="warehouse robots", evidence=_evidence())]).claims
    brief = compose({"canonical_name": "Acme Robotics"}, claims, generated_at="2026-11-08T00:00:00Z")
    assert "warehouse robots" in brief.headline


def test_headline_admits_when_nothing_is_supported():
    claims = verify([]).claims
    brief = compose({"canonical_name": "Acme Robotics"}, claims, generated_at="2026-11-08T00:00:00Z")
    assert "no supported one-line description" in brief.headline


def test_contested_claims_are_printed_side_by_side():
    claims = verify(
        [
            ClaimDraft(predicate="employees", value="120", evidence=_evidence()),
            ClaimDraft(
                predicate="employees",
                value="160",
                evidence=_evidence("https://news.example/a", "news"),
            ),
        ]
    ).claims
    brief = compose({"canonical_name": "Acme Robotics"}, claims, generated_at="2026-11-08T00:00:00Z")
    contested = next(s for s in brief.sections if s.id == "contested")
    assert len(contested.bullets) == 1
    text = contested.bullets[0].text
    assert "120" in text and "160" in text


def test_three_questions_are_derived_from_gaps():
    claims = verify([ClaimDraft(predicate="hq", value="Canberra", evidence=_evidence())]).claims
    brief = compose({"canonical_name": "Acme Robotics"}, claims, generated_at="2026-11-08T00:00:00Z")
    assert len(brief.questions) == 3
    assert any("runs" in q or "raised" in q or "founded" in q or "sell" in q for q in brief.questions)


def test_memory_line_is_attributed_not_stated_as_fact():
    brief = compose(
        {"canonical_name": "Acme Robotics"},
        verify([]).claims,
        generated_at="2026-11-08T00:00:00Z",
        memory_context="Met their COO at the Canberra supply-chain meetup in October.",
    )
    why = next(s for s in brief.sections if s.id == "why")
    assert "Canberra supply-chain meetup" in (why.note or "")
    assert why.bullets == ()


def test_sources_are_listed_once_per_page():
    """Four quotes from one page are one source, not four lines in the appendix."""
    url = "https://acme.example/about"
    quotes = [
        "Acme employs 120 employees.",
        "Acme was founded in 2014.",
        "Acme is headquartered in Canberra.",
        "Acme builds warehouse robots.",
    ]
    drafts = [
        ClaimDraft(predicate=predicate, value=value, evidence=Evidence(
            source_url=url,
            source_type="official",
            quote=quote,
            retrieved_at="2026-11-08T00:00:00Z",
            published_at="2026-10-01",
        ))
        for predicate, value, quote in zip(
            ("employees", "founded", "hq", "product"),
            ("120", "2014", "Canberra", "Warehouse robots"),
            quotes,
        )
    ]
    brief = compose({"canonical_name": "Acme Robotics"}, verify(drafts).claims, generated_at="2026-11-08T00:00:00Z")
    assert [item.source_url for item in brief.sources] == [url]
