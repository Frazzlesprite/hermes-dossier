"""End to end: two runs, one changed headcount, and a real diff."""

from __future__ import annotations

import json

from dossier import db, pipeline, tools
from dossier.pipeline import Config

import fakeweb


def _run(tmp_path, monkeypatch, version: int, name: str = "Acme Robotics"):
    web = fakeweb.install(monkeypatch, fakeweb.acme_web(version))
    conn = db.connect(tmp_path / "dossier.db")
    try:
        return pipeline.build(
            name,
            conn=conn,
            search_fn=web.search,
            config=Config(sources_per_brief=6),
        )
    finally:
        conn.close()


def test_a_brief_is_built_with_sourced_claims(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, 1)
    assert result["status"] == "ok", result
    predicates = {c["predicate"] for c in result["claims"]}
    assert "employees" in predicates and "founded" in predicates
    for claim in result["claims"]:
        assert claim["evidence"], f"{claim['predicate']} has no evidence"
        assert claim["evidence"][0]["quote"]
    assert result["counts"]["documents"] >= 1
    assert result["html"].startswith("<!doctype html>")


def test_the_first_run_has_no_diff_and_the_second_has_one(tmp_path, monkeypatch):
    first = _run(tmp_path, monkeypatch, 1)
    assert first["status"] == "ok"
    assert first["diff"] is None

    second = _run(tmp_path, monkeypatch, 2)
    assert second["status"] == "ok"
    assert second["entity_id"] == first["entity_id"], "a refresh must stay on the same entity"

    diff = second["diff"]
    assert diff is not None
    assert "160" in {c["value"] for c in diff["added"]}
    assert "120" in {c["value"] for c in diff["removed"]}
    assert diff["changed_count"] >= 2


def test_an_ambiguous_name_stops_before_writing_anything(tmp_path, monkeypatch):
    web = fakeweb.install(
        monkeypatch,
        fakeweb.FakeWeb(
            pages={
                "https://harbour.example/team/sarah-chen": fakeweb.AMBIGUOUS_A,
                "https://acme.example/team/sarah-chen": fakeweb.AMBIGUOUS_B,
            },
            results=[
                {"url": "https://harbour.example/team/sarah-chen", "title": "Sarah Chen - Partner, Harbour Fund"},
                {"url": "https://acme.example/team/sarah-chen", "title": "Sarah Chen - Engineer, Acme Robotics"},
            ],
        ),
    )
    conn = db.connect(tmp_path / "dossier.db")
    try:
        result = pipeline.build("Sarah Chen", conn=conn, search_fn=web.search, config=Config())
        assert result["status"] == "ambiguous"
        assert len(result["candidates"]) == 2
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0
    finally:
        conn.close()


def test_forget_removes_everything(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, 1)
    import dossier.db as dbmod
    import dossier.tools as toolsmod

    real_connect = dbmod.connect
    monkeypatch.setattr(dbmod, "connect", lambda path=None: real_connect(tmp_path / "dossier.db"))
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / "acme-robotics-20260101T000000Z.html").write_text("<p>a whole brief</p>")
    monkeypatch.setattr(toolsmod, "_brief_dir", lambda: briefs)
    conn = db.connect(tmp_path / "dossier.db")
    try:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("entities", "claims", "evidence", "snapshots")
        }
        assert all(before.values())

        payload = json.loads(tools.forget({"name": "Acme Robotics", "confirm": True}))
        assert payload["status"] == "deleted"
        assert payload["deleted"]["briefs"] == 1
        assert not list(briefs.glob("*.html")), "a rendered brief survived the delete"
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0

        again = json.loads(tools.forget({"name": "Acme Robotics", "confirm": True}))
        assert "No stored dossier" in again["error"]
    finally:
        conn.close()


def test_a_one_word_name_does_not_absorb_homonyms(tmp_path, monkeypatch):
    """'Kalamari' is an app studio and a Paris PR agency and a Greek dish."""
    web = fakeweb.install(
        monkeypatch,
        fakeweb.FakeWeb(
            pages={
                "https://kalamari.example/": "<html><head><title>Kalamari</title></head><body><p>Kalamari is an app studio in Canberra.</p></body></html>",
                "https://pr.example/kalamari-rename": "<html><head><title>Kalamari renames</title></head><body><p>A Paris agency today renamed itself Kalamari.</p></body></html>",
            },
            results=[
                {"url": "https://kalamari.example/", "title": "Kalamari"},
                {"url": "https://pr.example/kalamari-rename", "title": "Kalamari renames"},
            ],
        ),
    )
    conn = db.connect(tmp_path / "collision.db")
    try:
        result = pipeline.build(
            "Kalamari", conn=conn, search_fn=web.search, domain="kalamari.example", config=Config()
        )
    finally:
        conn.close()

    assert result["status"] == "ok"
    used = {item["source_url"] for claim in result["claims"] for item in claim["evidence"]}
    assert not any("pr.example" in url for url in used), "a homonym contributed a claim"
    assert any("collision guard" in note for note in result["notes"])


def test_a_distinctive_name_keeps_its_coverage(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, 1)
    used = {item["source_url"] for claim in result["claims"] for item in claim["evidence"]}
    assert any("news.example" in url for url in used), "two-token names should keep third-party coverage"


def test_a_sales_context_is_stored_and_shapes_the_questions(tmp_path, monkeypatch):
    web = fakeweb.install(monkeypatch, fakeweb.acme_web(1))
    conn = db.connect(tmp_path / "ctx.db")
    try:
        result = pipeline.build(
            "Acme Robotics",
            conn=conn,
            search_fn=web.search,
            config=Config(),
            purpose="first call with their procurement team",
            context="sales",
        )
        stored = conn.execute("SELECT context, purpose FROM entities").fetchone()
    finally:
        conn.close()

    assert result["status"] == "ok"
    assert result["context"] == "sales"
    assert stored["context"] == "sales"
    assert stored["purpose"] == "first call with their procurement team"
    joined = " ".join(result["questions"]).casefold()
    assert "renew" in joined or "procurement" in joined


def test_context_can_be_inferred_from_the_purpose_alone(tmp_path, monkeypatch):
    web = fakeweb.install(monkeypatch, fakeweb.acme_web(1))
    conn = db.connect(tmp_path / "ctx2.db")
    try:
        result = pipeline.build(
            "Acme Robotics",
            conn=conn,
            search_fn=web.search,
            config=Config(),
            purpose="interview for the platform role on Thursday",
        )
    finally:
        conn.close()
    assert result["context"] == "interview"


def test_forget_refuses_without_confirmation(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, 1)
    import dossier.db as dbmod

    real_connect = dbmod.connect
    monkeypatch.setattr(dbmod, "connect", lambda path=None: real_connect(tmp_path / "dossier.db"))
    conn = db.connect(tmp_path / "dossier.db")
    try:
        payload = json.loads(tools.forget({"name": "Acme Robotics"}))
        assert "confirm" in payload["error"]
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 1
    finally:
        conn.close()
