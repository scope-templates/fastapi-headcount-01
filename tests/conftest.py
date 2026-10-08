import json

import pytest
from fastapi.testclient import TestClient

from headcount import actors, db
from headcount.app import create_app

FINANCE = "e-0003"
PEOPLE = "e-0004"
MANAGER = "e-0006"  # Clinic App
REPORT = "e-0013"  # reports to MANAGER
OTHER_TEAM = "e-0014"  # Customer
STAFF = "e-0007"
SMALL_TEAM_MANAGER = "e-0016"  # Marketing
LEFT = "e-0042"  # end date 2026-08-21
TOKENS = {p["id"]: p["token"] for p in json.loads(db.SEED_FILE.read_text(encoding="utf-8"))["people"]}


@pytest.fixture
def db_file(tmp_path):
    return tmp_path / "desk.db"


@pytest.fixture
def conn(db_file):
    connection = db.open_store(db_file)
    yield connection
    connection.close()


@pytest.fixture
def client(db_file):
    return TestClient(create_app(db_file))


def as_(person_id: str) -> dict:
    return {"Authorization": f"Bearer {TOKENS[person_id]}"}


@pytest.fixture
def finance(conn):
    return actors.person(conn, FINANCE)


@pytest.fixture
def people_lead(conn):
    return actors.person(conn, PEOPLE)
