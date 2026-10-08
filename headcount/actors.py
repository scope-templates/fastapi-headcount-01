import sqlite3
from dataclasses import dataclass

from headcount import db

PAY_ROLES = ("finance", "people")
ACTOR_QUERY = "SELECT p.id, p.end_date, r.role FROM people p LEFT JOIN roles r ON r.person_id = p.id WHERE "


class Forbidden(db.Refusal):
    status = 403


class Unauthenticated(db.Refusal):
    status = 401


@dataclass(frozen=True)
class Actor:
    role: str
    person_id: str | None = None
    system: str | None = None

    @property
    def label(self) -> str:
        return self.person_id or f"system:{self.system}"


def _current(row: sqlite3.Row) -> Actor:
    if row["end_date"] and row["end_date"] < db.today().isoformat():
        raise Forbidden("person_left", f"{row['id']} left on {row['end_date']}")
    return Actor(role=row["role"] or "staff", person_id=row["id"])


def by_token(conn: sqlite3.Connection, token: str | None) -> Actor:
    if not token:
        raise Unauthenticated("token_missing", "send Authorization: Bearer <token>, or sign in at /sign-in")
    row = conn.execute(ACTOR_QUERY + "p.token = ?", (token,)).fetchone()
    if row is None:
        raise Unauthenticated("token_unknown", "that token belongs to nobody")
    return _current(row)


def person(conn: sqlite3.Connection, person_id: str) -> Actor:
    """For commands run on the desk's own machine, where the caller is named by person id."""
    row = conn.execute(ACTOR_QUERY + "p.id = ?", (person_id,)).fetchone()
    if row is None:
        raise Unauthenticated("no_such_person", f"no person {person_id}")
    return _current(row)


def system(conn: sqlite3.Connection, name: str) -> Actor:
    row = conn.execute("SELECT name, role FROM system_actors WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise Unauthenticated("no_such_system_actor", f"no system actor {name}")
    return Actor(role=row["role"], system=row["name"])


def require(actor: Actor, *roles: str) -> None:
    if actor.role not in roles:
        raise Forbidden("role_not_allowed", f"role {actor.role} may not do this")


def visible_ids(conn: sqlite3.Connection, actor: Actor) -> set[str] | None:
    """The person ids this actor may see; None means everyone."""
    if actor.role in PAY_ROLES:
        return None
    if actor.person_id is None:
        return set()
    if actor.role == "manager":
        rows = conn.execute("SELECT id FROM people WHERE manager_id = ?", (actor.person_id,))
        return {actor.person_id} | {r["id"] for r in rows}
    return {actor.person_id}


def require_visible(conn: sqlite3.Connection, actor: Actor, person_id: str) -> None:
    ids = visible_ids(conn, actor)
    if ids is not None and person_id not in ids:
        raise Forbidden("not_visible", f"{person_id} is not visible to {actor.label}")
