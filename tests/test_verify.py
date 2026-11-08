"""Verification: the confidence table, and contradictions kept as contradictions."""

from __future__ import annotations

from dossier.models import ClaimDraft, Evidence
from dossier.verify import verify


def _draft(predicate: str, value: str, url: str, source_type: str, quote: str = "a quote long enough") -> ClaimDraft:
    return ClaimDraft(
        predicate=predicate,
        value=value,
        evidence=Evidence(
            source_url=url,
            source_type=source_type,
            quote=quote,
            retrieved_at="2026-11-08T00:00:00Z",
            published_at="2026-10-01",
        ),
    )


def test_two_independent_primary_sources_agree():
    report = verify(
        [
            _draft("founded", "2014", "https://acme.example/about", "official"),
            _draft("founded", "2014", "https://registry.example/acme", "registry"),
        ]
    )
    claim = report.claims[0]
    assert claim.confidence == 0.95
    assert claim.status == "supported"


def test_one_primary_source():
    report = verify([_draft("hq", "Canberra", "https://acme.example/about", "official")])
    assert report.claims[0].confidence == 0.80


def test_one_secondary_source():
    report = verify([_draft("hq", "Canberra", "https://news.example/acme", "news")])
    assert report.claims[0].confidence == 0.60


def test_secondary_sources_disagree_so_both_survive_as_contested():
    report = verify(
        [
            _draft("employees", "120", "https://news.example/a", "news"),
            _draft("employees", "160", "https://news2.example/b", "news"),
        ]
    )
    assert report.contested == 1
    values = {c.value: c for c in report.claims}
    assert set(values) == {"120", "160"}
    for claim in values.values():
        assert claim.status == "contested"
        assert claim.confidence == 0.50


def test_a_contested_claim_is_never_resolved_to_a_winner():
    report = verify(
        [
            _draft("employees", "120", "https://acme.example/about", "official"),
            _draft("employees", "160", "https://news.example/a", "news"),
        ]
    )
    assert {c.status for c in report.claims} == {"contested"}
    assert len(report.claims) == 2


def test_a_contained_product_value_folds_into_the_full_one():
    report = verify(
        [
            _draft("product", "warehouse robots", "https://acme.example/about", "official"),
            _draft("product", "Acme Robotics builds warehouse robots", "https://acme.example/", "official"),
        ]
    )
    assert len(report.claims) == 1
    assert report.claims[0].value == "Acme Robotics builds warehouse robots"
    assert len(report.claims[0].evidence) == 2


def test_one_source_giving_a_series_is_unconfirmed_not_contested():
    """Wikipedia listing headcounts for 2003, 2012 and 2021 is a timeline."""
    url = "https://en.wikipedia.org/wiki/Valve_Corporation"
    report = verify(
        [
            _draft("employees", "60", url, "search"),
            _draft("employees", "250", url, "search"),
            _draft("employees", "350", url, "search"),
        ]
    )
    assert report.contested == 0
    assert {c.status for c in report.claims} == {"unconfirmed"}
    assert any("single source" in note for note in report.notes)


def test_two_different_sources_still_contest():
    report = verify(
        [
            _draft("employees", "120", "https://acme.example/about", "official"),
            _draft("employees", "160", "https://news.example/a", "news"),
        ]
    )
    assert report.contested == 1


def test_multi_valued_predicates_do_not_contest():
    report = verify(
        [
            _draft("product", "warehouse robots", "https://acme.example/about", "official"),
            _draft("product", "robot fleet software", "https://acme.example/platform", "official"),
        ]
    )
    assert report.contested == 0
    assert {c.status for c in report.claims} == {"supported"}


def test_duplicate_evidence_is_collapsed():
    report = verify(
        [
            _draft("founded", "2014", "https://acme.example/about", "official", quote="Founded in 2014."),
            _draft("founded", "2014", "https://acme.example/about", "official", quote="Founded in 2014."),
        ]
    )
    assert len(report.claims) == 1
    assert len(report.claims[0].evidence) == 1
