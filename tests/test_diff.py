"""Diff: report a changed headcount, and stay quiet about everything else."""

from __future__ import annotations

import json

from dossier.store import diff_claims


def _payload(claims: list[dict]) -> str:
    return json.dumps(claims)


BASE = [
    {"predicate": "founded", "value": "2014", "confidence": 0.8, "status": "supported"},
    {"predicate": "employees", "value": "120", "confidence": 0.6, "status": "supported"},
    {"predicate": "hq", "value": "Canberra", "confidence": 0.95, "status": "supported"},
]


def test_a_changed_headcount_shows_up():
    after = [
        {"predicate": "founded", "value": "2014", "confidence": 0.8, "status": "supported"},
        {"predicate": "employees", "value": "160", "confidence": 0.8, "status": "supported"},
        {"predicate": "hq", "value": "Canberra", "confidence": 0.95, "status": "supported"},
    ]
    result = diff_claims(_payload(BASE), _payload(after))
    assert [c["value"] for c in result["added"]] == ["160"]
    assert [c["value"] for c in result["removed"]] == ["120"]


def test_unchanged_claims_do_not_appear():
    result = diff_claims(_payload(BASE), _payload(BASE))
    assert result["changed_count"] == 0
    assert result["added"] == result["removed"] == result["changed"] == []


def test_a_status_change_is_reported():
    after = [
        {"predicate": "founded", "value": "2014", "confidence": 0.8, "status": "supported"},
        {"predicate": "employees", "value": "120", "confidence": 0.5, "status": "contested"},
        {"predicate": "hq", "value": "Canberra", "confidence": 0.95, "status": "supported"},
    ]
    result = diff_claims(_payload(BASE), _payload(after))
    assert len(result["changed"]) == 1
    assert result["changed"][0]["to"]["status"] == "contested"


def test_a_confidence_change_is_reported():
    after = [
        {"predicate": "founded", "value": "2014", "confidence": 0.95, "status": "supported"},
        {"predicate": "employees", "value": "120", "confidence": 0.6, "status": "supported"},
        {"predicate": "hq", "value": "Canberra", "confidence": 0.95, "status": "supported"},
    ]
    result = diff_claims(_payload(BASE), _payload(after))
    assert [c["predicate"] for c in result["changed"]] == ["founded"]


def test_malformed_payload_does_not_raise():
    result = diff_claims("not json", _payload(BASE))
    assert len(result["added"]) == len(BASE)
