"""Extraction: nothing becomes a claim without a verbatim quote."""

from __future__ import annotations

from dossier.extract import extract, extract_with_llm
from dossier.models import Document

PAGE = Document(
    url="https://acme.example/about",
    title="Acme Robotics",
    text=(
        "Acme Robotics builds autonomous warehouse robots for logistics operators. "
        "Founded in 2014, the company employs 120 employees. "
        "Headquartered in Canberra, Australia. The CEO is Dana Whitfield."
    ),
    source_type="official",
    retrieved_at="2026-11-08T00:00:00Z",
    domain="acme.example",
)


class FakeLlm:
    def __init__(self, claims):
        self.claims = claims

    def complete_structured(self, **kwargs):
        class Result:
            parsed = {"claims": self.claims}

        return Result()


def test_deterministic_extraction_finds_dated_facts():
    report = extract([PAGE])
    predicates = {c.predicate for c in report.claims}
    assert {"founded", "employees", "hq", "ceo"} <= predicates

    employees = next(c for c in report.claims if c.predicate == "employees")
    assert employees.value == "120"


def test_every_accepted_claim_quotes_the_source_verbatim():
    report = extract([PAGE])
    assert report.claims
    for claim in report.claims:
        assert claim.evidence.quote in PAGE.text


def test_a_claim_whose_quote_is_not_in_the_page_is_rejected():
    llm = FakeLlm(
        [
            {"predicate": "employees", "value": "900", "quote": "Acme employs 900 people worldwide."},
            {"predicate": "employees", "value": "120", "quote": "the company employs 120 employees"},
        ]
    )
    report = extract_with_llm(PAGE, llm)
    values = {c.value for c in report.claims}
    assert "120" in values
    assert "900" not in values
    assert any("not verbatim" in r["reason"] for r in report.rejected)


def test_a_quote_must_be_long_enough_to_check():
    llm = FakeLlm([{"predicate": "hq", "value": "Canberra", "quote": "Canberra"}])
    report = extract_with_llm(PAGE, llm)
    assert not report.claims
    assert any("too short" in r["reason"] for r in report.rejected)


def test_an_unsupported_predicate_is_rejected():
    llm = FakeLlm([{"predicate": "net_worth", "value": "1", "quote": "Acme Robotics builds autonomous warehouse robots"}])
    report = extract_with_llm(PAGE, llm)
    assert not report.claims
    assert any("closed set" in r["reason"] for r in report.rejected)


def test_a_third_party_quote_must_name_the_entity():
    """A sentence about Nvidia is not a fact about Valve."""
    page = Document(
        url="https://news.example/chips",
        title="Chip deal",
        text="Nvidia CEO Jensen Huang said the deal was the largest of its kind.",
        source_type="news",
        retrieved_at="2026-11-09T00:00:00Z",
        domain="news.example",
    )
    report = extract([page], entity_name="Valve Corporation", entity_domain="valvesoftware.com")
    assert not [c for c in report.claims if c.predicate == "ceo"]
    assert any("does not name the entity" in r["reason"] for r in report.rejected)


def test_a_page_on_the_entity_domain_needs_no_name_in_the_sentence():
    """Their own About page can say "Founded in 2014" without repeating the name."""
    report = extract(
        [PAGE], entity_name="Acme Robotics", entity_domain="acme.example"
    )
    assert {c.predicate for c in report.claims} >= {"founded", "employees"}


def test_founded_ignores_a_project_that_started():
    page = Document(
        url="https://en.wikipedia.org/wiki/Thing",
        title="Thing",
        text="Valve game started around late 2016, with the largest team in Valve's history.",
        source_type="search",
        retrieved_at="2026-11-09T00:00:00Z",
        domain="en.wikipedia.org",
    )
    report = extract([page], entity_name="Valve Corporation")
    assert not [c for c in report.claims if c.predicate == "founded"]


def test_a_model_failure_is_a_note_not_a_crash():
    class Broken:
        def complete_structured(self, **kwargs):
            raise TimeoutError("model timed out")

    report = extract_with_llm(PAGE, Broken())
    assert not report.claims
    assert any("model extraction failed" in r["reason"] for r in report.rejected)
