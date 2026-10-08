import sqlite3

import pytest

from headcount import actors, db, pay
from tests.conftest import FINANCE, MANAGER, PEOPLE, REPORT, as_

LATER = {"amount_cents": 16500000, "per": "year", "effective_date": "2099-01-01"}


def rates(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM pay_rates WHERE person_id = ? ORDER BY id", (REPORT,))]


def test_a_change_is_a_new_row_and_earlier_rows_stay(client, conn):
    before = rates(conn)
    assert client.post(f"/people/{REPORT}/pay", headers=as_(FINANCE), json=LATER).status_code == 201
    after = rates(conn)
    assert after[:-1] == before
    assert (after[-1]["amount_cents"], after[-1]["effective_date"], after[-1]["entered_by"]) == (
        16500000, "2099-01-01", FINANCE)


def test_a_rate_dated_in_the_past_needs_a_reason(client):
    body = {**LATER, "effective_date": "2026-01-01"}
    assert client.post(f"/people/{REPORT}/pay", headers=as_(FINANCE), json=body).status_code == 422
    body["reason"] = "January adjustment agreed in December, letter signed late"
    assert client.post(f"/people/{REPORT}/pay", headers=as_(PEOPLE), json=body).status_code == 201


def test_rows_are_never_edited_or_deleted(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE pay_rates SET amount_cents = 1 WHERE person_id = ?", (REPORT,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM pay_rates WHERE person_id = ?", (REPORT,))


def test_the_store_refuses_a_past_dated_row_without_a_reason(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO pay_rates (person_id, amount_cents, currency, per, effective_date, entered_by, entered_at)"
            " VALUES (?, 100, 'USD', 'year', '2026-01-01', ?, '2026-09-30T12:00:00Z')",
            (REPORT, FINANCE),
        )


def test_managers_cannot_add_rates(client):
    assert client.post(f"/people/{REPORT}/pay", headers=as_(MANAGER), json=LATER).status_code == 403


def test_rates_are_entered_by_a_person_with_a_positive_amount_and_a_known_period(conn):
    job = actors.system(conn, "monthly-report")
    with pytest.raises(db.Refused, match="entered by a person"):
        pay.add_rate(conn, job, REPORT, 100, "year", "2099-01-01")
    finance = actors.person(conn, FINANCE)
    for amount, per, code in ((0, "year", "bad_amount"), (100, "week", "bad_period")):
        with pytest.raises(db.Refused) as refused:
            pay.add_rate(conn, finance, REPORT, amount, per, "2099-01-01")
        assert refused.value.code == code
