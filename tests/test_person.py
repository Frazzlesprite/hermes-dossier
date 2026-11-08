"""Person dossiers: professional context is required, and roles are extracted."""

from __future__ import annotations

import fakeweb
from dossier import db, pipeline
from dossier.extract import extract
from dossier.models import Document
from dossier.pipeline import Config

PROFILE = Document(
    url="https://harbour.example/team/sarah-chen",
    title="Sarah Chen — Partner",
    text=(
        "Sarah Chen is a partner at Harbour Fund. "
        "She was previously an analyst at Acme Robotics. "
        "Sarah Chen leads the climate practice."
    ),
    source_type="official",
    retrieved_at="2026-11-09T00:00:00Z",
    domain="harbour.example",
)


def test_a_role_is_extracted_for_a_person():
    report = extract([PROFILE], kind="person")
    roles = [c for c in report.claims if c.predicate == "role"]
    assert roles, "a person page with a role sentence must yield a role claim"
    assert "Harbour Fund" in roles[0].value
    assert roles[0].evidence.quote in PROFILE.text


def test_organisation_dossiers_do_not_get_role_claims():
    report = extract([PROFILE], kind="org")
    assert not [c for c in report.claims if c.predicate == "role"]


def test_a_person_dossier_without_a_purpose_is_refused(tmp_path):
    conn = db.connect(tmp_path / "person.db")
    try:
        result = pipeline.build("Sarah Chen", conn=conn, kind="person", config=Config(), domain="harbour.example")
        stored = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    finally:
        conn.close()
    assert result["status"] == "refused"
    assert "purpose" in result["error"]
    assert stored == 0


def test_a_person_dossier_with_a_purpose_is_allowed(tmp_path, monkeypatch):
    web = fakeweb.install(
        monkeypatch,
        fakeweb.FakeWeb(
            pages={"https://harbour.example/team/sarah-chen": fakeweb.AMBIGUOUS_A},
            results=[{"url": "https://harbour.example/team/sarah-chen", "title": "Sarah Chen — Partner, Harbour Fund"}],
        ),
    )
    conn = db.connect(tmp_path / "person2.db")
    try:
        result = pipeline.build(
            "Sarah Chen",
            conn=conn,
            search_fn=web.search,
            kind="person",
            purpose="interview for the climate lead role",
            disambiguator="Harbour",
            config=Config(),
        )
    finally:
        conn.close()
    assert result["status"] == "ok", result
    assert result["entity"]["kind"] == "person"


def test_people_can_be_disabled_entirely(tmp_path):
    conn = db.connect(tmp_path / "person3.db")
    try:
        result = pipeline.build(
            "Sarah Chen", conn=conn, kind="person", purpose="x", config=Config(allow_people=False)
        )
    finally:
        conn.close()
    assert result["status"] == "refused"
