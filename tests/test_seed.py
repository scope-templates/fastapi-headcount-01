import importlib.util

from headcount import db
from headcount.db import ROOT


def load_generator():
    spec = importlib.util.spec_from_file_location("make_seed", ROOT / "scripts" / "make_seed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_generator_reproduces_the_committed_files_byte_for_byte():
    generator = load_generator()
    seed, files = generator.build()
    assert generator.render(seed).encode() == (ROOT / "data" / "seed.json").read_bytes()
    for name, text in files.items():
        assert text.encode() == (ROOT / "data" / "imports" / name).read_bytes()


def test_the_seed_loads_once_into_an_empty_store(db_file):
    first = db.open_store(db_file)
    people = first.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    first.close()
    again = db.open_store(db_file)
    assert again.execute("SELECT COUNT(*) FROM people").fetchone()[0] == people
    again.close()


def test_the_only_system_actor_is_the_monthly_report(conn):
    assert [tuple(r) for r in conn.execute("SELECT name, role FROM system_actors")] == [("monthly-report", "finance")]
