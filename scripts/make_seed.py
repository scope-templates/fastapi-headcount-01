"""Build data/seed.json and the two monthly import files from a fixed roster and a seeded random source.

Run from the repo root: python scripts/make_seed.py
The output is the same bytes on every run.
"""

import csv
import io
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from headcount.pay import rate_on  # noqa: E402
from headcount.reports import cost_of_month, month_days  # noqa: E402

FINANCE_LEAD = "e-0003"
HEAD_OF_PEOPLE = "e-0004"
IMPORTS = (
    {"id": 1, "file_name": "people-2026-08.csv", "at": "2026-08-04T17:42:10Z"},
    {"id": 2, "file_name": "people-2026-09.csv", "at": "2026-09-02T16:05:37Z"},
)
REPORT_MONTHS = [f"{y}-{m:02d}" for y, m in [(2025, 10), (2025, 11), (2025, 12)] + [(2026, n) for n in range(1, 10)]]

# id, name, title, team, manager, location, kind, start
ROSTER = [
    ("e-0001", "Matt Keller", "Chief executive and co-founder", "Leadership", None, "NY", "employee", "2021-03-01"),
    ("e-0002", "Laura Chen", "Chief technology officer and co-founder", "Platform", "e-0001", "CO", "employee", "2021-03-01"),
    ("e-0003", "Ruth Callahan", "Finance lead", "Operations", "e-0001", "NY", "employee", "2022-01-10"),
    ("e-0004", "Dana Morris", "Head of people and operations", "Operations", "e-0001", "IL", "employee", "2022-04-04"),
    ("e-0005", "Sam Patel", "Staff engineer", "Platform", "e-0002", "CO", "employee", "2021-06-14"),
    ("e-0006", "Colleen Byrne", "Engineering manager", "Clinic App", "e-0002", "WA", "employee", "2021-09-07"),
    ("e-0007", "Kevin Liu", "Senior engineer", "Clinic App", "e-0006", "CA", "employee", "2021-11-01"),
    ("e-0008", "Maria Lopez", "Head of customer", "Customer", "e-0001", "TX", "employee", "2021-10-18"),
    ("e-0009", "Jake Peterson", "Product designer", "Design", "e-0012", "NY", "employee", "2022-02-14"),
    ("e-0010", "Kyle Miller", "Engineer", "Platform", "e-0002", "TX", "employee", "2022-03-21"),
    ("e-0011", "Brooke Sullivan", "Head of sales", "Sales", "e-0001", "CA", "employee", "2022-05-02"),
    ("e-0012", "Lisa Nguyen", "Head of product and design", "Design", "e-0001", "NY", "employee", "2022-06-06"),
    ("e-0013", "Josh Miller", "Engineer", "Clinic App", "e-0006", "NC", "employee", "2022-07-11"),
    ("e-0014", "Hannah Kim", "Support specialist", "Customer", "e-0008", "TX", "employee", "2022-08-01"),
    ("e-0015", "Jorge Ramirez", "Account executive", "Sales", "e-0011", "CA", "employee", "2022-09-12"),
    ("e-0016", "Priya Shah", "Marketing lead", "Marketing", "e-0001", "IL", "employee", "2022-10-03"),
    ("e-0017", "Owen Murphy", "Engineer", "Platform", "e-0002", "WA", "employee", "2022-11-07"),
    ("e-0018", "Rachel Stein", "Onboarding specialist", "Customer", "e-0008", "NY", "employee", "2023-01-09"),
    ("e-0019", "Mike Johnson", "Senior engineer", "Clinic App", "e-0006", "NC", "employee", "2023-02-06"),
    ("e-0020", "Abby Thompson", "Account executive", "Sales", "e-0011", "TX", "employee", "2023-03-13"),
    ("e-0021", "Tiago Santos", "Contract engineer", "Clinic App", "e-0006", "Portugal", "contractor", "2023-04-03"),
    ("e-0022", "Emily Kim", "Data analyst", "Operations", "e-0003", "NY", "employee", "2023-05-01"),
    ("e-0023", "Dan Walsh", "Engineer", "Platform", "e-0002", "CO", "employee", "2023-06-05"),
    ("e-0024", "Grace Taylor", "Support specialist", "Customer", "e-0008", "NC", "employee", "2023-07-10"),
    ("e-0025", "Luis Garcia", "Sales development rep", "Sales", "e-0011", "TX", "employee", "2023-08-14"),
    ("e-0026", "Natalie Brooks", "Content marketer", "Marketing", "e-0016", "CA", "employee", "2023-09-05"),
    ("e-0027", "Valentina Ruiz", "Contract QA engineer", "Clinic App", "e-0006", "Argentina", "contractor", "2023-10-02"),
    ("e-0028", "Ben Carter", "Engineer", "Clinic App", "e-0006", "WA", "employee", "2023-11-06"),
    ("e-0029", "Sarah Johnson", "Product designer", "Design", "e-0012", "IL", "employee", "2024-01-08"),
    ("e-0030", "Ethan Clark", "Solutions engineer", "Sales", "e-0011", "CO", "employee", "2024-02-05"),
    ("e-0031", "Joy Bautista", "Contract support specialist", "Customer", "e-0008", "Philippines", "contractor", "2024-03-04"),
    ("e-0032", "Caleb Dunn", "Engineer", "Platform", "e-0002", "NY", "employee", "2024-04-15"),
    ("e-0033", "Leah Martin", "Onboarding specialist", "Customer", "e-0008", "IL", "employee", "2024-05-06"),
    ("e-0034", "Arjun Patel", "Engineer", "Clinic App", "e-0006", "CA", "employee", "2024-06-03"),
    ("e-0035", "Molly Ryan", "Account executive", "Sales", "e-0011", "NY", "employee", "2024-08-05"),
    ("e-0036", "Alex Rivera", "Product manager", "Design", "e-0012", "TX", "employee", "2024-09-09"),
    ("e-0037", "Zoe Anderson", "Lifecycle marketer", "Marketing", "e-0016", "WA", "employee", "2024-11-04"),
    ("e-0038", "Isaac Brown", "Support specialist", "Customer", "e-0008", "CO", "employee", "2025-01-13"),
    ("e-0039", "Nadia Hassan", "Engineer", "Platform", "e-0002", "IL", "employee", "2025-02-03"),
    ("e-0040", "Tyler Scott", "Account executive", "Sales", "e-0011", "CA", "employee", "2025-03-10"),
    ("e-0041", "Ashley Davis", "Engineer", "Clinic App", "e-0006", "NC", "employee", "2025-05-05"),
    ("e-0042", "Connor Walsh", "Sales development rep", "Sales", "e-0011", "NY", "employee", "2025-06-09"),
    ("e-0043", "Elena Wright", "Engineer", "Platform", "e-0002", "CO", "employee", "2025-07-14"),
    ("e-0044", "Megan Cole", "Senior engineer", "Platform", "e-0002", "WA", "employee", "2025-11-03"),
    ("e-0045", "Andre Wilson", "Customer success manager", "Customer", "e-0008", "TX", "employee", "2026-01-12"),
    ("e-0046", "Jenny Park", "Product designer", "Design", "e-0012", "CA", "employee", "2026-03-02"),
    ("e-0047", "Ryan Lee", "Engineer", "Clinic App", "e-0006", "NC", "employee", "2026-05-04"),
    ("e-0048", "Keisha Moore", "Support specialist", "Customer", "e-0008", "IL", "employee", "2026-08-10"),
    ("e-0049", "Daniel Reyes", "Account executive", "Sales", "e-0011", "TX", "employee", "2026-08-24"),
    ("e-0050", "Sofia Martinez", "Engineer", "Platform", "e-0002", "CO", "employee", "2026-09-14"),
    ("e-0051", "Marcus Hill", "Marketing manager", "Marketing", "e-0016", "NY", "employee", "2026-09-21"),
]

