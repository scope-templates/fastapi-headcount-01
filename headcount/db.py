import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = ROOT / "data" / "seed.json"
DEFAULT_DB = ROOT / "headcount.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS system_actors (
    name TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('finance', 'people')),
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY,
    file_name TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    headcount INTEGER NOT NULL,
    headcount_delta INTEGER,
    forced INTEGER NOT NULL DEFAULT 0 CHECK (forced IN (0, 1)),
    reason TEXT,
    run_by TEXT NOT NULL REFERENCES people(id),
    at TEXT NOT NULL,
    CHECK (forced = 0 OR COALESCE(length(trim(reason)), 0) > 0)
);

CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    team TEXT NOT NULL,
    manager_id TEXT REFERENCES people(id),
    location TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('employee', 'contractor')),
    start_date TEXT NOT NULL,
    end_date TEXT,
    token TEXT NOT NULL UNIQUE CHECK (length(token) = 32),
    entered_at TEXT NOT NULL,
    entered_by TEXT NOT NULL REFERENCES people(id),
    last_import_id INTEGER REFERENCES imports(id),
    CHECK (end_date IS NULL OR end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS roles (
    person_id TEXT PRIMARY KEY REFERENCES people(id),
    role TEXT NOT NULL CHECK (role IN ('finance', 'people', 'manager'))
);

CREATE TABLE IF NOT EXISTS identifiers (
    person_id TEXT PRIMARY KEY REFERENCES people(id),
    last_four TEXT NOT NULL CHECK (length(last_four) = 4),
    entered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pay_rates (
    id INTEGER PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES people(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    per TEXT NOT NULL CHECK (per IN ('year', 'month')),
    effective_date TEXT NOT NULL,
    entered_by TEXT NOT NULL REFERENCES people(id),
    entered_at TEXT NOT NULL,
    reason TEXT,
    CHECK (effective_date >= substr(entered_at, 1, 10) OR COALESCE(length(trim(reason)), 0) > 0)
);

CREATE TABLE IF NOT EXISTS time_off_balances (
    person_id TEXT NOT NULL REFERENCES people(id),
    year INTEGER NOT NULL,
    allowance_days INTEGER NOT NULL,
    carried_over_days INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (person_id, year)
);

CREATE TABLE IF NOT EXISTS time_off_requests (
    id INTEGER PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES people(id),
    kind TEXT NOT NULL CHECK (kind IN ('vacation', 'sick', 'parental', 'other')),
    first_day TEXT NOT NULL,
    last_day TEXT NOT NULL,
    days INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 60),
    entered_by TEXT NOT NULL REFERENCES people(id),
    entered_at TEXT NOT NULL,
    CHECK (last_day >= first_day)
);

CREATE TABLE IF NOT EXISTS hiring_plan (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    team TEXT NOT NULL,
    planned_start TEXT NOT NULL,
    band_min_cents INTEGER NOT NULL,
    band_max_cents INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'entered', 'withdrawn')),
    approved_on TEXT NOT NULL,
    person_id TEXT REFERENCES people(id),
    entered_at TEXT,
    entered_by TEXT REFERENCES people(id),
    CHECK (band_max_cents >= band_min_cents),
    CHECK ((status = 'entered') = (person_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS access_log (
    id INTEGER PRIMARY KEY,
    actor_person TEXT REFERENCES people(id),
    actor_system TEXT REFERENCES system_actors(name),
    what TEXT NOT NULL CHECK (what IN ('pay_rate', 'identifier')),
    person_id TEXT NOT NULL REFERENCES people(id),
    at TEXT NOT NULL,
    CHECK ((COALESCE(actor_person, '') <> '') + (COALESCE(actor_system, '') <> '') = 1)
);

CREATE TABLE IF NOT EXISTS monthly_reports (
    month TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    generated_by TEXT NOT NULL REFERENCES system_actors(name),
    headcount INTEGER NOT NULL,
    total_cents INTEGER NOT NULL,
    PRIMARY KEY (month, generated_at)
);

CREATE TRIGGER IF NOT EXISTS pay_rates_keep_rows BEFORE UPDATE ON pay_rates
BEGIN SELECT RAISE(ABORT, 'pay rates are never edited; add a new row with its effective date'); END;
CREATE TRIGGER IF NOT EXISTS pay_rates_keep_rows_on_delete BEFORE DELETE ON pay_rates
BEGIN SELECT RAISE(ABORT, 'pay rates are never deleted'); END;
CREATE TRIGGER IF NOT EXISTS time_off_within_employment BEFORE INSERT ON time_off_requests
WHEN EXISTS (SELECT 1 FROM people WHERE id = NEW.person_id AND end_date IS NOT NULL AND NEW.last_day > end_date)
BEGIN SELECT RAISE(ABORT, 'time off cannot run past the end date'); END;
CREATE TRIGGER IF NOT EXISTS access_log_known_actor BEFORE INSERT ON access_log
WHEN NOT EXISTS (SELECT 1 FROM people WHERE id = NEW.actor_person)
 AND NOT EXISTS (SELECT 1 FROM system_actors WHERE name = NEW.actor_system)
BEGIN SELECT RAISE(ABORT, 'an access-log entry names a person or a system actor'); END;
CREATE TRIGGER IF NOT EXISTS access_log_known_person BEFORE INSERT ON access_log
WHEN NOT EXISTS (SELECT 1 FROM people WHERE id = NEW.person_id)
BEGIN SELECT RAISE(ABORT, 'an access-log entry names the person whose record was read'); END;
CREATE TRIGGER IF NOT EXISTS access_log_append_only BEFORE UPDATE ON access_log
BEGIN SELECT RAISE(ABORT, 'the access log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS access_log_append_only_on_delete BEFORE DELETE ON access_log
BEGIN SELECT RAISE(ABORT, 'the access log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS imports_append_only BEFORE UPDATE ON imports
BEGIN SELECT RAISE(ABORT, 'import records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS imports_append_only_on_delete BEFORE DELETE ON imports
BEGIN SELECT RAISE(ABORT, 'import records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS access_log_no_replace BEFORE INSERT ON access_log
WHEN EXISTS (SELECT 1 FROM access_log WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'access_log rows are never replaced'); END;
CREATE TRIGGER IF NOT EXISTS pay_rates_no_replace BEFORE INSERT ON pay_rates
WHEN EXISTS (SELECT 1 FROM pay_rates WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'pay_rates rows are never replaced'); END;
CREATE TRIGGER IF NOT EXISTS imports_no_replace BEFORE INSERT ON imports
WHEN EXISTS (SELECT 1 FROM imports WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'imports rows are never replaced'); END;
"""

# Insert order for the seed: every row's references exist before it.
SEED_TABLES = (
    "system_actors",
    "people",
    "imports",
    "roles",
    "identifiers",
    "pay_rates",
    "time_off_balances",
    "time_off_requests",
    "hiring_plan",
    "access_log",
    "monthly_reports",
)


class Refusal(Exception):
    """A request the desk turns down, with a short reason code for callers and an HTTP status for the API."""

    status = 422

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Refused(Refusal):
    status = 422


class NotFound(Refusal):
    status = 404


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> date:
    return date.fromisoformat(now()[:10])


def require_person(conn: sqlite3.Connection, person_id: str) -> None:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone() is None:
        raise NotFound("no_such_person", f"no person {person_id}")


def db_path() -> Path:
    return Path(os.environ.get("HEADCOUNT_DB", DEFAULT_DB))


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA recursive_triggers = ON")
    return conn


def open_store(path: Path | str | None = None, seed_file: Path = SEED_FILE) -> sqlite3.Connection:
    """Connect, create the tables, and load the seed when the store is empty."""
    conn = connect(path)
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 0:
        load_seed(conn, json.loads(seed_file.read_text(encoding="utf-8")))
    return conn


@contextmanager
def deferred_references(conn: sqlite3.Connection):
    """One transaction whose foreign keys are checked at commit, so rows may name each other."""
    with conn:
        conn.execute("BEGIN")
        conn.execute("PRAGMA defer_foreign_keys = ON")
        yield


def load_seed(conn: sqlite3.Connection, seed: dict) -> None:
    with deferred_references(conn):
        for table in SEED_TABLES:
            rows = seed.get(table, [])
            if not rows:
                continue
            columns = list(rows[0])
            sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
            conn.executemany(sql, [tuple(row[c] for c in columns) for row in rows])
