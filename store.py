"""Snapshots and the diff — the reason this is a plugin and not a prompt.

A snapshot stores the brief HTML and the claim set as JSON. The diff compares
the newest snapshot with the one before it and reports only what changed:
claims that appeared, claims that disappeared, and claims whose confidence or
status moved. Unchanged claims are deliberately absent from the diff.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from .models import Claim


def claims_payload(claims: list[Claim]) -> str:
    return json.dumps([c.as_dict() for c in claims], ensure_ascii=False, sort_keys=True)


def save_snapshot(conn: sqlite3.Connection, entity_id: int, taken_at: str, brief_html: str, claims: list[Claim]) -> int:
    cursor = conn.execute(
        "INSERT INTO snapshots (entity_id, taken_at, brief_html, claims_json) VALUES (?, ?, ?, ?)",
        (entity_id, taken_at, brief_html, claims_payload(claims)),
    )
    conn.commit()
    return int(cursor.lastrowid)


def recent_snapshots(conn: sqlite3.Connection, entity_id: int, limit: int = 2) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, entity_id, taken_at, brief_html, claims_json FROM snapshots "
        "WHERE entity_id = ? ORDER BY taken_at DESC, id DESC LIMIT ?",
        (entity_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _key(claim: dict[str, Any]) -> tuple[str, str]:
    return (str(claim.get("predicate")), " ".join(str(claim.get("value", "")).casefold().split()))


def _index(claims_json: str) -> dict[tuple[str, str], dict[str, Any]]:
    try:
        payload = json.loads(claims_json or "[]")
    except json.JSONDecodeError:
        return {}
    return {_key(c): c for c in payload if isinstance(c, dict)}


def diff_claims(previous: str, current: str) -> dict[str, Any]:
    """Compare two claim payloads. Returns added / removed / changed only."""
    before = _index(previous)
    after = _index(current)

    added = [after[k] for k in after.keys() - before.keys()]
    removed = [before[k] for k in before.keys() - after.keys()]
    changed = []
    for key in before.keys() & after.keys():
        old, new = before[key], after[key]
        if (
            round(float(old.get("confidence", 0)), 2) != round(float(new.get("confidence", 0)), 2)
            or old.get("status") != new.get("status")
        ):
            changed.append(
                {
                    "predicate": new.get("predicate"),
                    "value": new.get("value"),
                    "from": {"confidence": old.get("confidence"), "status": old.get("status")},
                    "to": {"confidence": new.get("confidence"), "status": new.get("status")},
                }
            )

    for bucket in (added, removed):
        bucket.sort(key=lambda c: (str(c.get("predicate")), str(c.get("value"))))
    changed.sort(key=lambda c: (str(c.get("predicate")), str(c.get("value"))))

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "changed_count": len(added) + len(removed) + len(changed),
    }


def latest_diff(conn: sqlite3.Connection, entity_id: int) -> Optional[dict[str, Any]]:
    snapshots = recent_snapshots(conn, entity_id, limit=2)
    if len(snapshots) < 2:
        return None
    newest, previous = snapshots[0], snapshots[1]
    result = diff_claims(previous["claims_json"], newest["claims_json"])
    result["from"] = previous["taken_at"]
    result["to"] = newest["taken_at"]
    return result
