import os
import sqlite3
import subprocess
import sys

import pytest

from headcount import actors, db, monthly_report, reports
from tests.conftest import FINANCE, REPORT, as_


def test_reading_pay_rates_logs_the_reader(client, conn):
    client.get(f"/people/{REPORT}/pay", headers=as_(FINANCE))
    entry = conn.execute("SELECT * FROM access_log ORDER BY id DESC LIMIT 1").fetchone()
    assert (entry["actor_person"], entry["actor_system"], entry["what"], entry["person_id"]) == (
        FINANCE, None, "pay_rate", REPORT)


def test_cost_report_logs_one_entry_per_person_costed(client, conn):
    before = conn.execute("SELECT MAX(id) FROM access_log").fetchone()[0]
    report = client.get("/reports/cost/2026-08", headers=as_(FINANCE)).json()
    logged = conn.execute("SELECT person_id, actor_person FROM access_log WHERE id > ?", (before,)).fetchall()
    assert sorted(r["person_id"] for r in logged) == sorted(p["id"] for p in report["people"])
    assert {r["actor_person"] for r in logged} == {FINANCE}


def test_monthly_report_command_logs_under_its_system_actor(db_file, conn, monkeypatch, capsys):
    monkeypatch.setenv("HEADCOUNT_DB", str(db_file))
    before = conn.execute("SELECT MAX(id) FROM access_log").fetchone()[0]
    assert monthly_report.main(["2026-09"]) == 0
    logged = conn.execute("SELECT actor_person, actor_system FROM access_log WHERE id > ?", (before,)).fetchall()
    assert logged and {tuple(r) for r in logged} == {(None, "monthly-report")}
    saved = conn.execute("SELECT generated_by FROM monthly_reports WHERE month = '2026-09'").fetchall()
    assert [r[0] for r in saved] == ["monthly-report", "monthly-report"]
    assert "Cost for 2026-09" in capsys.readouterr().out


def test_a_bad_month_is_one_refusal_line(db_file):
    env = {**os.environ, "HEADCOUNT_DB": str(db_file)}
    done = subprocess.run([sys.executable, "-m", "headcount.monthly_report", "2026-13"],
                          cwd=db.ROOT, env=env, capture_output=True, text=True)
    assert done.returncode == 1
    assert done.stderr.splitlines() == ["refused [bad_month]: '2026-13' is not a YYYY-MM month"]


def test_saved_monthly_report_is_run_by_a_system_actor(conn, finance):
    with pytest.raises(actors.Forbidden):
        reports.save_monthly_report(conn, finance, "2026-09")


def test_unknown_system_actor_is_refused(conn):
    with pytest.raises(actors.Unauthenticated):
        actors.system(conn, "nightly-export")


@pytest.mark.parametrize(
    "person, system",
    [(None, None), (FINANCE, "monthly-report"), ("e-9999", None), (None, "nightly-export")],
)
def test_every_entry_names_exactly_one_known_actor(conn, person, system):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO access_log (actor_person, actor_system, what, person_id, at)"
            " VALUES (?, ?, 'pay_rate', ?, '2026-09-30T00:00:00Z')",
            (person, system, REPORT),
        )


def test_the_log_is_append_only(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE access_log SET at = '2020-01-01T00:00:00Z' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM access_log WHERE id = 1")


def test_finance_reads_the_log(client):
    entries = client.get(f"/access-log?person_id={REPORT}", headers=as_(FINANCE)).json()
    assert entries and all(e["person_id"] == REPORT for e in entries)


def test_a_raw_connection_cannot_write_an_entry_without_a_known_actor(db_file, conn):
    raw = sqlite3.connect(db_file)  # no PRAGMA foreign_keys on this one
    for person, system in [(None, None), ("", None), ("", ""), ("e-9999", None), (None, "nightly-export")]:
        with pytest.raises(sqlite3.IntegrityError):
            raw.execute(
                "INSERT INTO access_log (actor_person, actor_system, what, person_id, at)"
                " VALUES (?, ?, 'pay_rate', ?, '2026-09-30T00:00:00Z')",
                (person, system, REPORT),
            )
    raw.close()


def test_every_connection_enforces_references(db_file, client):
    assert db.connect(db_file).execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.open_store(db_file).execute("PRAGMA foreign_keys").fetchone()[0] == 1
