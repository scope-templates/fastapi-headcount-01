import sqlite3

from headcount import db, pay
from headcount.actors import PAY_ROLES, Actor, require
from headcount.people import new_token, set_identifier


def plan(conn: sqlite3.Connection, actor: Actor) -> list[dict]:
    require(actor, *PAY_ROLES)
    rows = conn.execute(
        "SELECT id, role, team, planned_start, band_min_cents, band_max_cents, status, approved_on,"
        " person_id, entered_at, entered_by FROM hiring_plan ORDER BY planned_start, id"
    )
    return [dict(r) for r in rows]


def next_person_id(conn: sqlite3.Connection) -> str:
    highest = conn.execute("SELECT MAX(CAST(substr(id, 3) AS INTEGER)) FROM people").fetchone()[0] or 0
    return f"e-{highest + 1:04d}"


def enter(
    conn: sqlite3.Connection,
    actor: Actor,
    plan_id: str,
    *,
    name: str,
    title: str,
    manager_id: str,
    location: str,
    kind: str,
    start_date: str,
    amount_cents: int,
    per: str,
    identifier: str,
    pay_reason: str | None = None,
) -> dict:
    """Enter a planned hire from the signed offer: the person, their first rate and their identifier."""
    require(actor, "people")
    row = conn.execute("SELECT status, team FROM hiring_plan WHERE id = ?", (plan_id,)).fetchone()
    if row is None:
        raise db.NotFound("no_such_plan_row", f"no plan row {plan_id}")
    if row["status"] != "open":
        raise db.Refused("plan_row_closed", f"plan row {plan_id} is {row['status']}")
    if kind not in ("employee", "contractor"):
        raise db.Refused("bad_kind", "kind must be employee or contractor")
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (manager_id,)).fetchone() is None:
        raise db.Refused("no_such_manager", f"no manager {manager_id}")
    person_id = next_person_id(conn)
    token = new_token()
    at = db.now()
    with conn:
        conn.execute(
            "INSERT INTO people (id, name, title, team, manager_id, location, kind, start_date, token,"
            " entered_at, entered_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (person_id, name.strip(), title.strip(), row["team"], manager_id, location, kind, start_date,
             token, at, actor.person_id),
        )
        pay.add_rate(conn, actor, person_id, amount_cents, per, start_date, pay_reason)
        set_identifier(conn, actor, person_id, identifier)
        conn.execute(
            "UPDATE hiring_plan SET status = 'entered', person_id = ?, entered_at = ?, entered_by = ? WHERE id = ?",
            (person_id, at, actor.person_id, plan_id),
        )
    return {"person_id": person_id, "plan_id": plan_id, "start_date": start_date, "token": token}
