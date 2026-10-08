import csv
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from headcount import access_log, db, pay
from headcount.actors import Actor, require
from headcount.people import new_token

COLUMNS = (
    "employee_number", "name", "title", "team", "manager", "location", "kind",
    "start_date", "end_date", "pay_amount", "pay_per", "pay_effective",
)

REQUIRED = ("employee_number", "name", "title", "team", "location", "kind", "start_date")


def read_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise db.Refused("bad_columns", f"{path.name} lacks columns: {', '.join(missing)}")
        rows = [{k: (v or "").strip() for k, v in row.items() if k in COLUMNS} for row in reader]
    seen = set()
    for number, row in enumerate(rows, start=2):
        blank = [f for f in REQUIRED if not row[f]]
        if blank:
            raise db.Refused("blank_field", f"line {number}: {', '.join(blank)} left blank")
        if row["employee_number"] in seen:
            raise db.Refused("repeated_row", f"line {number}: {row['employee_number']} appears twice")
        seen.add(row["employee_number"])
        if row["kind"] not in ("employee", "contractor"):
            raise db.Refused("bad_kind", f"line {number}: kind must be employee or contractor")
        for field in ("start_date", "end_date", "pay_effective"):
            if row[field]:
                try:
                    date.fromisoformat(row[field])
                except ValueError:
                    raise db.Refused("bad_date", f"line {number}: {field} {row[field]!r} is not a YYYY-MM-DD date") from None
        if row["end_date"] and row["end_date"] < row["start_date"]:
            raise db.Refused("end_before_start", f"line {number}: end_date {row['end_date']} is before start_date")
        if row["pay_amount"]:
            try:
                row["pay_cents"] = int(Decimal(row["pay_amount"].replace(",", "")) * 100)
            except InvalidOperation:
                raise db.Refused("bad_amount", f"line {number}: pay_amount {row['pay_amount']!r} is not a number") from None
            if row["pay_per"] not in pay.PERIODS or not row["pay_effective"]:
                raise db.Refused("bad_pay", f"line {number}: pay needs pay_per (year or month) and pay_effective")
    return rows


def headcount_of(rows: list[dict], day: str) -> int:
    return sum(1 for r in rows if not r["end_date"] or r["end_date"] >= day)


def run_import(
    conn: sqlite3.Connection,
    actor: Actor,
    path: Path,
    forced: bool = False,
    reason: str | None = None,
) -> dict:
    """Load one month's file. Refuse a headcount swing of more than a fifth unless forced with a reason."""
    require(actor, "finance")
    if actor.person_id is None:
        raise db.Refused("run_by_person", "the monthly import is run by a person")
    reason = (reason or "").strip() or None
    if forced and reason is None:
        raise db.Refused("force_needs_reason", "a forced import needs a reason")
    rows = read_rows(path)
    at = db.now()
    day = at[:10]
    headcount = headcount_of(rows, day)
    previous = conn.execute("SELECT headcount FROM imports ORDER BY id DESC LIMIT 1").fetchone()
    delta = None if previous is None else headcount - previous["headcount"]
    if delta is not None and abs(delta) * 5 > previous["headcount"] and not forced:
        raise db.Refused(
            "headcount_swing",
            f"{path.name} has a headcount of {headcount} against {previous['headcount']} at the last import"
            f" ({delta:+d}); run it again with --force and a reason if that is right"
        )
    file_ids = {r["employee_number"] for r in rows}
    known = {r["id"] for r in conn.execute("SELECT id FROM people")}
    for row in rows:
        if row["manager"] and row["manager"] not in file_ids | known:
            raise db.Refused("no_such_manager", f"{row['employee_number']} names an unknown manager {row['manager']}")

    added = updated = pay_rows = 0
    with db.deferred_references(conn):
        import_id = conn.execute(
            "INSERT INTO imports (file_name, row_count, headcount, headcount_delta, forced, reason, run_by, at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (path.name, len(rows), headcount, delta, int(forced), reason, actor.person_id, at),
        ).lastrowid
        for row in rows:
            values = (row["name"], row["title"], row["team"], row["manager"] or None, row["location"], row["kind"],
                      row["start_date"], row["end_date"] or None, import_id)
            if row["employee_number"] in known:
                conn.execute(
                    "UPDATE people SET name = ?, title = ?, team = ?, manager_id = ?, location = ?, kind = ?,"
                    " start_date = ?, end_date = ?, last_import_id = ? WHERE id = ?",
                    values + (row["employee_number"],),
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO people (name, title, team, manager_id, location, kind, start_date, end_date,"
                    " last_import_id, id, token, entered_at, entered_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values + (row["employee_number"], new_token(), at, actor.person_id),
                )
                added += 1
            if row["pay_amount"] and _rate_changed(conn, row):
                pay.add_rate(conn, actor, row["employee_number"], row["pay_cents"], row["pay_per"],
                             row["pay_effective"], f"monthly import {path.name}")
                pay_rows += 1
        access_log.record(conn, actor, "pay_rate", [r["employee_number"] for r in rows if r["pay_amount"]])
    return {"import_id": import_id, "file_name": path.name, "row_count": len(rows), "headcount": headcount,
            "headcount_delta": delta, "forced": forced, "people_added": added, "people_updated": updated,
            "pay_rows_added": pay_rows}


def _rate_changed(conn: sqlite3.Connection, row: dict) -> bool:
    rates = [dict(r) for r in conn.execute(
        "SELECT id, amount_cents, per, effective_date FROM pay_rates WHERE person_id = ?", (row["employee_number"],)
    )]
    current = pay.rate_on(rates, row["pay_effective"])
    return current is None or (current["amount_cents"], current["per"]) != (row["pay_cents"], row["pay_per"])
