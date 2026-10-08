import sqlite3

import pytest

from tests.conftest import FINANCE, MANAGER, PEOPLE, REPORT, as_


def test_only_the_last_four_characters_are_stored(client, conn):
    response = client.put(f"/people/{REPORT}/identifier", headers=as_(PEOPLE), json={"value": "417-55-0473"})
    assert response.json()["last_four"] == "0473"
    stored = conn.execute("SELECT last_four FROM identifiers WHERE person_id = ?", (REPORT,)).fetchone()[0]
    assert stored == "0473"


def test_the_store_refuses_anything_longer_than_four(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE identifiers SET last_four = '550473' WHERE person_id = ?", (REPORT,))


def test_only_people_role_reads_identifiers(client):
    assert client.get(f"/people/{REPORT}/identifier", headers=as_(PEOPLE)).status_code == 200
    for reader in (FINANCE, MANAGER, REPORT):
        assert client.get(f"/people/{REPORT}/identifier", headers=as_(reader)).status_code == 403
    assert client.put(f"/people/{REPORT}/identifier", headers=as_(FINANCE), json={"value": "1234"}).status_code == 403


def test_reading_an_identifier_is_logged_with_the_reader(client, conn):
    before = conn.execute("SELECT COUNT(*) FROM access_log").fetchone()[0]
    client.get(f"/people/{REPORT}/identifier", headers=as_(PEOPLE))
    row = conn.execute("SELECT * FROM access_log ORDER BY id DESC LIMIT 1").fetchone()
    assert conn.execute("SELECT COUNT(*) FROM access_log").fetchone()[0] == before + 1
    assert (row["actor_person"], row["what"], row["person_id"]) == (PEOPLE, "identifier", REPORT)


def test_short_identifiers_are_refused(client):
    response = client.put(f"/people/{REPORT}/identifier", headers=as_(PEOPLE), json={"value": "4-7"})
    assert response.status_code == 422
