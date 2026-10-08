import csv
import os
import sqlite3
import subprocess
import sys

import pytest

from headcount import actors, db, importer
from headcount.db import ROOT
from tests.conftest import MANAGER, PEOPLE

SEPTEMBER = ROOT / "data" / "imports" / "people-2026-09.csv"


def read(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def short_file(tmp_path):
    """The September file with ten current people left out."""
    return write(tmp_path / "short.csv", [r for r in read(SEPTEMBER) if not r["end_date"]][:-10])


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_loading_the_september_file_again_changes_no_pay_and_records_the_import(conn, finance):
    pay_rows, people_rows = count(conn, "pay_rates"), count(conn, "people")
    result = importer.run_import(conn, finance, SEPTEMBER)
    assert (result["headcount_delta"], result["people_added"], result["pay_rows_added"]) == (0, 0, 0)
    assert (count(conn, "pay_rates"), count(conn, "people")) == (pay_rows, people_rows)
    latest = conn.execute("SELECT * FROM imports ORDER BY id DESC LIMIT 1").fetchone()
    assert (latest["file_name"], latest["row_count"], latest["run_by"], latest["forced"]) == (
        "people-2026-09.csv", 44, finance.person_id, 0)


def test_a_swing_of_more_than_a_fifth_is_refused(conn, finance, tmp_path):
    short = short_file(tmp_path)
    imports = count(conn, "imports")
    with pytest.raises(db.Refused, match="more than a fifth|--force"):
        importer.run_import(conn, finance, short)
    assert count(conn, "imports") == imports


def test_a_forced_import_needs_a_reason_and_records_it(conn, finance, tmp_path):
    short = short_file(tmp_path)
    with pytest.raises(db.Refused, match="reason"):
        importer.run_import(conn, finance, short, forced=True)
    result = importer.run_import(conn, finance, short, forced=True, reason="Spreadsheet split by team this month")
    row = conn.execute("SELECT forced, reason, headcount_delta FROM imports WHERE id = ?", (result["import_id"],)).fetchone()
    assert tuple(row) == (1, "Spreadsheet split by team this month", -10)


def test_a_pay_change_in_the_file_becomes_a_new_dated_row(conn, finance, tmp_path):
    rows = read(SEPTEMBER)
    target = next(r for r in rows if r["employee_number"] == "e-0013")
    target.update(pay_amount="171000.00", pay_effective="2026-09-15")
    before = count(conn, "pay_rates")
    importer.run_import(conn, finance, write(tmp_path / "people-2026-10.csv", rows))
    added = conn.execute("SELECT * FROM pay_rates ORDER BY id DESC LIMIT 1").fetchone()
    assert count(conn, "pay_rates") == before + 1
    assert (added["person_id"], added["amount_cents"], added["effective_date"], added["reason"]) == (
        "e-0013", 17100000, "2026-09-15", "monthly import people-2026-10.csv")


def test_only_finance_runs_the_import(conn):
    for person_id in (PEOPLE, MANAGER):
        with pytest.raises(actors.Forbidden):
            importer.run_import(conn, actors.person(conn, person_id), SEPTEMBER)


def test_import_records_are_append_only(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE imports SET row_count = 0")


def test_the_import_command(db_file):
    env = {**os.environ, "HEADCOUNT_DB": str(db_file)}
    done = subprocess.run(
        [sys.executable, "-m", "headcount.import", str(SEPTEMBER), "--by", "e-0003"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    assert "people-2026-09.csv, 44 rows, headcount 43 (+0)" in done.stdout
    refused = subprocess.run(
        [sys.executable, "-m", "headcount.import", str(SEPTEMBER), "--by", PEOPLE],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert refused.returncode == 1
    assert refused.stderr.startswith("refused [role_not_allowed]: ")


def test_a_file_with_a_repeated_or_blank_row_is_refused(conn, finance, tmp_path):
    rows = read(SEPTEMBER)
    with pytest.raises(db.Refused, match="appears twice"):
        importer.run_import(conn, finance, write(tmp_path / "twice.csv", rows + rows[-1:]))
    rows[0]["start_date"] = ""
    with pytest.raises(db.Refused, match="start_date left blank"):
        importer.run_import(conn, finance, write(tmp_path / "blank.csv", rows))


def test_an_end_date_before_the_start_date_is_refused(conn, finance, tmp_path):
    rows = read(SEPTEMBER)
    rows[5]["end_date"] = "2020-03-31"
    with pytest.raises(db.Refused, match="before start_date"):
        importer.run_import(conn, finance, write(tmp_path / "early.csv", rows))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE people SET end_date = '2020-03-31' WHERE id = ?", (rows[5]["employee_number"],))


def test_the_import_logs_its_pay_reads_under_whoever_runs_it(conn, finance):
    before = conn.execute("SELECT MAX(id) FROM access_log").fetchone()[0]
    importer.run_import(conn, finance, SEPTEMBER)
    logged = conn.execute("SELECT actor_person, actor_system, person_id FROM access_log WHERE id > ?", (before,)).fetchall()
    assert {(r[0], r[1]) for r in logged} == {(finance.person_id, None)}
    assert sorted(r[2] for r in logged) == sorted(r["employee_number"] for r in read(SEPTEMBER))


def test_import_records_are_never_deleted(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM imports WHERE id = 1")


def test_the_store_refuses_a_forced_import_row_without_a_reason(conn):
    for reason in (None, "  "):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO imports (file_name, row_count, headcount, forced, reason, run_by, at)"
                " VALUES ('x.csv', 1, 1, 1, ?, 'e-0003', '2026-09-30T00:00:00Z')",
                (reason,),
            )


def test_the_import_is_run_by_a_person(conn):
    with pytest.raises(db.Refused) as refused:
        importer.run_import(conn, actors.system(conn, "monthly-report"), SEPTEMBER)
    assert refused.value.code == "run_by_person"


@pytest.mark.parametrize("field, value, code", [("manager", "e-0999", "no_such_manager"), ("kind", "intern", "bad_kind")])
def test_rows_name_a_manager_on_file_and_a_known_kind(conn, finance, tmp_path, field, value, code):
    rows = read(SEPTEMBER)
    rows[7][field] = value
    with pytest.raises(db.Refused) as refused:
        importer.run_import(conn, finance, write(tmp_path / "people.csv", rows))
    assert refused.value.code == code