# person: (end date, when the end date reached the desk, by whom); None for "by" means the monthly import.
LEAVERS = {
    "e-0028": ("2025-12-19", "2025-12-12T19:03:00Z", HEAD_OF_PEOPLE),
    "e-0043": ("2026-01-30", "2026-01-20T15:48:00Z", HEAD_OF_PEOPLE),
    "e-0017": ("2026-03-31", "2026-03-20T21:11:00Z", HEAD_OF_PEOPLE),
    "e-0040": ("2026-05-15", "2026-05-08T14:30:00Z", HEAD_OF_PEOPLE),
    "e-0038": ("2026-06-12", "2026-06-05T16:57:00Z", HEAD_OF_PEOPLE),
    "e-0042": ("2026-08-21", IMPORTS[1]["at"], None),
}

# person: [(effective, new title)]
TITLE_CHANGES = {
    "e-0010": [("2026-01-01", "Senior engineer")],
    "e-0019": [("2026-08-01", "Staff engineer")],
}

# plan id, role, team, planned start, band min, band max, status, approved on, person, entered at
PLAN = [
    ("H-01", "Senior engineer", "Platform", "2025-11-03", 170000, 195000, "entered", "2025-09-30", "e-0044", "2025-10-20T16:12:00Z"),
    ("H-02", "Customer success manager", "Customer", "2026-01-12", 95000, 115000, "entered", "2025-09-30", "e-0045", "2025-12-19T18:40:00Z"),
    ("H-03", "Product designer", "Design", "2026-03-02", 125000, 145000, "entered", "2025-09-30", "e-0046", "2026-02-10T17:05:00Z"),
    ("H-04", "Engineer", "Clinic App", "2026-05-04", 140000, 160000, "entered", "2025-09-30", "e-0047", "2026-04-14T15:26:00Z"),
    ("H-05", "Engineer", "Platform", "2026-09-08", 140000, 160000, "entered", "2026-04-15", "e-0050", "2026-09-16T20:31:00Z"),
    ("H-06", "Marketing manager", "Marketing", "2026-09-14", 110000, 130000, "entered", "2026-04-15", "e-0051", "2026-09-23T14:02:00Z"),
    ("H-07", "Senior account executive", "Sales", "2026-10-13", 110000, 130000, "open", "2026-04-15", None, None),
    ("H-08", "Engineer", "Clinic App", "2026-11-02", 140000, 160000, "open", "2026-04-15", None, None),
    ("H-09", "Data engineer", "Platform", "2026-07-06", 150000, 170000, "withdrawn", "2025-09-30", None, None),
]

