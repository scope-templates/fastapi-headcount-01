from fractions import Fraction

from headcount.reports import cost_of_month
from tests.conftest import FINANCE, MANAGER, as_

PERSON = {"id": "e-1", "name": "Test Person", "team": "Platform", "start_date": "2024-01-01", "end_date": None}


def rate(rate_id, cents, effective, per="year"):
    return {"id": rate_id, "amount_cents": cents, "per": per, "effective_date": effective}


def cents(amount: Fraction) -> int:
    return int(amount + Fraction(1, 2))


def test_each_day_is_costed_at_the_rate_in_effect_that_day():
    rates = {"e-1": [rate(1, 12_000_000, "2025-01-01"), rate(2, 24_000_000, "2026-06-16")]}
    report = cost_of_month([PERSON], rates, "2026-06")
    assert report["total_cents"] == cents(Fraction(15 * 12_000_000, 365) + Fraction(15 * 24_000_000, 365))
    assert report["total_cents"] != cents(Fraction(30 * 24_000_000, 365))


def test_only_days_employed_are_costed():
    joiner = {**PERSON, "start_date": "2026-06-21"}
    report = cost_of_month([joiner], {"e-1": [rate(1, 3_000_000, "2026-06-21", per="month")]}, "2026-06")
    assert report["total_cents"] == 1_000_000
    assert report["headcount"] == 1


def test_a_monthly_rate_costs_the_full_amount_for_a_full_month():
    report = cost_of_month([PERSON], {"e-1": [rate(1, 590_000, "2026-01-01", per="month")]}, "2026-02")
    assert report["total_cents"] == 590_000


def test_team_totals_add_up_to_the_month(client):
    report = client.get("/reports/cost/2026-08", headers=as_(FINANCE)).json()
    assert sum(t["cost_cents"] for t in report["teams"]) == report["total_cents"]
    assert sum(p["cost_cents"] for p in report["people"]) == report["total_cents"]


def test_budget_adds_open_planned_hires_from_their_planned_start(client):
    budget = client.get("/reports/budget/2026-10", headers=as_(FINANCE)).json()
    planned = {p["id"]: p for p in budget["planned"]}
    assert set(planned) == {"H-07"}
    yearly = planned["H-07"]["midpoint_cents_per_year"]
    assert planned["H-07"]["adds_cents"] == cents(Fraction(yearly * 19, 365))
    assert budget["total_cents"] == budget["current_cents"] + planned["H-07"]["adds_cents"]


def test_out_lists_overlapping_time_off_the_caller_may_see(client, conn):
    first, last = "2026-07-06", "2026-07-10"
    everyone = client.get(f"/time-off/out?first_day={first}&last_day={last}", headers=as_(FINANCE)).json()
    expected = conn.execute(
        "SELECT COUNT(*) FROM time_off_requests WHERE first_day <= ? AND last_day >= ?", (last, first)
    ).fetchone()[0]
    assert len(everyone) == expected > 0
    mine = client.get(f"/time-off/out?first_day={first}&last_day={last}", headers=as_(MANAGER)).json()
    team = {r[0] for r in conn.execute("SELECT id FROM people WHERE manager_id = ? OR id = ?", (MANAGER, MANAGER))}
    assert all(r["person_id"] in team for r in mine)


def test_report_pages_render(client):
    for path in ("/pages/headcount", "/pages/cost/2026-08", "/pages/out?first_day=2026-07-06"):
        response = client.get(path, headers=as_(FINANCE))
        assert response.status_code == 200
        assert "Last import: people-2026-09.csv" in response.text


def test_a_malformed_month_is_refused(client):
    assert client.get("/reports/cost/2026-13", headers=as_(FINANCE)).status_code == 422
