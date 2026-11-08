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
                {"url": "https://harbour.example/team/sarah-chen", "title": "Sarah Chen — Partner, Harbour Fund"},
                {"url": "https://acme.example/team/sarah-chen", "title": "Sarah Chen — Engineer, Acme Robotics"},
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

    real_connect = dbmod.connect
    monkeypatch.setattr(dbmod, "connect", lambda path=None: real_connect(tmp_path / "dossier.db"))
    conn = db.connect(tmp_path / "dossier.db")
    try:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("entities", "claims", "evidence", "snapshots")
        }
        assert all(before.values())

        payload = json.loads(tools.forget({"name": "Acme Robotics", "confirm": True}))
        assert payload["status"] == "deleted"
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0

        again = json.loads(tools.forget({"name": "Acme Robotics", "confirm": True}))
        assert "No stored dossier" in again["error"]
    finally:
        conn.close()


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
