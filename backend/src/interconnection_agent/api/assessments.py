"""Assessments as the website sees them: written by the agent, then reviewed on the page.

Each assessment keeps its own database connection, because its lookups are run again when a
person adjusts it. Writing one takes a minute or two, so it happens in the background and the
page checks back. They live in memory for now; saving and sharing them is ticket 5.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from interconnection_agent.assessment import (
    Answer,
    Assessment,
    Decision,
    FactualClaim,
    Judgement,
    Model,
    NotReady,
    Project,
    ask,
    write_assessment,
)
from interconnection_agent.assessment.check import SLOT
from interconnection_agent.assessment.lookups import Lookups
from interconnection_agent.assessment.review import shown
from interconnection_agent.budget import Limits
from interconnection_agent.chances.groups import Conn

# There are no accounts, so every change is logged as the reviewer's.
REVIEWER = "the reviewer"


@dataclass
class _Kept:
    assessment: Assessment
    conn: Conn
    lock: threading.Lock = field(default_factory=threading.Lock)


class Assessments:
    """The assessments written so far, by id."""

    def __init__(self, connect: Callable[[], Conn], limits: Limits | None = None) -> None:
        self._connect = connect
        self._limits = limits
        self._kept: dict[str, _Kept] = {}
        self._writing: set[str] = set()
        self._failed: dict[str, Exception] = {}

    def start(self, model: Model, *, site: str, project: Project) -> str:
        """Start writing an assessment in the background and return its id straight away."""
        assessment_id = uuid.uuid4().hex[:12]
        self._writing.add(assessment_id)

        def write() -> None:
            try:
                self._kept[assessment_id] = self._write(model, site=site, project=project)
            except Exception as e:
                self._failed[assessment_id] = e
            finally:
                self._writing.discard(assessment_id)

        threading.Thread(target=write, daemon=True).start()
        return assessment_id

    def _write(self, model: Model, *, site: str, project: Project) -> _Kept:
        conn = self._connect()
        conn.autocommit = True
        try:
            assessment = write_assessment(
                conn, model, site=site, project=project, limits=self._limits
            )
        except BaseException:
            conn.close()
            raise
        return _Kept(assessment, conn)

    def writing(self, assessment_id: str) -> bool:
        """Whether the assessment is still being written."""
        return assessment_id in self._writing

    def get(self, assessment_id: str) -> _Kept:
        """The written assessment. Raises why, if writing it failed."""
        if assessment_id in self._failed:
            raise self._failed[assessment_id]
        if assessment_id in self._writing:
            raise NotReady("This write-up is still being written.")
        if assessment_id not in self._kept:
            raise KeyError(f"No assessment called {assessment_id!r}.")
        return self._kept[assessment_id]

    def ask(self, assessment_id: str, model: Model, request: str) -> Answer:
        kept = self.get(assessment_id)
        with kept.lock:
            return ask(kept.assessment, model, request)

    def change(self, assessment_id: str, do: Callable[[Assessment], None]) -> None:
        kept = self.get(assessment_id)
        with kept.lock:
            do(kept.assessment)


def decision(word: str) -> Decision:
    return {"agree": Decision.APPROVED, "disagree": Decision.REJECTED}[word]


# --- As the page shows it --------------------------------------------------------------


def as_shown(assessment_id: str, a: Assessment) -> dict[str, Any]:
    return {
        "id": assessment_id,
        "site": a.site,
        "project": {
            "type": str(a.project.project_type) if a.project.project_type else None,
            "mw": a.project.mw,
            "describe": a.project.describe(),
        },
        "final": a.final,
        "claims": claims_shown(a.claims),
        "held": [answer_shown(x, a.lookups) for x in a.held.values()],
        "changes": [
            {"when": c.when.isoformat(), "who": c.who, "what": c.what, "why": c.why}
            for c in a.changes
        ],
        "left_out": sorted(a.lookups.leave_out),
        "comparison_group": a.lookups.comparison_group,
        "questions_left": a.budget.calls_left,
    }


def claims_shown(claims: Iterable[FactualClaim | Judgement]) -> list[dict[str, Any]]:
    return [c for c in (claim_shown(c) for c in claims) if c is not None]


def claim_shown(claim: FactualClaim | Judgement) -> dict[str, Any] | None:
    """A claim as the page shows it, or None if it isn't shown: a Factual Claim only once it
    passed the check, each number carrying the rows it was worked out from."""
    if isinstance(claim, Judgement):
        return {
            "id": claim.id,
            "kind": "judgement",
            "text": claim.text,
            "based_on": list(claim.based_on),
            "decision": {
                Decision.AWAITING: "awaiting",
                Decision.APPROVED: "agreed",
                Decision.REJECTED: "disagreed",
                Decision.REWRITTEN: "reworded",
            }[claim.decision],
        }
    if claim.check is None or not claim.check.passed:
        return None
    parts: list[dict[str, Any]] = []
    at = 0
    for slot in SLOT.finditer(claim.text):
        if slot.start() > at:
            parts.append({"text": claim.text[at : slot.start()]})
        i = int(slot.group(1))
        number = claim.check.worked_out[i]
        assert number is not None
        parts.append(
            {
                "number": shown(number, claim.values[i].unit),
                "rows": sorted(claim.check.rows[i]),
            }
        )
        at = slot.end()
    if at < len(claim.text):
        parts.append({"text": claim.text[at:]})
    return {"id": claim.id, "kind": "factual", "parts": parts}


def answer_shown(answer: Answer, lookups: Lookups) -> dict[str, Any]:
    """An answer as the page shows it, with the lookups its numbers came from ("how this
    was answered")."""
    proposal = answer.proposal
    used = sorted(
        {v.tool_call_id for c in answer.claims if isinstance(c, FactualClaim) for v in c.values}
    )
    ran = [lookups.log[i] for i in used if i in lookups.log]
    return {
        "id": answer.id,
        "request": answer.request,
        "claims": claims_shown(answer.claims),
        "lookups": [
            {
                "tool": x.tool,
                "asked": {k: v for k, v in x.arguments.items()},
                "rows": len(x.rows) or max((len(f.rows) for f in x.figures.values()), default=0),
            }
            for x in ran
        ],
        "rejected": len(answer.rejected),
        "cant_answer": answer.cant_answer,
        "proposal": (
            {
                "description": proposal.description,
                "leave_out": sorted(proposal.adjustment.leave_out),
                "comparison_group": proposal.adjustment.comparison_group,
                "why": proposal.adjustment.why,
            }
            if proposal
            else None
        ),
    }
