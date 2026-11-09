"""Storage for Dossier: schema, connection, and small query helpers.

The database lives in Hermes' per-plugin data directory so it survives
`hermes plugins update` and `hermes plugins remove`, and follows the active
profile. Tests pass an explicit path instead, which is why the import of
`plugins.plugin_storage` is deferred until a real connection is needed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

PLUGIN_ID = "dossier"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,                   -- org | person
  canonical_name TEXT NOT NULL,
  aliases TEXT,                         -- JSON array
  domain TEXT,
  registry_id TEXT,                     -- ABN, company number, CIK
  country TEXT,
  disambiguator TEXT,                   -- employer, role, location
  purpose TEXT,
  context TEXT,                   -- interview | sales | partnership | diligence | supplier | general                         -- why this dossier exists (section 12)
  retention_days INTEGER,
  github TEXT,                          -- org slug, for the GitHub adapter
  created_at TEXT NOT NULL,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS claims (
  id INTEGER PRIMARY KEY,
  entity_id INTEGER NOT NULL,
  predicate TEXT NOT NULL,
  value TEXT NOT NULL,
  confidence REAL NOT NULL,
  status TEXT NOT NULL,                 -- supported | contested | unconfirmed
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  UNIQUE (entity_id, predicate, value)
);

CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY,
  claim_id INTEGER NOT NULL,
  source_url TEXT NOT NULL,
  source_type TEXT NOT NULL,            -- registry | official | news | search | github
  published_at TEXT,
  retrieved_at TEXT NOT NULL,
  quote TEXT NOT NULL,                  -- <= 500 chars, verbatim from the page
  quote_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY,
  entity_id INTEGER NOT NULL,
  taken_at TEXT NOT NULL,
  brief_html TEXT NOT NULL,
  claims_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlist (
  entity_id INTEGER PRIMARY KEY,
  cadence TEXT,                         -- manual | daily | weekly
  calendar_hint TEXT,
  last_run TEXT
);

CREATE INDEX IF NOT EXISTS idx_claims_entity ON claims (entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence (claim_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_entity ON snapshots (entity_id, taken_at DESC);
"""


def connect(path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Open the dossier database and make sure the schema exists.

    With no path, uses Hermes' plugin database (WAL, thread-friendly, profile
    scoped). With a path, uses that file, for tests and for the dashboard
    backend, which must not depend on a plugin context.
    """
    if path is None:
        from plugins.plugin_storage import plugin_db  # noqa: PLC0415 - host import

        conn = plugin_db(PLUGIN_ID)
    else:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive column migrations, so an existing install keeps its data."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(snapshots)").fetchall()}
    if "brief_pdf" not in columns:
        conn.execute("ALTER TABLE snapshots ADD COLUMN brief_pdf BLOB")
    entity_columns = {row[1] for row in conn.execute("PRAGMA table_info(entities)").fetchall()}
    if "country" not in entity_columns:
        conn.execute("ALTER TABLE entities ADD COLUMN country TEXT")
    if "purpose" not in entity_columns:
        conn.execute("ALTER TABLE entities ADD COLUMN purpose TEXT")
    if "context" not in entity_columns:
        conn.execute("ALTER TABLE entities ADD COLUMN context TEXT")


def rows(cursor: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in cursor]


def find_entity(conn: sqlite3.Connection, ref: str) -> Optional[dict[str, Any]]:
    """Resolve a user-supplied reference to one entity row, or None.

    Accepts a numeric id or a name/alias match, case-insensitively. If a name
    matches more than one entity the caller must disambiguate, so this returns
    None rather than guessing, the same rule the resolver follows.
    """
    ref = (ref or "").strip()
    if not ref:
        return None
    if ref.isdigit():
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (int(ref))).fetchone()
        return dict(row) if row else None

    exact = conn.execute(
        "SELECT * FROM entities WHERE lower(canonical_name) = lower(?)", (ref,)
    ).fetchall()
    if len(exact) == 1:
        return dict(exact[0])
    if len(exact) > 1:
        return None
    like = conn.execute(
        "SELECT * FROM entities WHERE lower(canonical_name) LIKE lower(?) "
        "OR lower(COALESCE(aliases, '')) LIKE lower(?)",
        (f"%{ref}%", f"%{ref}%")).fetchall()
    return dict(like[0]) if len(like) == 1 else None


def find_entities(conn: sqlite3.Connection, ref: str) -> list[dict[str, Any]]:
    """All entities matching a reference, for the ambiguous case."""
    ref = (ref or "").strip()
    if not ref:
        return []
    return rows(
        conn.execute(
            "SELECT * FROM entities WHERE lower(canonical_name) LIKE lower(?) "
            "OR lower(COALESCE(aliases, '')) LIKE lower(?) ORDER BY id",
            (f"%{ref}%", f"%{ref}%")).fetchall()
    )


CADENCES = ("off", "manual", "daily", "weekly")


def set_watch(
    conn: sqlite3.Connection, entity_id: int, *, cadence: str, calendar_hint: Optional[str] = None
) -> dict[str, Any]:
    """Record the refresh cadence a user asked for. `off` removes the row."""
    cadence = (cadence or "manual").lower()
    if cadence not in CADENCES:
        raise ValueError(f"cadence must be one of {CADENCES}")
    if cadence == "off":
        conn.execute("DELETE FROM watchlist WHERE entity_id = ?", (entity_id,))
        conn.commit()
        return {"entity_id": entity_id, "cadence": "off"}
    conn.execute(
        "INSERT INTO watchlist (entity_id, cadence, calendar_hint, last_run) VALUES (?, ?, ?, NULL) "
        "ON CONFLICT(entity_id) DO UPDATE SET cadence = excluded.cadence, calendar_hint = excluded.calendar_hint",
        (entity_id, cadence, calendar_hint))
    conn.commit()
    return get_watch(conn, entity_id) or {}


def get_watch(conn: sqlite3.Connection, entity_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM watchlist WHERE entity_id = ?", (entity_id,)).fetchone()
    return dict(row) if row else None


def list_watch(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows(
        conn.execute(
            "SELECT w.*, e.canonical_name, e.domain FROM watchlist w "
            "JOIN entities e ON e.id = w.entity_id ORDER BY e.canonical_name"
        ).fetchall()
    )


def delete_entity(conn: sqlite3.Connection, entity_id: int) -> dict[str, int]:
    """Delete an entity and everything hanging off it. Returns counts."""
    claim_ids = [
        r[0] for r in conn.execute("SELECT id FROM claims WHERE entity_id = ?", (entity_id,))
    ]
    counts = {"claims": len(claim_ids), "evidence": 0, "snapshots": 0, "watchlist": 0}
    if claim_ids:
        marks = ",".join("?" * len(claim_ids))
        counts["evidence"] = conn.execute(
            f"DELETE FROM evidence WHERE claim_id IN ({marks})", claim_ids
        ).rowcount
    counts["snapshots"] = conn.execute(
        "DELETE FROM snapshots WHERE entity_id = ?", (entity_id,)
    ).rowcount
    counts["watchlist"] = conn.execute(
        "DELETE FROM watchlist WHERE entity_id = ?", (entity_id,)
    ).rowcount
    conn.execute("DELETE FROM claims WHERE entity_id = ?", (entity_id,))
    conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
    conn.commit()
    return counts
