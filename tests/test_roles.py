from tests.conftest import (
    FINANCE, LEFT, MANAGER, OTHER_TEAM, PEOPLE, REPORT, SMALL_TEAM_MANAGER, STAFF, TOKENS, as_,
)


def test_finance_and_people_read_pay_rates(client):
    for reader in (FINANCE, PEOPLE):
        response = client.get(f"/people/{REPORT}/pay", headers=as_(reader))
        assert response.status_code == 200
        assert response.json()[0]["currency"] == "USD"


def test_manager_and_staff_never_read_pay_rates(client):
    assert client.get(f"/people/{REPORT}/pay", headers=as_(MANAGER)).status_code == 403
    assert client.get(f"/people/{STAFF}/pay", headers=as_(STAFF)).status_code == 403


def test_manager_sees_only_self_and_direct_reports(client, conn):
    listed = {p["id"] for p in client.get("/people", headers=as_(MANAGER)).json()}
    reports = {r["id"] for r in conn.execute("SELECT id FROM people WHERE manager_id = ? AND (end_date IS NULL OR end_date >= date('now'))", (MANAGER,))}
    assert listed == reports | {MANAGER}
    assert client.get(f"/people/{OTHER_TEAM}", headers=as_(MANAGER)).status_code == 403


def test_person_record_carries_no_pay_figure(client):
    record = client.get(f"/people/{REPORT}", headers=as_(MANAGER)).json()
    assert not any("amount" in key or "cents" in key for key in record)


def test_manager_gets_no_cost_figures_even_for_a_team_under_four(client, conn):
    small = conn.execute(
        "SELECT COUNT(*) FROM people WHERE manager_id = ? AND end_date IS NULL", (SMALL_TEAM_MANAGER,)
    ).fetchone()[0]
    assert small < 4
    for path in ("/reports/cost/2026-08", "/reports/budget/2026-10", "/hiring-plan", "/reports/saved", "/pages/cost/2026-08"):
        assert client.get(path, headers=as_(SMALL_TEAM_MANAGER)).status_code == 403


def test_manager_headcount_covers_their_reports(client, conn):
    report = client.get("/reports/headcount?day=2026-09-30", headers=as_(MANAGER)).json()
    reports = conn.execute(
        "SELECT COUNT(*) FROM people WHERE manager_id = ? AND start_date <= '2026-09-30'"
        " AND (end_date IS NULL OR end_date >= '2026-09-30')", (MANAGER,)
    ).fetchone()[0]
    assert report["headcount"] == reports


def test_staff_see_their_own_record_only(client):
    assert [p["id"] for p in client.get("/people", headers=as_(STAFF)).json()] == [STAFF]
    assert client.get(f"/people/{STAFF}", headers=as_(STAFF)).status_code == 200
    assert client.get(f"/people/{REPORT}", headers=as_(STAFF)).status_code == 403
    assert client.get("/reports/headcount", headers=as_(STAFF)).status_code == 403


def test_callers_prove_who_they_are_with_their_token(client):
    missing = client.get("/people")
    assert (missing.status_code, missing.json()["reason"]) == (401, "token_missing")
    wrong = client.get("/people", headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"})
    assert (wrong.status_code, wrong.json()["reason"]) == (401, "token_unknown")
    asserted = client.get("/people", headers={"Authorization": f"Person {FINANCE}"})
    assert (asserted.status_code, asserted.json()["reason"]) == (401, "bad_scheme")


def test_a_person_whose_end_date_has_passed_is_refused(client, conn):
    left = client.get("/people", headers=as_(LEFT))
    assert (left.status_code, left.json()["reason"]) == (403, "person_left")
    with conn:
        conn.execute("UPDATE people SET end_date = '2026-01-30' WHERE id = ?", (STAFF,))
    assert client.get("/people", headers=as_(STAFF)).json()["reason"] == "person_left"


def test_sign_in_takes_a_token_and_sets_the_cookie(client):
    assert client.post("/sign-in", json={"token": "0" * 32}).status_code == 401
    response = client.post("/sign-in", json={"token": TOKENS[FINANCE]})
    assert response.json() == {"person_id": FINANCE, "role": "finance"}
    assert response.headers["set-cookie"].startswith(f"token={TOKENS[FINANCE]};")
    assert client.get("/pages/headcount").status_code == 200


def test_only_the_people_role_records_end_dates(client):
    for caller in (FINANCE, MANAGER, STAFF):
        response = client.post(f"/people/{REPORT}/end-date", headers=as_(caller), json={"end_date": "2099-01-31"})
        assert response.status_code == 403
    response = client.post(f"/people/{REPORT}/end-date", headers=as_(PEOPLE), json={"end_date": "2099-01-31"})
    assert response.json()["end_date"] == "2099-01-31"


def test_an_end_date_before_the_start_date_is_refused_with_its_reason(client):
    response = client.post(f"/people/{REPORT}/end-date", headers=as_(PEOPLE), json={"end_date": "2020-01-31"})
    assert (response.status_code, response.json()["reason"]) == (422, "end_before_start")


def test_imports_and_access_log_are_for_finance_and_people(client):
    for path in ("/imports", "/access-log"):
        for caller in (MANAGER, STAFF):
            assert client.get(path, headers=as_(caller)).status_code == 403
        for caller in (FINANCE, PEOPLE):
            assert client.get(path, headers=as_(caller)).status_code == 200
