import sqlite3

from headcount import db
from headcount.actors import Actor, require


def record(conn: sqlite3.Connection, actor: Actor, what: str, person_ids: list[str]) -> None:
    at = db.now()
    conn.executemany(
        "INSERT INTO access_log (actor_person, actor_system, what, person_id, at) VALUES (?, ?, ?, ?, ?)",
        [(actor.person_id, actor.system, what, pid, at) for pid in person_ids],
    )


def entries(conn: sqlite3.Connection, actor: Actor, person_id: str | None = None, limit: int = 200) -> list[dict]:
    require(actor, "finance", "people")
    sql = "SELECT id, actor_person, actor_system, what, person_id, at FROM access_log"
    args: tuple = ()
    if person_id:
        sql += " WHERE person_id = ?"
        args = (person_id,)
    sql += " ORDER BY id DESC LIMIT ?"
    return [dict(r) for r in conn.execute(sql, args + (limit,))]
