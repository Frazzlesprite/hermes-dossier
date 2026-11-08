"""Dashboard backend for Dossier, mounted at /api/plugins/dossier/.

The Desktop page talks to Python only over HTTP, so this module is the whole
bridge: list, detail, refresh, forget, and the rendered brief.

It loads the plugin package by file location, the same way Hermes loads a
directory plugin, because `dashboard/plugin_api.py` itself is imported as a
standalone module with no package parent, a relative import here would have
nothing to be relative to.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter()

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_PKG_NAME = "hermes_dashboard_plugin_dossier_agent"


def _plugin():
    """The Dossier package, loaded once and cached."""
    if _PKG_NAME in sys.modules:
        return sys.modules[_PKG_NAME]
    spec = importlib.util.spec_from_file_location(
        _PKG_NAME, _PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(_PLUGIN_ROOT)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the dossier package from {_PLUGIN_ROOT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PKG_NAME] = module
    spec.loader.exec_module(module)
    return module


def _parts():
    pkg = _plugin()
    return pkg, sys.modules[f"{_PKG_NAME}.db"], sys.modules[f"{_PKG_NAME}.store"]


def _mod(name: str):
    _plugin()
    return sys.modules[f"{_PKG_NAME}.{name}"]


def _connect() -> sqlite3.Connection:
    _, db, _ = _parts()
    return db.connect()


def _entity(conn: sqlite3.Connection, entity_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="no such dossier")
    return dict(row)


@router.get("/dossiers")
async def list_dossiers() -> dict[str, Any]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT e.id, e.canonical_name, e.kind, e.domain, e.updated_at, "
            "  (SELECT COUNT(*) FROM claims c WHERE c.entity_id = e.id) AS claims, "
            "  (SELECT COUNT(*) FROM claims c WHERE c.entity_id = e.id AND c.status = 'contested') AS contested, "
            "  (SELECT COUNT(*) FROM snapshots s WHERE s.entity_id = e.id) AS snapshots, "
            "  (SELECT MAX(taken_at) FROM snapshots s WHERE s.entity_id = e.id) AS last_snapshot "
            "FROM entities e ORDER BY COALESCE(e.updated_at, e.created_at) DESC"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/dossiers/{entity_id}")
async def get_dossier(entity_id: int) -> dict[str, Any]:
    pkg, db, store = _parts()
    conn = _connect()
    try:
        entity = _entity(conn, entity_id)
        snapshots = store.recent_snapshots(conn, entity_id, limit=10)
        claims = _mod("tools")._stored_claims(conn, entity_id)
        watch = conn.execute("SELECT * FROM watchlist WHERE entity_id = ?", (entity_id,)).fetchone()
    finally:
        conn.close()

    if not snapshots:
        return {
            "entity": entity,
            "claims": [],
            "sections": [],
            "questions": [],
            "headline": "No snapshot yet.",
            "snapshots": [],
            "watchlist": dict(watch) if watch else None,
        }

    brief = _mod("compose").compose(
        entity,
        claims,
        generated_at=snapshots[0]["taken_at"],
        freshness_days=int((entity.get("retention_days") or 90)))
    return {
        "entity": entity,
        "headline": brief.headline,
        "questions": brief.questions,
        "sections": [
            {
                "id": s.id,
                "title": s.title,
                "note": s.note,
                "bullets": [{"text": b.text, "sources": [e.source_url for e in b.evidence]} for b in s.bullets],
            }
            for s in brief.sections
        ],
        "claims": [c.as_dict() for c in claims],
        "snapshots": [{"id": s["id"], "taken_at": s["taken_at"]} for s in snapshots],
        "watchlist": dict(watch) if watch else None,
        "generated_at": snapshots[0]["taken_at"],
    }


@router.get("/dossiers/{entity_id}/brief", response_class=HTMLResponse)
async def get_brief(entity_id: int) -> HTMLResponse:
    _, db, store = _parts()
    conn = _connect()
    try:
        _entity(conn, entity_id)
        snapshots = store.recent_snapshots(conn, entity_id, limit=1)
    finally:
        conn.close()
    if not snapshots:
        raise HTTPException(status_code=404, detail="no snapshot yet")
    return HTMLResponse(snapshots[0]["brief_html"])


@router.get("/dossiers/{entity_id}/brief.pdf")
async def get_brief_pdf(entity_id: int):
    from fastapi import Response  # noqa: PLC0415

    _, db, store = _parts()
    conn = _connect()
    try:
        _entity(conn, entity_id)
        snapshots = store.recent_snapshots(conn, entity_id, limit=1)
    finally:
        conn.close()
    if not snapshots or not snapshots[0].get("brief_pdf"):
        raise HTTPException(status_code=404, detail="no PDF for this dossier yet; run a refresh")
    return Response(
        content=bytes(snapshots[0]["brief_pdf"]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="dossier-{entity_id}.pdf"'})


@router.post("/dossiers/{entity_id}/refresh")
async def refresh(entity_id: int) -> dict[str, Any]:
    """Re-fetch sources and store a new snapshot.

    Deliberately runs without a model and without a search backend: the model is
    session-bound and a plugin backend must not borrow one. That means this
    refresh re-reads the official site and GitHub and re-runs the deterministic
    extractor. For a full sweep, including search and news, run
    `/dossier refresh <name>` in a session, the card says so.
    """
    pkg, db, _ = _parts()
    conn = _connect()
    try:
        entity = _entity(conn, entity_id)
        if not entity.get("domain") and not entity.get("github"):
            return {
                "ok": False,
                "reason": "This dossier has no domain or GitHub slug, so there is nothing to re-fetch. Run /dossier refresh in a session.",
            }
        result = _mod("pipeline").build(
            entity["canonical_name"],
            conn=conn,
            search_fn=None,
            llm=None,
            domain=entity.get("domain"),
            github=entity.get("github"),
            disambiguator=entity.get("disambiguator"),
            kind=entity.get("kind"),
            purpose=entity.get("purpose"))
    finally:
        conn.close()

    if result.get("status") != "ok":
        return {"ok": False, "reason": result.get("error", "refresh failed")}
    result.pop("html", None)
    return {
        "ok": True,
        "diff": result.get("diff"),
        "counts": result.get("counts"),
        "note": "Official site and GitHub only. Run /dossier refresh in a session for search and news.",
    }


@router.post("/dossiers/{entity_id}/forget")
async def forget(entity_id: int, body: Optional[dict] = None) -> dict[str, Any]:
    _, db, _ = _parts()
    if not (body or {}).get("confirm"):
        raise HTTPException(status_code=400, detail="confirm=true is required")
    conn = _connect()
    try:
        _entity(conn, entity_id)
        counts = db.delete_entity(conn, entity_id)
    finally:
        conn.close()
    return {"ok": True, "deleted": counts}
