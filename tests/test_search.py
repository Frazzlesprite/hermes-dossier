"""Search results arrive in several envelopes; all of them must normalise.

The shapes here are taken from the real backends: Hermes' own `web_search`
returns ``{"success": ..., "data": {"web": [...]}}``, and the others are what
providers commonly return. A normaliser that only knows one shape silently
turns search off, which is the failure this file exists to prevent.
"""

from __future__ import annotations

import json

from dossier.adapters.search import normalise_results


def test_hermes_web_search_envelope():
    raw = json.dumps(
        {
            "success": True,
            "data": {
                "web": [
                    {"title": "Acme Robotics", "url": "https://acme.example/", "description": "Robots", "position": 1},
                    {"title": "Acme about", "url": "https://acme.example/about", "description": "", "position": 2},
                ]
            },
        }
    )
    results = normalise_results(raw)
    assert [r["url"] for r in results] == ["https://acme.example/", "https://acme.example/about"]
    assert results[0]["title"] == "Acme Robotics"


def test_results_envelope():
    raw = {"results": [{"title": "A", "url": "https://a.example/", "published_at": "2026-10-01"}]}
    assert normalise_results(raw)[0]["published_at"] == "2026-10-01"


def test_bare_list():
    assert normalise_results([{"url": "https://b.example/"}])[0]["url"] == "https://b.example/"


def test_link_key_is_accepted():
    assert normalise_results({"items": [{"link": "https://c.example/"}]})[0]["url"] == "https://c.example/"


def test_empty_and_junk_do_not_raise():
    for junk in ("not json", None, {}, {"data": None}, {"web": "nope"}, [1, 2, 3]):
        assert normalise_results(junk) == []


def test_entries_without_a_url_are_dropped():
    assert normalise_results({"results": [{"title": "no url"}, {"url": "ftp://x"}]}) == []
