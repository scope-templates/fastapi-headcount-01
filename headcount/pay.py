import sqlite3
from datetime import date

from headcount import access_log, db
from headcount.actors import PAY_ROLES, Actor, require

PERIODS = ("year", "month")


def add_rate(
    conn: sqlite3.Connection,
    actor: Actor,
    person_id: str,
    amount_cents: int,
    per: str,
    effective_date: str,
    reason: str | None = None,
) -> int:
    """Add a new rate row. A rate dated before today needs a reason."""
    require(actor, *PAY_ROLES)
    if actor.person_id is None:
        raise db.Refused("entered_by_person", "pay rates are entered by a person")
    if per not in PERIODS:
        raise db.Refused("bad_period", f"per must be one of {PERIODS}")
    if amount_cents <= 0:
        raise db.Refused("bad_amount", "amount must be positive")
    effective = date.fromisoformat(effective_date)
    reason = (reason or "").strip() or None
    if effective < db.today() and reason is None:
        raise db.Refused("past_needs_reason", f"a rate effective {effective_date} is in the past and needs a reason")
    db.require_person(conn, person_id)
    cur = conn.execute(
        "INSERT INTO pay_rates (person_id, amount_cents, currency, per, effective_date, entered_by, entered_at, reason)"
        " VALUES (?, ?, 'USD', ?, ?, ?, ?, ?)",
        (person_id, amount_cents, per, effective.isoformat(), actor.person_id, db.now(), reason),
    )
    return cur.lastrowid


def rates_for(conn: sqlite3.Connection, actor: Actor, person_id: str) -> list[dict]:
    require(actor, *PAY_ROLES)
    db.require_person(conn, person_id)
    with conn:
        access_log.record(conn, actor, "pay_rate", [person_id])
        rows = conn.execute(
            "SELECT id, amount_cents, currency, per, effective_date, entered_by, entered_at, reason"
            " FROM pay_rates WHERE person_id = ? ORDER BY effective_date, id",
            (person_id,),
        )
        return [dict(r) for r in rows]


def rate_on(rates: list[dict], day: str) -> dict | None:
    """The rate in effect on a day: the latest effective date on or before it, later entries winning ties."""
    current = None
    for rate in rates:
        if rate["effective_date"] <= day and (
            current is None or (rate["effective_date"], rate["id"]) > (current["effective_date"], current["id"])
        ):
            current = rate
    return current