ANNUAL = {
    "Chief executive and co-founder": 185000, "Chief technology officer and co-founder": 185000,
    "Finance lead": 150000, "Head of people and operations": 145000, "Staff engineer": 205000,
    "Engineering manager": 195000, "Senior engineer": 180000, "Engineer": 150000, "Head of customer": 150000,
    "Product designer": 135000, "Head of sales": 160000, "Head of product and design": 175000,
    "Support specialist": 72000, "Account executive": 95000, "Marketing lead": 140000,
    "Onboarding specialist": 78000, "Data analyst": 110000, "Sales development rep": 68000,
    "Content marketer": 92000, "Solutions engineer": 140000, "Product manager": 155000,
    "Lifecycle marketer": 98000, "Customer success manager": 105000, "Marketing manager": 120000,
}
STEPS = (500, 500, 500, 100, 50, 10)
MONTHLY = {"e-0021": 8200, "e-0027": 5400, "e-0031": 2600}

ROLES = {FINANCE_LEAD: "finance", HEAD_OF_PEOPLE: "people", "e-0001": "manager", "e-0002": "manager",
         "e-0006": "manager", "e-0008": "manager", "e-0011": "manager", "e-0012": "manager", "e-0016": "manager"}

VACATION_NOTES = [
    "", "", "", "Vacation", "Moving", "Long weekend", "Out Friday afternoon", "", "Family event",
    "Vacation, back on the Monday", "Taking the week between projects",
]
SICK_NOTES = ["", "", "", "Sick day", "Appointment", "Appointment, counted as a full day", "Half day"]
OTHER_NOTES = ["Conference", "Jury duty", "Volunteer day", "Moving", "Appointment", "", "Team offsite"]
OPENING_REASONS_AT_HIRE = ["rate at hire", "per offer letter", "opening rate"]
OPENING_REASONS_REVIEWED = ["opening rate", "April 2025 review", "opening rate, from the finance spreadsheet"]
LATE_OPENING = {"e-0014": "2025-10-15T16:02:11Z", "e-0030": "2025-10-22T19:40:52Z", "e-0035": "2025-11-04T15:17:30Z"}


