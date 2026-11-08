"""Policy: the sensitive categories the schema must refuse."""

from __future__ import annotations

import pytest

from dossier.extract import extract, extract_with_llm
from dossier.models import PREDICATES, SENSITIVE_TERMS, Document


def _page(text: str) -> Document:
    return Document(
        url="https://example.org/profile",
        title="Profile",
        text=text,
        source_type="news",
        retrieved_at="2026-11-08T00:00:00Z",
        domain="example.org",
    )


class FakeLlm:
    def __init__(self, claims):
        self.claims = claims

    def complete_structured(self, **kwargs):
        class Result:
            parsed = {"claims": self.claims}

        return Result()


@pytest.mark.parametrize(
    "sentence",
    [
        "The founder's religion is Christian, according to the profile.",
        "She has spoken publicly about her sexual orientation and her health.",
        "He is a member of a political party and of a trade union.",
        "The team is described by ethnicity in the recruitment report.",
    ],
)
def test_sensitive_sentences_are_refused_at_extraction(sentence):
    llm = FakeLlm(
        [{"predicate": "news", "value": sentence, "quote": sentence}]
    )
    report = extract_with_llm(_page(sentence), llm)
    assert not report.claims
    assert any("sensitive category" in r["reason"] for r in report.rejected)


def test_the_deterministic_path_refuses_them_too():
    page = _page("The company employs 40 employees and the founder's religion is Christian.")
    report = extract([page])
    assert all("religion" not in c.evidence.quote.casefold() for c in report.claims)


def test_no_sensitive_term_is_ever_a_predicate():
    for term in SENSITIVE_TERMS:
        assert term not in PREDICATES


def test_the_schema_has_no_sensitive_columns():
    from dossier.db import SCHEMA

    lowered = SCHEMA.casefold()
    for banned in ("religion", "ethnicity", "sexual", "health", "political", "union"):
        assert banned not in lowered
