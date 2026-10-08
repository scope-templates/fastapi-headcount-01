# Wexvale headcount desk

Wexvale sells appointment scheduling to veterinary clinics. We are forty-five people: employees in seven states and three contractors abroad. This desk is the small service Ruth (finance lead) and Dana (head of people) use to answer what the founders ask every month: who is on which team, what each team costs, who is out next week, and what a planned hire adds to the budget. Managers use it to book time off for their reports. People and pay arrive through the monthly import of Ruth's spreadsheet, where each person is entered from the signed offer; managers type time off into the form.

Ruth's data rule, in her words:

> We keep only what the monthly reports need. Never a bank detail, never a dependant, and only the last four characters of any identifier.

## What is in it

FastAPI with Python's built-in `sqlite3`, a JSON API, a few report pages rendered with Jinja2, and pytest.

| Table | What it holds | What it refuses |
| --- | --- | --- |
| `people` | name, title, team, manager, state or country, employee or contractor, start and end dates, a sign-in token, who entered the row and when, the last import that touched it; status (starting, active, left) is worked out from the dates on each read | an end date before the start date; a token that is not 32 characters or is already someone's |
| `pay_rates` | one row per rate: amount in cents, USD, per year or per month, effective date, who entered it, when, and why | any edit, delete or replacement; a row dated before the day it is entered without a reason; a rate entered by anything but a person; an amount of zero or less; a period other than year or month |
| `identifiers` | the last four characters of each person's identifier | anything other than four characters |
| `time_off_requests`, `time_off_balances` | requests by day range and kind; each 2026 allowance and carry-over | a last day before the first; a request that crosses the new year; any day after the person's end date; a note over 60 characters; a kind other than vacation, sick, parental or other |
| `hiring_plan` | approved roles with team, planned start, pay band and status; the person once entered | entering a row that is already entered or withdrawn; a row marked entered without its person, or a person on a row not marked entered; a band whose top is below its bottom |
| `imports` | every monthly import: file name, row count, headcount, change from the last import, forced or not, reason, who ran it, when | any edit, delete or replacement; a forced import without a reason |
| `access_log` | every read of a pay rate or an identifier: actor, what was read, which person, when | any edit, delete or replacement; an entry without exactly one actor that is a person or a system actor; an entry about someone not on file. These hold even from a bare sqlite3 connection |
| `system_actors` | named jobs that read pay; `monthly-report` (role finance) is the only one | |
| `monthly_reports` | the saved monthly pack: month, when it ran, headcount and total | |

Operations:

| Operation | Route or command | Refuses |
| --- | --- | --- |
| Monthly import | `python -m headcount.import <file.csv> --by <person id>` | a caller without the finance role; a headcount that differs from the last import by more than a fifth unless `--force` with `--reason`; a run by a system actor rather than a person; a row whose end date is before its start date; a manager who is neither on file nor in the file; a kind other than employee or contractor; a blank required field, a repeated employee number, or a bad date or amount |
| Monthly cost pack | `python -m headcount.monthly_report <YYYY-MM>` | a month that is not `YYYY-MM`; saving a pack under anything but a system actor |
| Cost by team and person | `GET /reports/cost/{month}`, `/pages/cost/{month}` | callers outside finance and people |
| Budget with planned hires (each open planned hire priced at the middle of its band from its planned start) | `GET /reports/budget/{month}` | callers outside finance and people |
| Headcount | `GET /reports/headcount?day=`, `/pages/headcount` | staff |
| Who is out | `GET /time-off/out`, `/pages/out` (next week unless days are given) | |
| Book time off | `POST /time-off`, form at `/time-off/new` | anyone but the person's manager or the head of people |
| Pay rates | `GET` and `POST /people/{id}/pay` | callers outside finance and people; a past date without a reason |
| Identifier | `GET` and `PUT /people/{id}/identifier` | anyone but the people role; fewer than four letters or digits |
| End date | `POST /people/{id}/end-date` | anyone but the people role |
| Enter a planned hire | `POST /hiring-plan/{id}/enter` | anyone but the people role; a past start date without a pay reason; a manager not on file; a kind other than employee or contractor |
| Imports, access log, saved packs | `GET /imports`, `/access-log`, `/reports/saved` | callers outside finance and people |

