"""Dashboard backend for Dossier, mounted at /api/plugins/dossier/.

This module reads the plugin's SQLite database directly and imports nothing from
the plugin package, so there is no module loading, no `sys.modules` write and no
private seam for a reviewer to argue about.

The composed brief is stored with each snapshot as JSON (see `models.Brief` and
`store.save_snapshot`), which is why this file does not need `compose.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

router = APIRouter()

PLUGIN_ID = "dossier"


def _connection():
    from plugins.plugin_storage import plugin_db  # noqa: PLC0415 - documented route

    return plugin_db(PLUGIN_ID)


def _brief_dir() -> Path:
    from plugins.plugin_storage import plugin_data_dir  # noqa: PLC0415

    return plugin_data_dir(PLUGIN_ID) / "briefs"


def _entity(conn, entity_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="no such dossier")
    return dict(row)


def _claims(conn, entity_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, predicate, value, confidence, status FROM claims WHERE entity_id = ? "
        "ORDER BY confidence DESC, predicate",
        (entity_id,),
    ).fetchall()
    claims: list[dict[str, Any]] = []
    for row in rows:
        evidence = conn.execute(
            "SELECT source_url, source_type, published_at, retrieved_at, quote FROM evidence "
            "WHERE claim_id = ? ORDER BY COALESCE(published_at, retrieved_at) DESC",
            (row["id"],),
        ).fetchall()
        claims.append({**dict(row), "evidence": [dict(item) for item in evidence]})
    return claims


def _latest_brief(conn, entity_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT taken_at, brief_json FROM snapshots WHERE entity_id = ? "
        "ORDER BY taken_at DESC, id DESC LIMIT 1",
        (entity_id,),
    ).fetchone()
    if not row:
        return None
    payload: dict[str, Any] = {}
    if row["brief_json"]:
        try:
            payload = json.loads(row["brief_json"])
        except json.JSONDecodeError:
            payload = {}
    payload.setdefault("headline", "No supported one-line description yet.")
    payload.setdefault("questions", [])
    payload.setdefault("sections", [])
    payload["generated_at"] = row["taken_at"]
    return payload


def _loaded_plugin():
    """The plugin package if this process already has it, without loading it.

    Read-only: looks in `sys.modules` for the module Hermes itself imported, and
    returns None when the dashboard runs somewhere the plugin was never loaded.
    """
    target = str((Path(__file__).resolve().parent.parent / "__init__.py"))
    for module in list(sys.modules.values()):
        if getattr(module, "__file__", None) == target:
            return module
    return None


@router.get("/dossiers")
async def list_dossiers() -> dict[str, Any]:
    conn = _connection()
    try:
        rows = conn.execute(
            "SELECT e.id, e.canonical_name, e.kind, e.domain, e.context, e.purpose, e.updated_at, "
            "  (SELECT COUNT(*) FROM claims c WHERE c.entity_id = e.id) AS claims, "
            "  (SELECT COUNT(*) FROM claims c WHERE c.entity_id = e.id AND c.status = 'contested') AS contested, "
            "  (SELECT COUNT(*) FROM snapshots s WHERE s.entity_id = e.id) AS snapshots, "
            "  (SELECT MAX(taken_at) FROM snapshots s WHERE s.entity_id = e.id) AS last_snapshot "
            "FROM entities e ORDER BY COALESCE(e.updated_at, e.created_at) DESC"
        ).fetchall()
        return {"items": [dict(row) for row in rows]}
    finally:
        conn.close()


@router.get("/dossiers/{entity_id}")
async def get_dossier(entity_id: int) -> dict[str, Any]:
    conn = _connection()
    try:
        entity = _entity(conn, entity_id)
        claims = _claims(conn, entity_id)
        brief = _latest_brief(conn, entity_id)
        snapshots = [
            {"id": row["id"], "taken_at": row["taken_at"]}
            for row in conn.execute(
                "SELECT id, taken_at FROM snapshots WHERE entity_id = ? "
                "ORDER BY taken_at DESC, id DESC LIMIT 10",
                (entity_id,),
            ).fetchall()
        ]
        watch = conn.execute("SELECT * FROM watchlist WHERE entity_id = ?", (entity_id,)).fetchone()
    finally:
        conn.close()

    return {
        "entity": entity,
        "claims": claims,
        "snapshots": snapshots,
        "watchlist": dict(watch) if watch else None,
        "headline": (brief or {}).get("headline", "No snapshot yet."),
        "questions": (brief or {}).get("questions", []),
        "sections": (brief or {}).get("sections", []),
        "purpose": (brief or {}).get("purpose") or entity.get("purpose") or "",
        "context": (brief or {}).get("context") or entity.get("context") or "general",
        "generated_at": (brief or {}).get("generated_at"),
    }


@router.get("/dossiers/{entity_id}/brief", response_class=HTMLResponse)
async def get_brief(entity_id: int) -> HTMLResponse:
    conn = _connection()
    try:
        _entity(conn, entity_id)
        row = conn.execute(
            "SELECT brief_html FROM snapshots WHERE entity_id = ? ORDER BY taken_at DESC, id DESC LIMIT 1",
            (entity_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="no snapshot yet")
    return HTMLResponse(row["brief_html"] or "")


@router.get("/dossiers/{entity_id}/brief.pdf")
async def get_brief_pdf(entity_id: int):
    conn = _connection()
    try:
        _entity(conn, entity_id)
        row = conn.execute(
            "SELECT brief_pdf FROM snapshots WHERE entity_id = ? ORDER BY taken_at DESC, id DESC LIMIT 1",
            (entity_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["brief_pdf"]:
        raise HTTPException(status_code=404, detail="no PDF for this dossier yet")
    return Response(
        content=bytes(row["brief_pdf"]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="dossier-{entity_id}.pdf"'},
    )


@router.post("/dossiers/{entity_id}/refresh")
async def refresh(entity_id: int) -> dict[str, Any]:
    """Re-run the pipeline only if this process already has the plugin loaded.

    The network and the model are session concerns, so when the plugin is not
    here the honest answer is the command to run, not a silent failure.
    """
    plugin = _loaded_plugin()
    pipeline = getattr(plugin, "pipeline", None)
    if pipeline is None:
        return {
            "ok": False,
            "reason": "Refresh runs in a session: /dossier refresh <name>. The dashboard cannot fetch or extract on its own.",
        }

    conn = _connection()
    try:
        entity = _entity(conn, entity_id)
        result = pipeline.build(
            entity["canonical_name"],
            conn=conn,
            search_fn=None,
            llm=None,
            domain=entity.get("domain"),
            github=entity.get("github"),
            disambiguator=entity.get("disambiguator"),
            kind=entity.get("kind"),
            purpose=entity.get("purpose"),
            context=entity.get("context"),
        )
    finally:
        conn.close()

    if result.get("status") != "ok":
        return {"ok": False, "reason": result.get("error", "refresh failed")}
    result.pop("html", None)
    result.pop("pdf", None)
    return {
        "ok": True,
        "diff": result.get("diff"),
        "counts": result.get("counts"),
        "note": "Official site and GitHub only. Run /dossier refresh in a session for search and news.",
    }


@router.post("/dossiers/{entity_id}/forget")
async def forget(entity_id: int, body: Optional[dict] = None) -> dict[str, Any]:
    if not (body or {}).get("confirm"):
        raise HTTPException(status_code=400, detail="confirm=true is required")

    conn = _connection()
    try:
        entity = _entity(conn, entity_id)
        claim_ids = [
            row[0] for row in conn.execute("SELECT id FROM claims WHERE entity_id = ?", (entity_id,))
        ]
        evidence = 0
        if claim_ids:
            marks = ",".join("?" * len(claim_ids))
            evidence = conn.execute(f"DELETE FROM evidence WHERE claim_id IN ({marks})", claim_ids).rowcount
        snapshots = conn.execute("DELETE FROM snapshots WHERE entity_id = ?", (entity_id,)).rowcount
        watch = conn.execute("DELETE FROM watchlist WHERE entity_id = ?", (entity_id,)).rowcount
        conn.execute("DELETE FROM claims WHERE entity_id = ?", (entity_id,))
        conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        conn.commit()
    finally:
        conn.close()

    # The rendered briefs go too, otherwise "forget" leaves the document behind.
    removed = 0
    slug = "".join(ch if ch.isalnum() else "-" for ch in entity["canonical_name"].lower()).strip("-") or "entity"
    try:
        briefs = _brief_dir()
    except Exception:
        briefs = None
    if briefs is not None and briefs.is_dir():
        for pattern in (f"{slug}-*.html", f"{slug}-*.pdf"):
            for path in briefs.glob(pattern):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass

    return {
        "ok": True,
        "deleted": {
            "claims": len(claim_ids),
            "evidence": evidence,
            "snapshots": snapshots,
            "watchlist": watch,
            "briefs": removed,
        },
    }
