"""Tool handlers. Every one returns a JSON string, including on error."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from . import db
from . import pipeline
from . import store
from .adapters.base import now_iso
from .models import Claim, Evidence
from .pipeline import Config


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60] or "entity"


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _config(ctx) -> Config:
    values: dict[str, Any] = {}
    for key in pipeline.DEFAULTS:
        try:
            values[key] = ctx.get_config(key, default=pipeline.DEFAULTS[key])
        except Exception:
            values[key] = pipeline.DEFAULTS[key]
    return Config.from_mapping(values)


def _search_fn(ctx):
    def search(query: str, limit: int):
        return ctx.dispatch_tool("web_search", {"query": query, "limit": int(limit)})

    return search


def _llm(ctx):
    try:
        return ctx.llm
    except Exception:
        return None


def _brief_dir() -> Path:
    from plugins.plugin_storage import plugin_data_dir  # noqa: PLC0415

    path = plugin_data_dir(db.PLUGIN_ID) / "briefs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_brief(name: str, html: str) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = _brief_dir() / f"{_slug(name)}-{stamp}.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


def _stored_claims(conn, entity_id: int) -> list[Claim]:
    rows = conn.execute("SELECT * FROM claims WHERE entity_id = ? ORDER BY confidence DESC", (entity_id,)).fetchall()
    claims: list[Claim] = []
    for row in rows:
        evidence_rows = conn.execute("SELECT * FROM evidence WHERE claim_id = ?", (row["id"],)).fetchall()
        claims.append(
            Claim(
                predicate=row["predicate"],
                value=row["value"],
                confidence=row["confidence"],
                status=row["status"],
                evidence=[
                    Evidence(
                        source_url=e["source_url"],
                        source_type=e["source_type"],
                        quote=e["quote"],
                        retrieved_at=e["retrieved_at"],
                        published_at=e["published_at"],
                    )
                    for e in evidence_rows
                ],
            )
        )
    return claims


def build(args: dict, *, ctx=None, **kwargs) -> str:
    try:
        name = str(args.get("name", "")).strip()
        if not name:
            return _dump({"error": "name is required"})
        kind = args.get("kind")
        conn = db.connect()
        try:
            result = pipeline.build(
                name,
                conn=conn,
                search_fn=_search_fn(ctx) if ctx is not None else None,
                llm=_llm(ctx) if ctx is not None else None,
                config=_config(ctx) if ctx is not None else Config(),
                disambiguator=args.get("disambiguator"),
                domain=args.get("domain"),
                github=args.get("github"),
                kind=kind,
                purpose=args.get("purpose"),
            )
        finally:
            conn.close()

        if result.get("status") != "ok":
            return _dump(result)

        result["brief_path"] = _write_brief(name, result["html"])
        for key in ("html",):
            result.pop(key, None)
        return _dump(result)
    except Exception as exc:
        return _dump({"error": f"dossier_build failed: {type(exc).__name__}: {exc}"})


def show(args: dict, *, ctx=None, **kwargs) -> str:
    try:
        ref = str(args.get("name", "")).strip()
        if not ref:
            return _dump({"error": "name is required"})
        conn = db.connect()
        try:
            matches = db.find_entities(conn, ref)
            if not matches:
                return _dump({"error": f"No stored dossier matches {ref!r}. Build one first."})
            if len(matches) > 1:
                return _dump(
                    {
                        "status": "ambiguous",
                        "error": f"{len(matches)} stored dossiers match {ref!r}; pick a numeric id.",
                        "candidates": [
                            {"id": m["id"], "name": m["canonical_name"], "domain": m.get("domain")}
                            for m in matches
                        ],
                    }
                )
            entity = matches[0]
            snapshot = store.recent_snapshots(conn, entity["id"], limit=1)
            claims = _stored_claims(conn, entity["id"])
        finally:
            conn.close()

        if not snapshot:
            return _dump({"error": f"No snapshot stored for {entity['canonical_name']!r}."})

        brief_path = _write_brief(entity["canonical_name"], snapshot[0].get("brief_html") or "")
        return _dump(
            {
                "status": "ok",
                "entity": {"id": entity["id"], "name": entity["canonical_name"], "kind": entity["kind"]},
                "taken_at": snapshot[0]["taken_at"],
                "claims": len(claims),
                "contested": len([c for c in claims if c.status == "contested"]),
                "brief_path": brief_path,
                "note": "Run dossier_refresh to fetch fresh sources and get a diff.",
            }
        )
    except Exception as exc:
        return _dump({"error": f"dossier_show failed: {type(exc).__name__}: {exc}"})


def diff(args: dict, *, ctx=None, **kwargs) -> str:
    try:
        ref = str(args.get("name", "")).strip()
        if not ref:
            return _dump({"error": "name is required"})
        conn = db.connect()
        try:
            entity = db.find_entity(conn, ref)
            if not entity:
                return _dump({"error": f"No stored dossier matches {ref!r}."})
            result = store.latest_diff(conn, entity["id"])
        finally:
            conn.close()

        if result is None:
            return _dump(
                {
                    "status": "no_diff",
                    "error": "Only one snapshot exists, so there is nothing to compare yet. Run dossier_refresh.",
                }
            )
        return _dump({"status": "ok", "entity": entity["canonical_name"], **result})
    except Exception as exc:
        return _dump({"error": f"dossier_diff failed: {type(exc).__name__}: {exc}"})


def refresh(args: dict, *, ctx=None, **kwargs) -> str:
    try:
        ref = str(args.get("name", "")).strip()
        if not ref:
            return _dump({"error": "name is required"})
        conn = db.connect()
        try:
            entity = db.find_entity(conn, ref)
            if not entity:
                return _dump({"error": f"No stored dossier matches {ref!r}. Build one first."})
            result = pipeline.build(
                entity["canonical_name"],
                conn=conn,
                search_fn=_search_fn(ctx) if ctx is not None else None,
                llm=_llm(ctx) if ctx is not None else None,
                config=_config(ctx) if ctx is not None else Config(),
                domain=entity.get("domain"),
                github=entity.get("github"),
                disambiguator=entity.get("disambiguator"),
                kind=entity.get("kind"),
                purpose=entity.get("purpose"),
            )
        finally:
            conn.close()

        if result.get("status") != "ok":
            return _dump(result)
        result["brief_path"] = _write_brief(entity["canonical_name"], result.pop("html"))
        return _dump(result)
    except Exception as exc:
        return _dump({"error": f"dossier_refresh failed: {type(exc).__name__}: {exc}"})


def forget(args: dict, *, ctx=None, **kwargs) -> str:
    try:
        ref = str(args.get("name", "")).strip()
        if not args.get("confirm"):
            return _dump({"error": "Refusing to delete without confirm=true."})
        if not ref:
            return _dump({"error": "name is required"})
        conn = db.connect()
        try:
            entity = db.find_entity(conn, ref)
            if not entity:
                return _dump({"error": f"No stored dossier matches {ref!r}."})
            counts = db.delete_entity(conn, entity["id"])
        finally:
            conn.close()
        return _dump({"status": "deleted", "entity": entity["canonical_name"], "deleted": counts})
    except Exception as exc:
        return _dump({"error": f"dossier_forget failed: {type(exc).__name__}: {exc}"})


HANDLERS = {
    "dossier_build": build,
    "dossier_show": show,
    "dossier_diff": diff,
    "dossier_refresh": refresh,
    "dossier_forget": forget,
}
