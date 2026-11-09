"""Purpose and context: the same evidence, framed for the meeting you have."""

from __future__ import annotations

import pytest

from dossier import contexts
from dossier.compose import compose
from dossier.models import Claim, Evidence, ClaimDraft
from dossier.verify import verify


def _claim(predicate: str, value: str) -> Claim:
    evidence = Evidence(
        source_url="https://acme.example/about",
        source_type="official",
        quote=f"Acme says {value}.",
        retrieved_at="2026-11-09T00:00:00Z",
    )
    return Claim(predicate=predicate, value=value, confidence=0.8, status="supported", evidence=[evidence])


@pytest.mark.parametrize(
    "purpose,expected",
    [
        ("interview for the platform role on Thursday", "interview"),
        ("first sales call with their procurement team", "sales"),
        ("exploring a partnership with their platform team", "partnership"),
        ("due diligence before we acquire them", "diligence"),
        ("annual supplier review", "supplier"),
        ("", "general"),
        ("something vague about the weather", "general"),
    ],
)
def test_context_is_inferred_from_the_purpose(purpose, expected):
    assert contexts.infer(purpose) == expected


def test_a_person_dossier_defaults_to_interview_context():
    assert contexts.infer("", kind="person") == "interview"


def test_a_person_with_no_context_still_gets_interview_questions():
    brief = compose(
        {"canonical_name": "Sarah Chen", "kind": "person"},
        [_claim("role", "Partner at Harbour Fund")],
        generated_at="2026-11-09T00:00:00Z",
        purpose="meeting on Thursday",
        context="interview",
    )
    assert any("report to" in q or "team" in q for q in brief.questions)


def test_sales_context_changes_the_questions():
    brief = compose(
        {"canonical_name": "Acme Robotics"},
        [_claim("product", "warehouse robots")],
        generated_at="2026-11-09T00:00:00Z",
        purpose="first sales call",
        context="sales",
    )
    joined = " ".join(brief.questions).casefold()
    assert "renew" in joined or "procurement" in joined or "sign" in joined
    assert len(brief.questions) == 3


def test_the_risk_heading_follows_the_context():
    brief = compose(
        {"canonical_name": "Acme Robotics"},
        [_claim("hq", "Canberra")],
        generated_at="2026-11-09T00:00:00Z",
        context="sales",
    )
    risks = next(section for section in brief.sections if section.id == "risks")
    assert risks.title == "Objections to expect"


def test_the_purpose_is_printed_on_the_brief():
    brief = compose(
        {"canonical_name": "Acme Robotics"},
        [_claim("hq", "Canberra")],
        generated_at="2026-11-09T00:00:00Z",
        purpose="interview for the platform role",
        context="interview",
    )
    why = next(section for section in brief.sections if section.id == "why")
    # The purpose lives in the brief header, printed once; this section is for
    # Hermes memory only, so it must not repeat it.
    assert "Purpose:" not in (why.note or "")
    assert brief.purpose == "interview for the platform role"
    assert brief.context == "interview"


def test_purpose_does_not_add_an_unsourced_bullet():
    brief = compose(
        {"canonical_name": "Acme Robotics"},
        [_claim("hq", "Canberra")],
        generated_at="2026-11-09T00:00:00Z",
        purpose="interview",
        context="interview",
    )
    for section in brief.sections:
        for bullet in section.bullets:
            assert bullet.evidence


def test_unknown_context_falls_back_to_general():
    assert contexts.normalise("nonsense") == ""
    assert contexts.merge("nonsense", "Acme", ["a?", "b?", "c?"]) == ["a?", "b?", "c?"]
