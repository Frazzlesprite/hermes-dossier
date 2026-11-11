"""The dashboard backend: the routes exist, and they refuse dangerous calls.

The Desktop page can only reach Python through these routes, so a broken route
is a broken button. This loads `dashboard/plugin_api.py` exactly the way Hermes
does, as a standalone module with no package parent, which is also the check
that its imports survive that.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
import sys

import pytest
from fastapi import HTTPException

import dossier.db as db
from conftest import ROOT


def _load_api():
    name = "hermes_dashboard_plugin_dossier_test"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "dashboard" / "plugin_api.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def api(tmp_path, monkeypatch):
    module = _load_api()
    conn = db.connect(tmp_path / "api.db")
    conn.execute(
        "INSERT INTO entities (kind, canonical_name, domain, created_at) VALUES ('org', 'Acme Robotics', 'acme.example', '2026-11-08')"
    )
    conn.execute(
        "INSERT INTO entities (kind, canonical_name, created_at) VALUES ('org', 'No Web Presence Pty Ltd', '2026-11-08')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(module, "_connection", lambda: db.connect(tmp_path / "api.db"))
    return module


def test_the_router_declares_every_route_the_page_calls():
    module = _load_api()
    paths = {(route.path, tuple(sorted(route.methods))) for route in module.router.routes}
    expected = {
        ("/dossiers", ("GET",)),
        ("/dossiers/{entity_id}", ("GET",)),
        ("/dossiers/{entity_id}/brief", ("GET",)),
        ("/dossiers/{entity_id}/brief.pdf", ("GET",)),
        ("/dossiers/{entity_id}/refresh", ("POST",)),
        ("/dossiers/{entity_id}/forget", ("POST",)),
    }
    assert expected <= paths


def test_list_returns_the_stored_entities(api):
    payload = asyncio.run(api.list_dossiers())
    assert [item["canonical_name"] for item in payload["items"]] != []
    assert "Acme Robotics" in [item["canonical_name"] for item in payload["items"]]
    assert payload["items"][0]["claims"] == 0


def test_detail_works_before_any_snapshot(api):
    payload = asyncio.run(api.get_dossier(1))
    assert payload["entity"]["canonical_name"] == "Acme Robotics"
    assert payload["headline"] == "No snapshot yet."
    assert payload["snapshots"] == []


def test_unknown_entity_is_a_404(api):
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(api.get_dossier(999))
    assert excinfo.value.status_code == 404


def test_forget_requires_confirmation(api):
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(api.forget(1, body={}))
    assert excinfo.value.status_code == 400

    payload = asyncio.run(api.forget(1, body={"confirm": True}))
    assert payload["ok"] is True
    names = [item["canonical_name"] for item in asyncio.run(api.list_dossiers())["items"]]
    assert "Acme Robotics" not in names


def test_refresh_without_the_plugin_loaded_says_where_to_run_it(api, monkeypatch):
    # In this test process the plugin package *is* imported by conftest, so the
    # backend would find it. Pretend it is somewhere else, which is the real
    # dashboard case, and check the message the user gets.
    monkeypatch.setattr(api, "_loaded_plugin", lambda: None)
    payload = asyncio.run(api.refresh(2))
    assert payload["ok"] is False
    assert "/dossier refresh" in payload["reason"]
