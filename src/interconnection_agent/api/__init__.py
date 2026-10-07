"""Headway's API: what the website reads and does, over the tested modules.

``create_app`` builds it. The model is passed in: Claude in the product (when an API key is
set), a scripted stand-in in the browser tests. Run it with ``python -m
interconnection_agent.api``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from interconnection_agent.api import figures
from interconnection_agent.api.assessments import (
    REVIEWER,
    Assessments,
    answer_shown,
    as_shown,
    decision,
)
from interconnection_agent.assessment import (
    Adjustment,
    AgentStopped,
    AssessmentIsFinal,
    Model,
    NotReady,
    Project,
)
from interconnection_agent.budget import BudgetExceeded, Limits
from interconnection_agent.chances import NotEnoughHistory, ProjectType
from interconnection_agent.chances.groups import Conn
from interconnection_agent.db import connect as connect_to_database

NAME = "Headway"
NO_MODEL = (
    "Written assessments need an Anthropic API key, and none is set where this site runs. "
    "Everything else on the page works without one."
)


class NewAssessment(BaseModel):
    site: str
    project_type: ProjectType | None = None
    mw: float | None = Field(default=None, gt=0)


class AdjustRequest(BaseModel):
    why: str = Field(min_length=1)
    leave_out: list[str] = []
    comparison_group: str | None = None


class DecideRequest(BaseModel):
    judgement_id: str
    decision: str = Field(pattern="^(agree|disagree)$")
    why: str = ""


class RewordRequest(BaseModel):
    judgement_id: str
    text: str = Field(min_length=1)


class AskRequest(BaseModel):
    request: str = Field(min_length=1)


class AnswerRequest(BaseModel):
    answer_id: str


class RowsRequest(BaseModel):
    ids: list[str]


def _leave_out(text: str | None) -> frozenset[str]:
    return frozenset(i for i in (text or "").split(",") if i)


def create_app(
    model: Callable[[], Model | None],
    connect: Callable[[], Conn] = connect_to_database,
    *,
    limits: Limits | None = None,
    warm: bool = True,
) -> FastAPI:
    """The API. ``model`` gives the model to write with, or None if there's none."""
    assessments = Assessments(connect, limits)

    @contextmanager
    def database() -> Iterator[Conn]:
        conn = connect()
        try:
            conn.autocommit = True
            yield conn
        finally:
            conn.close()

    def warm_up() -> None:
        with database() as conn:
            figures.sites(conn)
            figures.overview(conn)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        if warm:
            threading.Thread(target=warm_up, daemon=True).start()
        yield

    app = FastAPI(title=f"{NAME} API", lifespan=lifespan)

    for kind, status in (
        (LookupError, 404),
        (KeyError, 404),
        (NotEnoughHistory, 422),
        (ValueError, 422),
        (AssessmentIsFinal, 409),
        (NotReady, 409),
        (BudgetExceeded, 429),
        (AgentStopped, 502),
    ):

        def handler(_: Request, e: Exception, status: int = status) -> JSONResponse:
            detail = e.args[0] if e.args else str(e)
            return JSONResponse({"detail": str(detail)}, status_code=status)

        app.add_exception_handler(kind, handler)

    # --- Figures ---

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        with database() as conn:
            return figures.overview(conn)

    @app.get("/api/sites")
    def sites() -> dict[str, Any]:
        with database() as conn:
            return figures.sites(conn)

    @app.get("/api/sites/{site}")
    def site(site: str, leave_out: str | None = None) -> dict[str, Any]:
        with database() as conn:
            return figures.site_detail(conn, site, _leave_out(leave_out))

    @app.get("/api/odds")
    def odds(
        place: str,
        project_type: ProjectType | None = None,
        mw: float | None = None,
        years: int = 10,
        group: str | None = None,
        leave_out: str | None = None,
    ) -> dict[str, Any]:
        with database() as conn:
            return figures.odds(
                conn,
                place=place,
                project_type=project_type,
                mw=mw,
                within_years=years,
                group=group,
                leave_out=_leave_out(leave_out),
            )

    @app.post("/api/rows")
    def rows(body: RowsRequest) -> dict[str, Any]:
        with database() as conn:
            return {"rows": figures.rows(conn, body.ids)}

    # --- Assessments ---

    def the_model() -> Model:
        found = model()
        if found is None:
            raise HTTPException(503, NO_MODEL)
        return found

    def shown(assessment_id: str) -> dict[str, Any]:
        return as_shown(assessment_id, assessments.get(assessment_id).assessment)

    @app.post("/api/assessments", status_code=201)
    def create(body: NewAssessment) -> dict[str, Any]:
        project = Project(body.project_type, body.mw if body.project_type else None)
        assessment_id = assessments.write(the_model(), site=body.site, project=project)
        return shown(assessment_id)

    @app.get("/api/assessments/{assessment_id}")
    def read(assessment_id: str) -> dict[str, Any]:
        return shown(assessment_id)

    @app.post("/api/assessments/{assessment_id}/adjust")
    def adjust(assessment_id: str, body: AdjustRequest) -> dict[str, Any]:
        made = Adjustment(body.why, frozenset(body.leave_out), body.comparison_group)
        assessments.change(assessment_id, lambda a: a.adjust(made, by=REVIEWER))
        return shown(assessment_id)

    @app.post("/api/assessments/{assessment_id}/decide")
    def decide(assessment_id: str, body: DecideRequest) -> dict[str, Any]:
        chosen = decision(body.decision)
        assessments.change(
            assessment_id, lambda a: a.decide(body.judgement_id, chosen, by=REVIEWER, why=body.why)
        )
        return shown(assessment_id)

    @app.post("/api/assessments/{assessment_id}/reword")
    def reword(assessment_id: str, body: RewordRequest) -> dict[str, Any]:
        assessments.change(
            assessment_id, lambda a: a.rewrite(body.judgement_id, body.text, by=REVIEWER)
        )
        return shown(assessment_id)

    @app.post("/api/assessments/{assessment_id}/finalise")
    def finalise(assessment_id: str) -> dict[str, Any]:
        assessments.change(assessment_id, lambda a: a.finalise(by=REVIEWER))
        return shown(assessment_id)

    @app.post("/api/assessments/{assessment_id}/ask")
    def ask(assessment_id: str, body: AskRequest) -> dict[str, Any]:
        answer = assessments.ask(assessment_id, the_model(), body.request)
        lookups = assessments.get(assessment_id).assessment.lookups
        return {"answer": answer_shown(answer, lookups), "assessment": shown(assessment_id)}

    @app.post("/api/assessments/{assessment_id}/add")
    def add(assessment_id: str, body: AnswerRequest) -> dict[str, Any]:
        assessments.change(assessment_id, lambda a: a.add(body.answer_id, by=REVIEWER))
        return shown(assessment_id)

    @app.post("/api/assessments/{assessment_id}/confirm")
    def confirm(assessment_id: str, body: AnswerRequest) -> dict[str, Any]:
        assessments.change(assessment_id, lambda a: a.confirm(body.answer_id, by=REVIEWER))
        return shown(assessment_id)

    return app