A refused API call answers with a `reason` code and a `detail` line; a refused command prints `refused [code]: ...` and exits 1.

The monthly cost is worked out day by day: each day a person is employed is costed at the rate in effect on that day, a yearly rate over the days in the year and a monthly rate over the days in the month.

## Roles

Each person has a token. API calls send it as `Authorization: Bearer <token>`; report pages read the `token` cookie that `/sign-in` sets once the token checks out. A request with no token, or one that matches nobody, gets 401. The role comes from the `roles` table, and anyone without a row there is staff. A person can act through their last day and not after: from the day after their end date they get 403, whatever their role. The two commands run on the desk's own machine and take a person id with `--by` instead.

| Role | Sees | Does |
| --- | --- | --- |
| finance | everyone; pay rates; cost, budget, hiring plan, imports, access log | runs the monthly import; adds pay rates |
| people | everyone; pay rates; identifiers; cost, budget, hiring plan, imports, access log | enters planned hires; records end dates and identifiers; adds pay rates; books time off for anyone |
| manager | their own record, and headcount and time off for their direct reports; never a pay figure, not even a team's cost total, and not the hiring plan | books time off for their direct reports |
| staff | their own record and time off | nothing |

Every read of a pay rate or an identifier writes an access-log entry naming the actor. The cost report writes one entry per person it costs, and the monthly import one per row with pay, under whoever runs it. The monthly pack runs as the `monthly-report` system actor.

A time-off note is a short reason, nothing more: 60 characters at most.

## Running locally

Python 3.12 or later.

```
python -m venv .venv
.venv/Scripts/activate        # or: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn --factory headcount.app:create_app --port 8000
```

The store is `headcount.db` at the repo root, or the path in `HEADCOUNT_DB`. On first start, when it has no people, it is loaded from `data/seed.json`. Each seeded person's token is on their row in `data/seed.json`. Ruth's is `806774292ff72e3dd407cb037005ed51`:

```
curl -H "Authorization: Bearer 806774292ff72e3dd407cb037005ed51" localhost:8000/reports/cost/2026-08
```

Or open `localhost:8000/sign-in` and paste the token.

The import and the monthly pack:

```
python -m headcount.import data/imports/people-2026-09.csv --by e-0003
python -m headcount.monthly_report 2026-09
```

## Tests

```
python -m pytest
```

## The data

`data/seed.json` covers the twelve months to September 2026 and is written by `python scripts/make_seed.py` (a fixed random seed; the same bytes every run). The script also writes the two import files in `data/imports/`.

- 51 people since October 2025: 45 current, six who left. Teams: Leadership, Platform, Clinic App, Design, Customer, Sales, Marketing, Operations.
- Pay history from the opening rates entered in the desk's first weeks, October and early November 2025: the April review, a promotion in January and another that came in with the September import, contractor rate changes, and the rates that came in with each import.
- Two imports on record: `people-2026-08.csv` on 2026-08-04 and `people-2026-09.csv` on 2026-09-02, both run by Ruth.
- The hiring plan has nine rows: six entered, two open, one withdrawn.
- Time off across the year, typed in by managers and by Dana, with 2026 balances for every employee on staff during 2026. Notes are a short reason or blank.
- The monthly pack for each month from October 2025 to September 2026, each saved on the first of the next month, and the access-log entries written by those runs, by both imports, and by people reading pay and identifiers.

Useful ids: `e-0003` Ruth (finance), `e-0004` Dana (people), `e-0006` Colleen (manager, Clinic App), `e-0007` Kevin (staff).
