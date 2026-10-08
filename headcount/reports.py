import calendar
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from fractions import Fraction

from headcount import access_log, db
from headcount.actors import PAY_ROLES, Actor, Forbidden, require, visible_ids
from headcount.pay import rate_on


def month_days(month: str) -> list[str]:
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise db.Refused("bad_month", f"{month!r} is not a YYYY-MM month") from None
    year, number = first.year, first.month
    return [(first + timedelta(days=n)).isoformat() for n in range(calendar.monthrange(year, number)[1])]


def daily_amount(rate: dict, day: str) -> Fraction:
    year, month = int(day[:4]), int(day[5:7])
    if rate["per"] == "year":
        return Fraction(rate["amount_cents"], 366 if calendar.isleap(year) else 365)
    return Fraction(rate["amount_cents"], calendar.monthrange(year, month)[1])


def to_cents(amount: Fraction) -> int:
    return int(amount + Fraction(1, 2))


def employed_on(person: dict, day: str) -> bool:
    return person["start_date"] <= day and (person["end_date"] is None or person["end_date"] >= day)


def cost_of_month(people: list[dict], rates_by_person: dict[str, list[dict]], month: str) -> dict:
    """Cost each person for every day they were employed, at the rate in effect on that day."""
    days = month_days(month)
    teams: dict[str, dict] = defaultdict(lambda: {"headcount": 0, "cost_cents": 0})
    lines = []
    for person in people:
        person_rates = rates_by_person.get(person["id"], [])
        cost = Fraction(0)
        for day in days:
            rate = rate_on(person_rates, day) if employed_on(person, day) else None
            if rate:
                cost += daily_amount(rate, day)
        cents = to_cents(cost)
        team = teams[person["team"]]
        team["cost_cents"] += cents
        if employed_on(person, days[-1]):
            team["headcount"] += 1
        lines.append({"id": person["id"], "name": person["name"], "team": person["team"], "cost_cents": cents})
    return {
        "month": month,
        "headcount": sum(t["headcount"] for t in teams.values()),
        "total_cents": sum(t["cost_cents"] for t in teams.values()),
        "teams": [{"team": name, **values} for name, values in sorted(teams.items())],
        "people": lines,
    }


def people_in_month(conn: sqlite3.Connection, month: str) -> list[dict]:
    days = month_days(month)
    rows = conn.execute(
        "SELECT id, name, team, start_date, end_date FROM people"
        " WHERE start_date <= ? AND (end_date IS NULL OR end_date >= ?) ORDER BY team, name",
        (days[-1], days[0]),
    )
    return [dict(r) for r in rows]


def monthly_cost(conn: sqlite3.Connection, actor: Actor, month: str) -> dict:
    require(actor, *PAY_ROLES)
    people = people_in_month(conn, month)
    ids = [p["id"] for p in people]
    if not ids:
        return cost_of_month([], {}, month)
    with conn:
        access_log.record(conn, actor, "pay_rate", ids)
        rates: dict[str, list[dict]] = defaultdict(list)
        for row in conn.execute(
            f"SELECT id, person_id, amount_cents, per, effective_date FROM pay_rates"
            f" WHERE person_id IN ({', '.join('?' for _ in ids)}) ORDER BY effective_date, id",
            ids,
        ):
            rates[row["person_id"]].append(dict(row))
    return cost_of_month(people, rates, month)


def save_monthly_report(conn: sqlite3.Connection, actor: Actor, month: str) -> dict:
    """The monthly pack: run by the monthly-report system actor and kept with its totals."""
    if actor.system is None:
        raise Forbidden("system_actor_only", "the saved monthly report is run by a system actor")
    report = monthly_cost(conn, actor, month)
    with conn:
        conn.execute(
            "INSERT INTO monthly_reports (month, generated_at, generated_by, headcount, total_cents)"
            " VALUES (?, ?, ?, ?, ?)",
            (month, db.now(), actor.system, report["headcount"], report["total_cents"]),
        )
    return report


def saved_reports(conn: sqlite3.Connection, actor: Actor) -> list[dict]:
    require(actor, *PAY_ROLES)
    rows = conn.execute(
        "SELECT month, generated_at, generated_by, headcount, total_cents FROM monthly_reports"
        " ORDER BY month DESC, generated_at DESC"
    )
    return [dict(r) for r in rows]


def budget(conn: sqlite3.Connection, actor: Actor, month: str) -> dict:
    """This month's cost plus what each open planned hire adds, at the middle of its pay band."""
    current = monthly_cost(conn, actor, month)
    days = month_days(month)
    planned = []
    for row in conn.execute(
        "SELECT id, role, team, planned_start, band_min_cents, band_max_cents FROM hiring_plan"
        " WHERE status = 'open' AND planned_start <= ? ORDER BY planned_start, id",
        (days[-1],),
    ):
        yearly = (row["band_min_cents"] + row["band_max_cents"]) // 2
        rate = {"per": "year", "amount_cents": yearly}
        adds = to_cents(sum((daily_amount(rate, d) for d in days if d >= row["planned_start"]), Fraction(0)))
        planned.append({**dict(row), "midpoint_cents_per_year": yearly, "adds_cents": adds})
    return {
        "month": month,
        "current_cents": current["total_cents"],
        "planned": planned,
        "total_cents": current["total_cents"] + sum(p["adds_cents"] for p in planned),
    }


def headcount(conn: sqlite3.Connection, actor: Actor, day: str) -> dict:
    """People employed on a day, by team, kind and location, over the people the actor may see."""
    if actor.role == "staff":
        raise Forbidden("role_not_allowed", "staff see their own record only")
    ids = visible_ids(conn, actor)
    if actor.role == "manager":
        ids.discard(actor.person_id)
    rows = [
        dict(r)
        for r in conn.execute("SELECT id, team, kind, location, start_date, end_date FROM people")
        if (ids is None or r["id"] in ids) and employed_on(dict(r), day)
    ]
    by_team: dict[str, dict] = defaultdict(lambda: {"employee": 0, "contractor": 0})
    by_location: dict[str, int] = defaultdict(int)
    for row in rows:
        by_team[row["team"]][row["kind"]] += 1
        by_location[row["location"]] += 1
    return {
        "day": day,
        "headcount": len(rows),
        "teams": [{"team": t, **counts} for t, counts in sorted(by_team.items())],
        "locations": dict(sorted(by_location.items())),
    }


def last_import(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT id, file_name, row_count, headcount, headcount_delta, forced, reason, run_by, at"
        " FROM imports ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None
