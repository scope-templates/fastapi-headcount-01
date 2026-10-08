"""Built per store by create_app, so run it with: python -m uvicorn --factory headcount.app:create_app"""

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import BaseModel, Field

from headcount import access_log, actors, db, hiring, pay, people, reports, timeoff
from headcount.actors import Actor

pages = Environment(loader=PackageLoader("headcount", "templates"), autoescape=select_autoescape())
pages.filters["dollars"] = lambda cents: f"${cents / 100:,.2f}"


class NewRate(BaseModel):
    amount_cents: int = Field(gt=0)
    per: str
    effective_date: date
    reason: str | None = None


class SignIn(BaseModel):
    token: str


class EndDate(BaseModel):
    end_date: date


class Identifier(BaseModel):
    value: str


class TimeOff(BaseModel):
    person_id: str
    kind: str
    first_day: date
    last_day: date
    note: str = ""


class EnterHire(BaseModel):
    name: str
    title: str
    manager_id: str
    location: str
    kind: str
    start_date: date
    amount_cents: int = Field(gt=0)
    per: str
    identifier: str
    pay_reason: str | None = None


def _refusal(request: Request, exc: db.Refusal) -> JSONResponse:
    return JSONResponse({"reason": exc.code, "detail": str(exc)}, status_code=exc.status)


def _constraint(request: Request, exc: sqlite3.IntegrityError) -> JSONResponse:
    return JSONResponse({"reason": "store_constraint", "detail": str(exc)}, status_code=409)


