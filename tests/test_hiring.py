import pytest

from headcount import actors, hiring
from tests.conftest import FINANCE, PEOPLE, as_

OFFER = {
    "name": "Jordan Hayes",
    "title": "Senior account executive",
    "manager_id": "e-0011",
    "location": "CO",
    "kind": "employee",
    "start_date": "2099-10-13",
    "amount_cents": 12000000,
    "per": "year",
    "identifier": "532-71-3382",
}


def test_a_planned_hire_becomes_a_person_when_entered(client, conn):
    assert conn.execute("SELECT person_id FROM hiring_plan WHERE id = 'H-07'").fetchone()[0] is None
    response = client.post("/hiring-plan/H-07/enter", headers=as_(PEOPLE), json=OFFER)
    assert response.status_code == 201
    person_id = response.json()["person_id"]
    person = conn.execute("SELECT team, entered_by FROM people WHERE id = ?", (person_id,)).fetchone()
    assert tuple(person) == ("Sales", PEOPLE)
    own = client.get(f"/people/{person_id}", headers={"Authorization": f"Bearer {response.json()['token']}"})
    assert own.json()["status"] == "starting"
    assert conn.execute("SELECT last_four FROM identifiers WHERE person_id = ?", (person_id,)).fetchone()[0] == "3382"
    rate = conn.execute("SELECT amount_cents, effective_date FROM pay_rates WHERE person_id = ?", (person_id,)).fetchone()
    assert tuple(rate) == (12000000, "2099-10-13")
    plan = conn.execute("SELECT status, person_id FROM hiring_plan WHERE id = 'H-07'").fetchone()
    assert tuple(plan) == ("entered", person_id)


def test_only_the_head_of_people_enters_hires(client):
    assert client.post("/hiring-plan/H-07/enter", headers=as_(FINANCE), json=OFFER).status_code == 403


def test_a_start_date_already_passed_needs_a_pay_reason_and_writes_nothing_without_one(client, conn):
    people = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    late = {**OFFER, "start_date": "2026-09-28"}
    assert client.post("/hiring-plan/H-07/enter", headers=as_(PEOPLE), json=late).status_code == 422
    assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == people
    late["pay_reason"] = "from the signed offer; start date was before the offer reached the desk"
    assert client.post("/hiring-plan/H-07/enter", headers=as_(PEOPLE), json=late).status_code == 201


def test_rows_already_entered_or_withdrawn_are_refused(client):
    for plan_id in ("H-05", "H-09"):
        assert client.post(f"/hiring-plan/{plan_id}/enter", headers=as_(PEOPLE), json=OFFER).status_code == 422
    assert client.post("/hiring-plan/H-99/enter", headers=as_(PEOPLE), json=OFFER).status_code == 404


def test_a_finance_actor_cannot_enter_a_hire_directly(conn, finance):
    with pytest.raises(actors.Forbidden):
        hiring.enter(conn, finance, "H-07", **{**OFFER, "start_date": "2099-10-13"})


@pytest.mark.parametrize("change, reason", [({"manager_id": "e-0999"}, "no_such_manager"), ({"kind": "intern"}, "bad_kind")])
def test_a_hire_needs_a_manager_on_file_and_a_known_kind(client, change, reason):
    response = client.post("/hiring-plan/H-07/enter", headers=as_(PEOPLE), json={**OFFER, **change})
    assert (response.status_code, response.json()["reason"]) == (422, reason)
