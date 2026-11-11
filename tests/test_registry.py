"""The registry adapter: three providers, and honest degradation without keys."""

from __future__ import annotations

import json

from dossier.adapters import registry
from dossier.adapters.base import Fetch
from dossier.extract import extract

TICKERS = json.dumps(
    {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }
)

SUBMISSIONS = {
    "name": "Apple Inc.",
    "sicDescription": "Electronic Computers",
    "addresses": {"business": {"city": "CUPERTINO", "stateOrCountry": "CA"}},
    "filings": {"recent": {"form": ["10-Q", "10-K"], "filingDate": ["2026-02-01", "2025-10-31"]}},
}


def _install(monkeypatch, pages: dict[str, str]):
    registry._ticker_cache.update({"at": 0.0, "entries": {}})
    monkeypatch.setattr(registry, "_ticker_cache_path", lambda: None)

    def fake_fetch(url, policy=None):
        for key, body in pages.items():
            if key in url:
                return Fetch(url=url, status=200, text=body, retrieved_at="2026-11-09T00:00:00Z", final_url=url)
        return Fetch(url=url, status=404, error="HTTP 404", retrieved_at="2026-11-09T00:00:00Z")

    monkeypatch.setattr(registry, "fetch", fake_fetch)


def test_edgar_needs_no_key_and_produces_primary_claims(monkeypatch):
    _install(monkeypatch, {"company_tickers": TICKERS, "submissions": json.dumps(SUBMISSIONS)})
    result = registry.collect_edgar("Apple", contact="dev@example.com")
    assert result["notes"] == []
    doc = result["documents"][0]
    assert "CIK 0000320193" in doc.text
    assert "Headquartered in Cupertino, CA." in doc.text
    assert "Filed its 10-K on 2025-10-31." in doc.text

    predicates = {c.predicate for c in extract([doc]).claims}
    assert "hq" in predicates


def test_edgar_without_a_match_is_a_note(monkeypatch):
    _install(monkeypatch, {"company_tickers": TICKERS})
    result = registry.collect_edgar("Nonexistent Holdings", contact="dev@example.com")
    assert result["documents"] == []
    assert any("no registrant" in note for note in result["notes"])


def test_edgar_unreadable_submissions_are_not_silent(monkeypatch):
    _install(monkeypatch, {"company_tickers": TICKERS, "submissions": "not json"})
    result = registry.collect_edgar("Apple", contact="dev@example.com")
    assert result["documents"] == []
    assert any("unreadable" in note for note in result["notes"])


def test_edgar_without_a_contact_is_skipped_with_a_reason():
    result = registry.collect_edgar("Apple")
    assert result["documents"] == []
    assert "registry_contact" in result["notes"][0]


INCORPORATION = json.dumps(
    {
        "cik": 320193,
        "taxonomy": "dei",
        "tag": "EntityIncorporationDateOfIncorporation",
        "units": {
            "date": [
                {"end": "1977-01-03", "val": "1977-01-03", "filed": "2026-02-01"},
            ]
        },
    }
)


def test_edgar_does_not_invent_a_founding_year(monkeypatch):
    """EDGAR has no incorporation date, so the adapter claims none.

    Of eighteen large filers sampled, none tagged
    dei:EntityIncorporationDateOfIncorporation. A first-filing date is not a
    founding date, so the brief gets no founded claim from the US registry.
    """
    _install(
        monkeypatch,
        {
            "company_tickers": TICKERS,
            "submissions": json.dumps(SUBMISSIONS),
            "companyconcept": INCORPORATION,
        },
    )
    result = registry.collect_edgar("Apple", contact="dev@example.com")
    doc = result["documents"][0]
    assert "Incorporated" not in doc.text
    assert not [c for c in extract([doc]).claims if c.predicate == "founded"]


def test_abn_without_a_guid_says_so():
    result = registry.collect_abn("Acme Pty Ltd", "")
    assert result["documents"] == []
    assert "no ABN Lookup GUID" in result["notes"][0]


def test_abn_parses_jsonp(monkeypatch):
    match = """callback({"Names":[{"Abn":"51824753556","Name":"ACME PTY LTD","AbnStatus":"Active"}]})"""
    detail = """callback({"EntityName":"ACME PTY LTD","AbnStatus":"Active","AddressState":"NSW","EntityTypeName":"Australian Private Company"})"""
    _install(monkeypatch, {"MatchingNames": match, "AbnDetails": detail})
    result = registry.collect_abn("Acme", "guid-123")
    doc = result["documents"][0]
    assert "ABN 51 824 753 556" in doc.text
    assert "Located in Nsw." in doc.text


def test_companies_house_without_a_key_says_so():
    result = registry.collect_companies_house("Acme Ltd", "")
    assert result["documents"] == []
    assert "no API key" in result["notes"][0]


def test_companies_house_uses_the_number_and_address(monkeypatch):
    search = json.dumps({"items": [{"company_number": "12345678", "title": "ACME LTD"}]})
    company = json.dumps(
        {
            "company_name": "ACME LTD",
            "date_of_creation": "2015-04-02",
            "company_status": "active",
            "registered_office_address": {"locality": "LONDON"},
            "sic_codes": ["62012"],
        }
    )
    _install(monkeypatch, {"/search/companies": search, "/company/": company})
    result = registry.collect_companies_house("Acme", "key-123")
    doc = result["documents"][0]
    assert "company number 12345678" in doc.text
    assert "Incorporated in 2015." in doc.text
    assert "located in London." in doc.text


def test_all_providers_without_credentials_report_the_gaps():
    result = registry.collect_registry("Anything", country="AU")
    assert result["documents"] == []
    assert any("ABN" in note for note in result["notes"])


def test_a_provider_exception_is_a_note_not_a_crash(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("registry on fire")

    monkeypatch.setattr(registry, "collect_edgar", boom)
    result = registry.collect_registry("Anything", country="US")
    assert result["documents"] == []
    assert any("on fire" in note for note in result["notes"])
