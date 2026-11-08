"""Watchlist: cadence, the calendar hint, and cleanup on delete."""

from __future__ import annotations

import pytest

from dossier import db


@pytest.fixture()
def conn(tmp_path):
    connection = db.connect(tmp_path / "watch.db")
    connection.execute(
        "INSERT INTO entities (kind, canonical_name, domain, created_at) VALUES ('org', 'Acme Robotics', 'acme.example', '2026-11-09')"
    )
    connection.commit()
    yield connection
    connection.close()


def test_setting_a_cadence_round_trips(conn):
    state = db.set_watch(conn, 1, cadence="weekly", calendar_hint="board meeting, first Tuesday")
    assert state["cadence"] == "weekly"
    assert state["calendar_hint"] == "board meeting, first Tuesday"
    assert db.get_watch(conn, 1)["cadence"] == "weekly"


def test_the_cadence_can_change(conn):
    db.set_watch(conn, 1, cadence="daily")
    db.set_watch(conn, 1, cadence="weekly")
    assert db.get_watch(conn, 1)["cadence"] == "weekly"


def test_off_removes_the_row(conn):
    db.set_watch(conn, 1, cadence="daily")
    assert db.set_watch(conn, 1, cadence="off")["cadence"] == "off"
    assert db.get_watch(conn, 1) is None


def test_an_unknown_cadence_is_refused(conn):
    with pytest.raises(ValueError):
        db.set_watch(conn, 1, cadence="hourly")


def test_the_watchlist_lists_with_names(conn):
    db.set_watch(conn, 1, cadence="manual")
    listed = db.list_watch(conn)
    assert listed[0]["canonical_name"] == "Acme Robotics"


def test_forget_drops_the_watchlist_entry(conn):
    db.set_watch(conn, 1, cadence="daily")
    db.delete_entity(conn, 1)
    assert db.list_watch(conn) == []