def stamp(day: str, hour: int, minute: int) -> str:
    return f"{day}T{hour:02d}:{minute:02d}:00Z"


def shift(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def weekday_on_or_after(day: str) -> str:
    d = date.fromisoformat(day)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


def weekdays(first: str, last: str) -> int:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    return sum(1 for n in range((b - a).days + 1) if (a + timedelta(days=n)).weekday() < 5)


def round_to(amount: float, step: int) -> int:
    return int(round(amount / step) * step)


def first_week(rng: random.Random) -> str:
    day = rng.choice(["2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09", "2025-10-10"])
    return f"{day}T{rng.randint(14, 22):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}Z"


def build() -> tuple[dict, dict[str, str]]:
    rng = random.Random(4517)
    tokens = random.Random(8803)
    plan_by_person = {row[8]: row for row in PLAN if row[8]}
    import_joiners = {"e-0048", "e-0049"}

    people = []
    opening = set()
    for pid, name, title, team, manager, location, kind, start in ROSTER:
        if pid in plan_by_person:
            entered_at, entered_by = plan_by_person[pid][9], HEAD_OF_PEOPLE
        elif pid in import_joiners:
            entered_at, entered_by = IMPORTS[1]["at"], FINANCE_LEAD
        else:
            entered_at, entered_by = first_week(rng), HEAD_OF_PEOPLE if pid != HEAD_OF_PEOPLE else "e-0001"
            opening.add(pid)
        end = LEAVERS.get(pid, (None,))[0]
        final_title = TITLE_CHANGES.get(pid, [(None, title)])[-1][1]
        people.append({
            "id": pid, "name": name, "title": final_title, "team": team, "manager_id": manager,
            "location": location, "kind": kind, "start_date": start, "end_date": end,
            "token": f"{tokens.getrandbits(128):032x}",
            "entered_at": entered_at, "entered_by": entered_by, "last_import_id": None,
        })
    by_id = {p["id"]: p for p in people}

    # Pay history: opening rates when the desk started, hires, the April review, and the changes in between.
    pay = []

    def add_pay(person_id, cents, per, effective, entered_at, entered_by, reason=None):
        pay.append({"person_id": person_id, "amount_cents": cents, "currency": "USD", "per": per,
                    "effective_date": effective, "entered_by": entered_by, "entered_at": entered_at,
                    "reason": reason})

    base = {}
    for p in people:
        if p["kind"] == "contractor":
            base[p["id"]] = MONTHLY[p["id"]]
            continue
        first_title = next(r[2] for r in ROSTER if r[0] == p["id"])
        base[p["id"]] = round_to(ANNUAL[first_title] * rng.uniform(0.96, 1.04), rng.choice(STEPS))

    for p in people:
        pid, per = p["id"], "month" if p["kind"] == "contractor" else "year"
        if pid in opening:
            effective = max(p["start_date"], "2025-04-01")
            reasons = OPENING_REASONS_AT_HIRE if effective == p["start_date"] else OPENING_REASONS_REVIEWED
            entered_at = LATE_OPENING.get(pid) or max(first_week(rng), p["entered_at"])
            add_pay(pid, base[pid] * 100, per, effective, entered_at, FINANCE_LEAD, rng.choice(reasons))
        elif pid in plan_by_person:
            entered_at = p["entered_at"]
            reason = None
            if p["start_date"] < entered_at[:10]:
                reason = "from the signed offer; start date was before the offer reached the desk"
            add_pay(pid, base[pid] * 100, per, p["start_date"], entered_at, HEAD_OF_PEOPLE, reason)

    promotions = {"e-0010": ("2026-01-01", 168250, "2025-12-18T17:30:00Z")}
    for pid, (effective, amount, entered_at) in promotions.items():
        add_pay(pid, amount * 100, "year", effective, entered_at, FINANCE_LEAD)

    late_letters = {"e-0013", "e-0026", "e-0033", "e-0009"}
    for p in people:
        pid = p["id"]
        if p["kind"] != "employee" or p["start_date"] >= "2026-01-01" or (p["end_date"] and p["end_date"] < "2026-04-01"):
            continue
        if pid in promotions or rng.random() > 0.7:
            continue
        raise_to = round_to(base[pid] * rng.uniform(1.03, 1.07), rng.choice(STEPS))
        base[pid] = raise_to
        if pid in late_letters:
            entered_at = stamp(f"2026-04-{rng.randint(6, 10):02d}", rng.randint(14, 21), rng.randint(0, 59))
            reason = "April review; letter signed after the first"
        else:
            entered_at = stamp(f"2026-03-{rng.randint(23, 27):02d}", rng.randint(14, 21), rng.randint(0, 59))
            reason = None
        add_pay(pid, raise_to * 100, "year", "2026-04-01", entered_at, FINANCE_LEAD, reason)

    add_pay("e-0031", 290000, "month", "2026-03-01", "2026-04-09T15:14:00Z", FINANCE_LEAD,
            "March invoice came in at the new rate and was paid late, with April's")
    add_pay("e-0021", 860000, "month", "2026-06-01", "2026-05-28T16:45:00Z", FINANCE_LEAD)

    # Brought in by the September import: two joiners and three changes dated in August.
    import_reason = f"monthly import {IMPORTS[1]['file_name']}"
    at2 = IMPORTS[1]["at"]
    add_pay("e-0048", round_to(ANNUAL["Support specialist"] * 0.98, 500) * 100, "year", "2026-08-10", at2, FINANCE_LEAD, import_reason)
    add_pay("e-0049", round_to(ANNUAL["Account executive"] * 1.03, 500) * 100, "year", "2026-08-24", at2, FINANCE_LEAD, import_reason)
    add_pay("e-0019", round_to(base["e-0019"] * 1.1, 500) * 100, "year", "2026-08-01", at2, FINANCE_LEAD, import_reason)
    add_pay("e-0024", round_to(base["e-0024"] * 1.08, 500) * 100, "year", "2026-08-16", at2, FINANCE_LEAD, import_reason)
    add_pay("e-0027", 590000, "month", "2026-08-01", at2, FINANCE_LEAD, import_reason)

    pay.sort(key=lambda r: (r["entered_at"], r["person_id"], r["effective_date"]))
    for n, row in enumerate(pay, start=1):
        row["id"] = n

    # The two import files and the import rows.
    files = {}
    imports = []
    import_reads = []
    previous = None
    for record in IMPORTS:
        day, at = record["at"][:10], record["at"]
        rows = []
        for p in people:
            if p["entered_at"] > at:
                continue
            end, end_known_at, _ = LEAVERS.get(p["id"], (None, None, None))
            if end and end_known_at <= at and end < shift(day, -31):
                continue
            title = next(r[2] for r in ROSTER if r[0] == p["id"])
            for effective, new_title in TITLE_CHANGES.get(p["id"], []):
                if effective <= day and (record["id"] == 2 or effective < "2026-08-01"):
                    title = new_title
            known = [r for r in pay if r["person_id"] == p["id"] and r["entered_at"] <= at]
            rate = rate_on(known, day)
            rows.append({
                "employee_number": p["id"], "name": p["name"], "title": title, "team": p["team"],
                "manager": p["manager_id"] or "", "location": p["location"], "kind": p["kind"],
                "start_date": p["start_date"], "end_date": end if end and end_known_at <= at else "",
                "pay_amount": f"{rate['amount_cents'] / 100:.2f}", "pay_per": rate["per"],
                "pay_effective": rate["effective_date"],
            })
            if record["id"] == 2:
                by_id[p["id"]]["last_import_id"] = 2
            elif by_id[p["id"]]["last_import_id"] is None:
                by_id[p["id"]]["last_import_id"] = 1
        headcount = sum(1 for r in rows if not r["end_date"] or r["end_date"] >= day)
        imports.append({
            "id": record["id"], "file_name": record["file_name"], "row_count": len(rows), "headcount": headcount,
            "headcount_delta": None if previous is None else headcount - previous, "forced": 0, "reason": None,
            "run_by": FINANCE_LEAD, "at": at,
        })
        previous = headcount
        import_reads.extend({"actor_person": FINANCE_LEAD, "actor_system": None, "what": "pay_rate",
                             "person_id": r["employee_number"], "at": at} for r in rows)
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        files[record["file_name"]] = out.getvalue()

    identifiers = [
        {"person_id": p["id"], "last_four": f"{rng.randint(0, 9999):04d}", "entered_at": p["entered_at"]}
        for p in people
    ]

    # Time off: balances for 2026, requests typed in by each person's manager or the head of people.
    balances = []
    requests = []
    for p in people:
        if p["kind"] != "employee":
            continue
        if p["end_date"] is None or p["end_date"] >= "2026-01-01":
            tenure_years = 2026 - int(p["start_date"][:4])
            balances.append({"person_id": p["id"], "year": 2026, "allowance_days": 20 if tenure_years >= 3 else 15,
                             "carried_over_days": rng.choice([0, 0, 1, 2, 3, 5])})
        manager = p["manager_id"]
        booker = manager if manager and ROLES.get(manager) == "manager" else HEAD_OF_PEOPLE
        window_start = max(p["start_date"], "2025-10-01")
        window_end = min(p["end_date"] or "2026-10-30", "2026-10-30")
        if window_start >= window_end:
            continue
        span = (date.fromisoformat(window_end) - date.fromisoformat(window_start)).days
        for _ in range(rng.randint(1, 5) if span > 60 else 1):
            first = weekday_on_or_after(shift(window_start, rng.randint(0, max(span - 6, 0))))
            kind = rng.choices(["vacation", "sick", "other"], [68, 22, 10])[0]
            length = rng.choice([1, 1, 2, 3, 5, 7, 9]) if kind == "vacation" else rng.choice([1, 1, 1, 2])
            last = shift(first, length - 1)
            if last > window_end or first[:4] != last[:4]:
                continue
            if kind == "sick":
                entered = stamp(shift(first, rng.randint(0, 3)), rng.randint(14, 22), rng.randint(0, 59))
                note = rng.choice(SICK_NOTES)
            else:
                entered = stamp(shift(first, -rng.randint(4, 40)), rng.randint(14, 22), rng.randint(0, 59))
                note = rng.choice(VACATION_NOTES if kind == "vacation" else OTHER_NOTES)
            entered = max(entered, p["entered_at"])
            taken = [r for r in requests if r["person_id"] == p["id"]]
            if entered > "2026-09-30T23:59:59Z" or any(r["first_day"] <= last and r["last_day"] >= first for r in taken):
                continue
            requests.append({"person_id": p["id"], "kind": kind, "first_day": first, "last_day": last,
                             "days": weekdays(first, last), "note": note, "entered_by": booker, "entered_at": entered})
    requests.append({"person_id": "e-0029", "kind": "parental", "first_day": "2026-02-02", "last_day": "2026-04-24",
                     "days": weekdays("2026-02-02", "2026-04-24"), "note": "Twelve weeks",
                     "entered_by": "e-0012", "entered_at": "2025-12-03T17:22:00Z"})
    requests.sort(key=lambda r: (r["entered_at"], r["person_id"]))
    for n, row in enumerate(requests, start=1):
        row["id"] = n

    hiring_plan = [
        {"id": h[0], "role": h[1], "team": h[2], "planned_start": h[3], "band_min_cents": h[4] * 100,
         "band_max_cents": h[5] * 100, "status": h[6], "approved_on": h[7], "person_id": h[8], "entered_at": h[9],
         "entered_by": HEAD_OF_PEOPLE if h[8] else None}
        for h in PLAN
    ]

    # The monthly pack, run on the first of each month as monthly-report over what the desk held at that moment.
    access_log = list(import_reads)
    monthly_reports = []
    for month in REPORT_MONTHS:
        days = month_days(month)
        run_at = f"{shift(days[-1], 1)}T06:{rng.randint(0, 14):02d}:{rng.randint(0, 59):02d}Z"
        seen = []
        for p in people:
            if p["entered_at"] > run_at:
                continue
            end, end_known_at, _ = LEAVERS.get(p["id"], (None, None, None))
            known_end = end if end and end_known_at <= run_at else None
            if p["start_date"] <= days[-1] and (known_end is None or known_end >= days[0]):
                seen.append({**p, "end_date": known_end})
        rates = {p["id"]: [r for r in pay if r["person_id"] == p["id"] and r["entered_at"] <= run_at] for p in seen}
        report = cost_of_month(seen, rates, month)
        monthly_reports.append({"month": month, "generated_at": run_at, "generated_by": "monthly-report",
                                "headcount": report["headcount"], "total_cents": report["total_cents"]})
        access_log.extend({"actor_person": None, "actor_system": "monthly-report", "what": "pay_rate",
                           "person_id": p["id"], "at": run_at} for p in seen)

    human_reads = [
        (FINANCE_LEAD, "pay_rate", "e-0010", "2025-12-18T17:26:00Z"),
        (FINANCE_LEAD, "pay_rate", "e-0031", "2026-04-09T15:09:00Z"),
        (FINANCE_LEAD, "pay_rate", "e-0021", "2026-05-28T16:40:00Z"),
        (FINANCE_LEAD, "pay_rate", "e-0019", "2026-09-03T14:12:00Z"),
        (FINANCE_LEAD, "pay_rate", "e-0024", "2026-09-03T14:15:00Z"),
        (FINANCE_LEAD, "pay_rate", "e-0049", "2026-09-03T14:21:00Z"),
        (HEAD_OF_PEOPLE, "pay_rate", "e-0047", "2026-04-14T15:31:00Z"),
        (HEAD_OF_PEOPLE, "pay_rate", "e-0050", "2026-09-16T20:36:00Z"),
        (HEAD_OF_PEOPLE, "identifier", "e-0038", "2026-06-05T17:02:00Z"),
        (HEAD_OF_PEOPLE, "identifier", "e-0045", "2026-01-14T16:44:00Z"),
        (HEAD_OF_PEOPLE, "identifier", "e-0022", "2026-02-27T19:10:00Z"),
        (HEAD_OF_PEOPLE, "identifier", "e-0051", "2026-09-23T14:09:00Z"),
    ]
    for review_day in ("2026-03-18", "2026-03-19"):
        for pid in sorted(rng.sample([p["id"] for p in people if p["kind"] == "employee" and not p["end_date"]
                                      and p["start_date"] < "2026-01-01"], 6)):
            human_reads.append((FINANCE_LEAD, "pay_rate", pid, stamp(review_day, rng.randint(14, 21), rng.randint(0, 59))))
    access_log.extend({"actor_person": a, "actor_system": None, "what": w, "person_id": pid, "at": at}
                      for a, w, pid, at in human_reads)
    access_log.sort(key=lambda r: (r["at"], r["actor_system"] or "", r["actor_person"] or "", r["person_id"]))
    for n, row in enumerate(access_log, start=1):
        row["id"] = n

    seed = {
        "system_actors": [{"name": "monthly-report", "role": "finance",
                           "description": "Runs the founders' monthly cost pack on the first of each month"}],
        "people": people,
        "imports": imports,
        "roles": [{"person_id": pid, "role": role} for pid, role in sorted(ROLES.items())],
        "identifiers": identifiers,
        "pay_rates": pay,
        "time_off_balances": balances,
        "time_off_requests": requests,
        "hiring_plan": hiring_plan,
        "access_log": access_log,
        "monthly_reports": monthly_reports,
    }
    return seed, files


def render(seed: dict) -> str:
    """One row per line, keys sorted, so the file diffs well and is byte-stable."""
    parts = []
    for table in sorted(seed):
        rows = ",\n".join("  " + json.dumps(row, sort_keys=True, ensure_ascii=False) for row in seed[table])
        parts.append(f'"{table}": [\n{rows}\n]')
    return "{\n" + ",\n".join(parts) + "\n}\n"


def main() -> None:
    seed, files = build()
    (ROOT / "data" / "seed.json").write_text(render(seed), encoding="utf-8", newline="\n")
    for name, text in files.items():
        (ROOT / "data" / "imports" / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote data/seed.json and {len(files)} import files")


if __name__ == "__main__":
    main()
