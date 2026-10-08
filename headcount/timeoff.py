import sqlite3
from datetime import date, timedelta

from headcount import db
from headcount.actors import Actor, Forbidden, require, require_visible, visible_ids

KINDS = ("vacation", "sick", "parental", "other")
NOTE_LIMIT = 60


def weekdays(first: date, last: date) -> int:
    return sum(1 for n in range((last - first).days + 1) if (first + timedelta(days=n)).weekday() < 5)


def book(
    conn: sqlite3.Connection,
    actor: Actor,
    person_id: str,
    kind: str,
    first_day: str,
    last_day: str,
    note: str = "",
) -> dict:
    """Book time off. Managers book for their own reports; the head of people books for anyone."""
    require(actor, "manager", "people")
    if actor.role == "manager":
        manager = conn.execute("SELECT manager_id FROM people WHERE id = ?", (person_id,)).fetchone()
        if manager is None or manager["manager_id"] != actor.person_id:
            raise Forbidden("not_your_report", f"{person_id} does not report to {actor.person_id}")
    if kind not in KINDS:
        raise db.Refused("bad_kind", f"kind must be one of {KINDS}")
    note = note.strip()
    if len(note) > NOTE_LIMIT:
        raise db.Refused("note_too_long", f"a note is a short reason of at most {NOTE_LIMIT} characters")
    first, last = date.fromisoformat(first_day), date.fromisoformat(last_day)
    if last < first:
        raise db.Refused("last_before_first", "the last day comes before the first day")
    if first.year != last.year:
        raise db.Refused("crosses_new_year", "book time off that crosses the new year as two requests")
    person = conn.execute("SELECT start_date, end_date FROM people WHERE id = ?", (person_id,)).fetchone()
    if person is None:
        raise db.NotFound("no_such_person", f"no person {person_id}")
    if person["end_date"] and last_day > person["end_date"]:
        raise db.Refused("after_end_date", f"{person_id} has an end date of {person['end_date']}")
    days = weekdays(first, last)
    with conn:
        cur = conn.execute(
            "INSERT INTO time_off_requests (person_id, kind, first_day, last_day, days, note, entered_by, entered_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (person_id, kind, first_day, last_day, days, note, actor.person_id, db.now()),
        )
    return {"id": cur.lastrowid, "person_id": person_id, "kind": kind, "first_day": first_day,
            "last_day": last_day, "days": days}


def requests_for(conn: sqlite3.Connection, actor: Actor, person_id: str) -> list[dict]:
    require_visible(conn, actor, person_id)
    rows = conn.execute(
        "SELECT id, kind, first_day, last_day, days, note, entered_by, entered_at"
        " FROM time_off_requests WHERE person_id = ? ORDER BY first_day",
        (person_id,),
    )
    return [dict(r) for r in rows]


def balance(conn: sqlite3.Connection, actor: Actor, person_id: str, year: int) -> dict:
    require_visible(conn, actor, person_id)
    row = conn.execute(
        "SELECT allowance_days, carried_over_days FROM time_off_balances WHERE person_id = ? AND year = ?",
        (person_id, year),
    ).fetchone()
    taken = conn.execute(
        "SELECT COALESCE(SUM(days), 0) FROM time_off_requests"
        " WHERE person_id = ? AND kind = 'vacation' AND substr(first_day, 1, 4) = ?",
        (person_id, str(year)),
    ).fetchone()[0]
    allowance = row["allowance_days"] if row else 0
    carried = row["carried_over_days"] if row else 0
    return {"person_id": person_id, "year": year, "allowance_days": allowance, "carried_over_days": carried,
            "vacation_days_booked": taken, "remaining_days": allowance + carried - taken}


def out_between(conn: sqlite3.Connection, actor: Actor, first_day: str, last_day: str) -> list[dict]:
    """Everyone the actor may see who has time off overlapping the given days."""
    ids = visible_ids(conn, actor)
    rows = conn.execute(
        "SELECT t.person_id, p.name, p.team, t.kind, t.first_day, t.last_day, t.days"
        " FROM time_off_requests t JOIN people p ON p.id = t.person_id"
        " WHERE t.first_day <= ? AND t.last_day >= ? ORDER BY t.first_day, p.name",
        (last_day, first_day),
    )
    return [dict(r) for r in rows if ids is None or r["person_id"] in ids]


def week_of(day: date) -> tuple[str, str]:
    monday = day - timedelta(days=day.weekday())
    return monday.isoformat(), (monday + timedelta(days=4)).isoformat()
