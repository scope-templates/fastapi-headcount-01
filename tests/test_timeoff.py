import sqlite3

import pytest

from tests.conftest import FINANCE, LEFT, MANAGER, OTHER_TEAM, PEOPLE, REPORT, STAFF, as_


def booking(person_id=REPORT, first="2099-03-09", last="2099-03-13", kind="vacation"):
    return {"person_id": person_id, "kind": kind, "first_day": first, "last_day": last, "note": "Spring break"}


def test_manager_books_time_off_for_a_report(client, conn):
    response = client.post("/time-off", headers=as_(MANAGER), json=booking(last="2099-03-16"))
    assert response.status_code == 201
    assert response.json()["days"] == 6
    row = conn.execute("SELECT entered_by, note FROM time_off_requests ORDER BY id DESC LIMIT 1").fetchone()
    assert tuple(row) == (MANAGER, "Spring break")


def test_booking_is_limited_to_own_reports_and_the_head_of_people(client):
    assert client.post("/time-off", headers=as_(MANAGER), json=booking(OTHER_TEAM)).status_code == 403
    assert client.post("/time-off", headers=as_(STAFF), json=booking(STAFF)).status_code == 403
    assert client.post("/time-off", headers=as_(FINANCE), json=booking()).status_code == 403
    assert client.post("/time-off", headers=as_(PEOPLE), json=booking(OTHER_TEAM)).status_code == 201


def test_bad_bookings_are_refused(client):
    assert client.post("/time-off", headers=as_(MANAGER), json=booking(last="2099-03-01")).status_code == 422
    assert client.post("/time-off", headers=as_(MANAGER), json=booking(kind="sabbatical")).status_code == 422
    crossing = booking(first="2099-12-28", last="2100-01-02")
    assert client.post("/time-off", headers=as_(MANAGER), json=crossing).status_code == 422


def test_balance_counts_booked_vacation_days(client, conn):
    before = client.get(f"/people/{REPORT}/time-off/balance?year=2099", headers=as_(MANAGER)).json()
    client.post("/time-off", headers=as_(MANAGER), json=booking())
    after = client.get(f"/people/{REPORT}/time-off/balance?year=2099", headers=as_(MANAGER)).json()
    assert after["vacation_days_booked"] == before["vacation_days_booked"] + 5
    assert after["remaining_days"] == before["remaining_days"] - 5


def test_the_booking_form_lists_only_the_managers_reports(client, conn):
    page = client.get("/time-off/new", headers=as_(MANAGER)).text
    assert 'value="e-0013"' in page and 'value="e-0014"' not in page
    assert client.get("/time-off/new", headers=as_(STAFF)).status_code == 403


def test_nothing_is_booked_past_an_end_date(client, conn):
    response = client.post("/time-off", headers=as_(PEOPLE), json=booking(LEFT, "2026-08-20", "2026-08-24"))
    assert (response.status_code, response.json()["reason"]) == (422, "after_end_date")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO time_off_requests (person_id, kind, first_day, last_day, days, entered_by, entered_at)"
            " VALUES (?, 'vacation', '2026-08-20', '2026-08-24', 3, ?, '2026-08-01T00:00:00Z')",
            (LEFT, PEOPLE),
        )


def test_a_note_is_a_short_reason(client):
    long_note = {**booking(), "note": "x" * 61}
    response = client.post("/time-off", headers=as_(MANAGER), json=long_note)
    assert (response.status_code, response.json()["reason"]) == (422, "note_too_long")


def test_requests_and_balances_are_visible_only_to_whoever_may_see_the_person(client):
    for caller, person_id in ((STAFF, REPORT), (MANAGER, OTHER_TEAM)):
        for path in (f"/people/{person_id}/time-off", f"/people/{person_id}/time-off/balance"):
            assert client.get(path, headers=as_(caller)).status_code == 403
    assert client.get(f"/people/{REPORT}/time-off", headers=as_(MANAGER)).status_code == 200
