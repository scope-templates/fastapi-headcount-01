import sqlite3

import pytest

from tests.conftest import FINANCE, REPORT

ROW_ONE = {
    "access_log": (
        "(id, actor_person, actor_system, what, person_id, at)",
        (1, FINANCE, None, "pay_rate", REPORT, "2099-01-01T00:00:00Z"),
        "at = excluded.at",
    ),
    "pay_rates": (
        "(id, person_id, amount_cents, currency, per, effective_date, entered_by, entered_at, reason)",
        (1, REPORT, 1, "USD", "year", "2099-01-01", FINANCE, "2026-10-01T00:00:00Z", None),
        "amount_cents = excluded.amount_cents",
    ),
    "imports": (
        "(id, file_name, row_count, headcount, forced, run_by, at)",
        (1, "x.csv", 1, 1, 0, FINANCE, "2026-10-01T00:00:00Z"),
        "row_count = excluded.row_count",
    ),
}


@pytest.fixture
def raw(conn, db_file):
    """A bare connection with none of the desk's pragmas."""
    connection = sqlite3.connect(db_file)
    yield connection
    connection.close()


@pytest.mark.parametrize("table", sorted(ROW_ONE))
def test_append_only_rows_are_never_replaced_or_upserted(raw, table):
    columns, values, update = ROW_ONE[table]
    before = raw.execute(f"SELECT * FROM {table} WHERE id = 1").fetchone()
    count = raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    marks = ", ".join("?" for _ in values)
    for sql in (
        f"INSERT OR REPLACE INTO {table} {columns} VALUES ({marks})",
        f"REPLACE INTO {table} {columns} VALUES ({marks})",
        f"INSERT INTO {table} {columns} VALUES ({marks}) ON CONFLICT (id) DO UPDATE SET {update}",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            raw.execute(sql, values)
    assert raw.execute(f"SELECT * FROM {table} WHERE id = 1").fetchone() == before
    assert raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == count


def test_an_access_log_entry_names_a_person_on_file(raw):
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute(
            "INSERT INTO access_log (actor_person, what, person_id, at)"
            " VALUES (?, 'pay_rate', 'e-9999', '2026-10-01T00:00:00Z')",
            (FINANCE,),
        )


@pytest.mark.parametrize("first, last, note", [("2099-03-09", "2099-03-13", "x" * 61), ("2099-03-13", "2099-03-09", "")])
def test_time_off_rows_keep_short_notes_and_ordered_days(raw, first, last, note):
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute(
            "INSERT INTO time_off_requests (person_id, kind, first_day, last_day, days, note, entered_by, entered_at)"
            " VALUES (?, 'vacation', ?, ?, 5, ?, 'e-0004', '2026-10-01T00:00:00Z')",
            (REPORT, first, last, note),
        )


def test_tokens_are_32_characters_and_unique(raw):
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute("UPDATE people SET token = 'abc' WHERE id = ?", (REPORT,))
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute("UPDATE people SET token = (SELECT token FROM people WHERE id = ?) WHERE id = ?", (FINANCE, REPORT))


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE hiring_plan SET status = 'entered' WHERE id = 'H-07'",
        "UPDATE hiring_plan SET person_id = NULL WHERE id = 'H-01'",
        "UPDATE hiring_plan SET band_max_cents = band_min_cents - 1 WHERE id = 'H-07'",
    ],
)
def test_hiring_plan_rows_stay_consistent(raw, sql):
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute(sql)