def create_app(db_file: Path | str | None = None) -> FastAPI:
    path = db_file or db.db_path()
    db.open_store(path).close()
    app = FastAPI(title="Headcount and pay desk")
    app.add_exception_handler(db.Refusal, _refusal)
    app.add_exception_handler(sqlite3.IntegrityError, _constraint)

    def conn() -> Iterator[sqlite3.Connection]:
        connection = db.connect(path)
        try:
            yield connection
        finally:
            connection.close()

    def actor(
        request: Request,
        connection: sqlite3.Connection = Depends(conn),
        authorization: str | None = Header(default=None),
    ) -> Actor:
        scheme, _, token = (authorization or "").partition(" ")
        if authorization and scheme.lower() != "bearer":
            raise actors.Unauthenticated("bad_scheme", "use Authorization: Bearer <token>")
        return actors.by_token(connection, token.strip() or request.cookies.get("token"))

    def render(name: str, **values) -> HTMLResponse:
        last_month = (db.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        return HTMLResponse(pages.get_template(name).render(last_month=last_month, **values))

    @app.get("/sign-in", response_class=HTMLResponse)
    def sign_in_page():
        return render("sign_in.html")

    @app.post("/sign-in")
    def sign_in(body: SignIn, connection: sqlite3.Connection = Depends(conn)):
        who = actors.by_token(connection, body.token.strip())
        response = JSONResponse({"person_id": who.person_id, "role": who.role})
        response.set_cookie("token", body.token.strip(), httponly=True, samesite="strict")
        return response

    @app.get("/people")
    def list_people(include_left: bool = False, who: Actor = Depends(actor), c=Depends(conn)):
        return people.list_people(c, who, include_left)

    @app.get("/people/{person_id}")
    def get_person(person_id: str, who: Actor = Depends(actor), c=Depends(conn)):
        return people.get_person(c, who, person_id)

    @app.post("/people/{person_id}/end-date")
    def record_end_date(person_id: str, body: EndDate, who: Actor = Depends(actor), c=Depends(conn)):
        with c:
            people.record_end_date(c, who, person_id, body.end_date.isoformat())
        return people.get_person(c, who, person_id)

    @app.get("/people/{person_id}/pay")
    def pay_rates(person_id: str, who: Actor = Depends(actor), c=Depends(conn)):
        return pay.rates_for(c, who, person_id)

    @app.post("/people/{person_id}/pay", status_code=201)
    def add_pay_rate(person_id: str, body: NewRate, who: Actor = Depends(actor), c=Depends(conn)):
        with c:
            rate_id = pay.add_rate(c, who, person_id, body.amount_cents, body.per,
                                   body.effective_date.isoformat(), body.reason)
        return {"id": rate_id}

    @app.get("/people/{person_id}/identifier")
    def read_identifier(person_id: str, who: Actor = Depends(actor), c=Depends(conn)):
        return {"person_id": person_id, "last_four": people.read_identifier(c, who, person_id)}

    @app.put("/people/{person_id}/identifier")
    def set_identifier(person_id: str, body: Identifier, who: Actor = Depends(actor), c=Depends(conn)):
        with c:
            kept = people.set_identifier(c, who, person_id, body.value)
        return {"person_id": person_id, "last_four": kept}

    @app.get("/people/{person_id}/time-off")
    def time_off_for(person_id: str, who: Actor = Depends(actor), c=Depends(conn)):
        return timeoff.requests_for(c, who, person_id)

    @app.get("/people/{person_id}/time-off/balance")
    def time_off_balance(person_id: str, year: int | None = None, who: Actor = Depends(actor), c=Depends(conn)):
        return timeoff.balance(c, who, person_id, year or db.today().year)

    @app.post("/time-off", status_code=201)
    def book_time_off(body: TimeOff, who: Actor = Depends(actor), c=Depends(conn)):
        return timeoff.book(c, who, body.person_id, body.kind, body.first_day.isoformat(),
                            body.last_day.isoformat(), body.note)

    @app.get("/time-off/out")
    def out(first_day: date | None = None, last_day: date | None = None,
            who: Actor = Depends(actor), c=Depends(conn)):
        first, last = _next_week(first_day, last_day)
        return timeoff.out_between(c, who, first, last)

    @app.get("/hiring-plan")
    def hiring_plan(who: Actor = Depends(actor), c=Depends(conn)):
        return hiring.plan(c, who)

    @app.post("/hiring-plan/{plan_id}/enter", status_code=201)
    def enter_hire(plan_id: str, body: EnterHire, who: Actor = Depends(actor), c=Depends(conn)):
        details = body.model_dump()
        details["start_date"] = body.start_date.isoformat()
        return hiring.enter(c, who, plan_id, **details)

    @app.get("/reports/headcount")
    def headcount(day: date | None = None, who: Actor = Depends(actor), c=Depends(conn)):
        return reports.headcount(c, who, (day or db.today()).isoformat())

    @app.get("/reports/cost/{month}")
    def cost(month: str, who: Actor = Depends(actor), c=Depends(conn)):
        return reports.monthly_cost(c, who, month)

    @app.get("/reports/budget/{month}")
    def budget(month: str, who: Actor = Depends(actor), c=Depends(conn)):
        return reports.budget(c, who, month)

    @app.get("/reports/saved")
    def saved(who: Actor = Depends(actor), c=Depends(conn)):
        return reports.saved_reports(c, who)

    @app.get("/imports")
    def imports(who: Actor = Depends(actor), c=Depends(conn)):
        actors.require(who, "finance", "people")
        return [dict(r) for r in c.execute("SELECT * FROM imports ORDER BY id DESC")]

    @app.get("/access-log")
    def read_access_log(person_id: str | None = None, who: Actor = Depends(actor), c=Depends(conn)):
        return access_log.entries(c, who, person_id)

    @app.get("/pages/headcount", response_class=HTMLResponse)
    def headcount_page(who: Actor = Depends(actor), c=Depends(conn)):
        today = db.today().isoformat()
        return render("headcount.html", who=who, report=reports.headcount(c, who, today),
                      people=people.list_people(c, who), last_import=reports.last_import(c))

    @app.get("/pages/cost/{month}", response_class=HTMLResponse)
    def cost_page(month: str, who: Actor = Depends(actor), c=Depends(conn)):
        return render("cost.html", who=who, report=reports.monthly_cost(c, who, month),
                      last_import=reports.last_import(c))

    @app.get("/pages/out", response_class=HTMLResponse)
    def out_page(first_day: date | None = None, who: Actor = Depends(actor), c=Depends(conn)):
        first, last = _next_week(first_day, None)
        return render("out.html", who=who, first=first, last=last, rows=timeoff.out_between(c, who, first, last),
                      last_import=reports.last_import(c))

    @app.get("/time-off/new", response_class=HTMLResponse)
    def time_off_form(who: Actor = Depends(actor), c=Depends(conn)):
        actors.require(who, "manager", "people")
        reports_to = [p for p in people.list_people(c, who) if who.role == "people" or p["manager_id"] == who.person_id]
        return render("time_off_form.html", who=who, people=reports_to, kinds=timeoff.KINDS)

    return app


def _next_week(first_day: date | None, last_day: date | None) -> tuple[str, str]:
    """The given days, or Monday to Friday of next week."""
    if first_day:
        return first_day.isoformat(), (last_day or first_day + timedelta(days=4)).isoformat()
    return timeoff.week_of(db.today() + timedelta(days=7))
