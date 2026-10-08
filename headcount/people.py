import secrets
import sqlite3

from headcount import access_log, db
from headcount.actors import Actor, require, require_visible, visible_ids

PERSON_FIELDS = (
    "id, name, title, team, manager_id, location, kind, start_date, end_date, entered_at, entered_by, last_import_id"
)


def new_token() -> str:
    return secrets.token_hex(16)


def status_for(start_date: str, end_date: str | None, day: str) -> str:
    if end_date and end_date < day:
        return "left"
    if start_date > day:
        return "starting"
    return "active"


def _with_status(row: sqlite3.Row) -> dict:
    person = dict(row)
    person["status"] = status_for(person["start_date"], person["end_date"], db.today().isoformat())
    return person


def list_people(conn: sqlite3.Connection, actor: Actor, include_left: bool = False) -> list[dict]:
    ids = visible_ids(conn, actor)
    rows = conn.execute(f"SELECT {PERSON_FIELDS} FROM people ORDER BY team, name")
    people = [_with_status(r) for r in rows if ids is None or r["id"] in ids]
    return [p for p in people if include_left or p["status"] != "left"]


def get_person(conn: sqlite3.Connection, actor: Actor, person_id: str) -> dict:
    require_visible(conn, actor, person_id)
    row = conn.execute(f"SELECT {PERSON_FIELDS} FROM people WHERE id = ?", (person_id,)).fetchone()
    if row is None:
        raise db.NotFound("no_such_person", f"no person {person_id}")
    return _with_status(row)


def record_end_date(conn: sqlite3.Connection, actor: Actor, person_id: str, end_date: str) -> None:
    require(actor, "people")
    row = conn.execute("SELECT start_date FROM people WHERE id = ?", (person_id,)).fetchone()
    if row is None:
        raise db.NotFound("no_such_person", f"no person {person_id}")
    if end_date < row["start_date"]:
        raise db.Refused("end_before_start", "an end date cannot come before the start date")
    conn.execute("UPDATE people SET end_date = ? WHERE id = ?", (end_date, person_id))


def last_four(value: str) -> str:
    characters = [c for c in value if c.isalnum()]
    if len(characters) < 4:
        raise db.Refused("identifier_too_short", "an identifier needs at least four letters or digits")
    return "".join(characters[-4:])


def set_identifier(conn: sqlite3.Connection, actor: Actor, person_id: str, value: str) -> str:
    """Keep only the last four characters of the identifier; the rest is never stored."""
    require(actor, "people")
    db.require_person(conn, person_id)
    kept = last_four(value)
    conn.execute(
        "INSERT INTO identifiers (person_id, last_four, entered_at) VALUES (?, ?, ?)"
        " ON CONFLICT (person_id) DO UPDATE SET last_four = excluded.last_four, entered_at = excluded.entered_at",
        (person_id, kept, db.now()),
    )
    return kept


def read_identifier(conn: sqlite3.Connection, actor: Actor, person_id: str) -> str | None:
    require(actor, "people")
    db.require_person(conn, person_id)
    with conn:
        access_log.record(conn, actor, "identifier", [person_id])
        row = conn.execute("SELECT last_four FROM identifiers WHERE person_id = ?", (person_id,)).fetchone()
    return row["last_four"] if row else None
