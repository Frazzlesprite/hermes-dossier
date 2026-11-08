"""Dossier — sourced, dated, refreshable briefs, and what changed since.

Registration only wires things up. Nothing here touches the network or opens a
database, because `hermes plugins doctor` and `hermes plugins validate` import
this module and run `register()` in a probe that blocks sockets.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from . import schemas, tools

logger = logging.getLogger(__name__)

PLUGIN_ID = "dossier"

_entity_cache: tuple[float, list[tuple[str, int]]] = (0.0, [])
_CACHE_SECONDS = 60.0


def _known_entities() -> list[tuple[str, int]]:
    """(name, id) pairs, cached for a minute. Never raises."""
    global _entity_cache
    stamp, cached = _entity_cache
    if time.time() - stamp < _CACHE_SECONDS and cached:
        return cached
    try:
        from .db import connect  # noqa: PLC0415

        conn = connect()
        try:
            rows = conn.execute("SELECT id, canonical_name FROM entities ORDER BY id").fetchall()
            cached = [(str(r["canonical_name"]), int(r["id"])) for r in rows]
        finally:
            conn.close()
    except Exception:
        cached = []
    _entity_cache = (time.time(), cached)
    return cached


def recall_dossier(session_id: str = "", user_message: str = "", **kwargs: Any) -> Optional[dict[str, str]]:
    """Inject a pointer when the user names an entity we already hold.

    Observer-shaped and cheap: it says a dossier exists and when it was taken.
    It never injects claim text, so a stale snapshot cannot masquerade as fact.
    """
    try:
        message = (user_message or "")[:2000].casefold()
        if not message.strip():
            return None
        for name, entity_id in _known_entities():
            if len(name) < 3 or name.casefold() not in message:
                continue
            from .db import connect  # noqa: PLC0415

            conn = connect()
            try:
                row = conn.execute(
                    "SELECT taken_at FROM snapshots WHERE entity_id = ? ORDER BY taken_at DESC LIMIT 1",
                    (entity_id,),
                ).fetchone()
            finally:
                conn.close()
            if not row:
                continue
            return {
                "context": (
                    f"[dossier] This user already holds a dossier on {name} "
                    f"(id {entity_id}, snapshot {row['taken_at']}). Offer /dossier diff {name} "
                    "for what changed, or /dossier refresh before relying on it."
                )
            }
    except Exception:
        logger.debug("dossier: recall hook skipped", exc_info=True)
    return None


def _parse(raw_args: str) -> tuple[str, str]:
    parts = (raw_args or "").strip().split(None, 1)
    verbs = {"build", "show", "diff", "refresh", "forget", "watch"}
    if parts and parts[0].lower() in verbs:
        return parts[0].lower(), (parts[1] if len(parts) > 1 else "")
    return "build", (raw_args or "").strip()


USAGE = (
    "Usage: /dossier <name>\n"
    "       /dossier show|diff|refresh|forget <name>\n"
    "       /dossier watch <name> [off|manual|daily|weekly]\n"
    "`forget` requires confirm=true on the tool, or the delete button in the Desktop."
)


def db_cadences() -> tuple[str, ...]:
    try:
        from .db import CADENCES  # noqa: PLC0415

        return CADENCES
    except Exception:
        return ("off", "manual", "daily", "weekly")


def _register_blueprint(ctx) -> None:
    """A scheduled refresh users can pick in /blueprint without touching cron."""
    if not hasattr(ctx, "register_automation_blueprint"):
        return
    try:
        ctx.register_automation_blueprint(
            "refresh",
            title="Dossier refresh",
            description="Re-fetch a saved dossier before a regular meeting and report only what changed.",
            category="work",
            schedule_template="{minute} {hour} * * 1-5",
            prompt_template=(
                "Refresh the dossier on {entity}: call dossier_refresh with name={entity}, "
                "then report only what changed since the previous snapshot. If nothing changed, "
                "say so in one line."
            ),
            slots=[
                {"name": "entity", "type": "text", "label": "Which entity?", "default": "Acme Robotics"},
                {"name": "time", "type": "time", "label": "What time?", "default": "07:30"},
            ],
            tags=["research", "dossier"],
        )
    except Exception:
        logger.debug("dossier: automation blueprint not registered", exc_info=True)


def register(ctx) -> None:
    for schema in schemas.ALL:
        name = schema["name"]
        handler = tools.HANDLERS[name]
        ctx.register_tool(
            name=name,
            toolset=PLUGIN_ID,
            schema=schema,
            handler=(lambda args, _h=handler, **kwargs: _h(args, ctx=ctx, **kwargs)),
        )

    ctx.register_hook("pre_llm_call", recall_dossier)
    _register_blueprint(ctx)

    def _command(raw_args: str, **kwargs: Any) -> str:
        verb, rest = _parse(raw_args)
        if not rest:
            return USAGE
        if verb == "watch":
            pieces = rest.rsplit(None, 1)
            if len(pieces) == 2 and pieces[1].lower() in db_cadences():
                rest, cadence = pieces[0], pieces[1].lower()
            else:
                cadence = "manual"
            payload = {"name": rest, "cadence": cadence}
        else:
            payload = {"name": rest}
        if verb == "forget":
            payload["confirm"] = True
        handler = tools.HANDLERS[f"dossier_{verb}"]
        result = json.loads(handler(payload, ctx=ctx, **kwargs) or "{}")
        if result.get("error"):
            return f"Dossier: {result['error']}"
        if verb == "watch":
            watch_state = result.get("watch") or {}
            return f"{result['entity']}: cadence {watch_state.get('cadence', cadence)}."
        if verb == "diff":
            if not result.get("changed_count"):
                return f"No changes since {result.get('from')}."
            lines = [f"Changes since {result.get('from')}:"]
            for item in result.get("added", [])[:5]:
                lines.append(f"+ {item['predicate']}: {item['value']}")
            for item in result.get("removed", [])[:5]:
                lines.append(f"- {item['predicate']}: {item['value']}")
            for item in result.get("changed", [])[:5]:
                lines.append(f"~ {item['predicate']}: {item['value']} ({item['from']['status']} → {item['to']['status']})")
            return "\n".join(lines)
        if verb == "forget":
            return f"Deleted the dossier on {result.get('entity')}: {result.get('deleted')}"
        card = result.get("card") or result.get("headline") or "Built."
        paths = [p for p in (result.get("brief_path"), result.get("pdf_path")) if p]
        return f"{card}\n\nFull brief: {paths[0]}" + (f"\nPDF: {result['pdf_path']}" if result.get("pdf_path") else "") if paths else card

    ctx.register_command(
        "dossier",
        handler=_command,
        description="Build, show, diff, refresh or forget a sourced dossier",
        args_hint="[show|diff|refresh|forget] <name>",
    )

    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.is_dir() and hasattr(ctx, "register_skill"):
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                ctx.register_skill(child.name, skill_md)

    logger.debug("dossier: registered %d tools", len(schemas.ALL))
