"""The agent: the model looks things up and writes claims; code checks them.

The model's only way to state anything is a claim submitted through a tool. It never
writes the text a reader sees. Every model call goes through the assessment's spending
limits (``interconnection_agent.budget``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from anthropic.types.beta import BetaMessage

from interconnection_agent.assessment.check import check, unchecked_numbers
from interconnection_agent.assessment.claims import (
    Claim,
    FactualClaim,
    Parsed,
    Rejected,
    parse_claims,
)
from interconnection_agent.assessment.lookups import LookupRefused, Lookups, places_at
from interconnection_agent.assessment.review import Adjustment, Assessment, Project
from interconnection_agent.budget import AssessmentBudget, Limits
from interconnection_agent.chances import ProjectType
from interconnection_agent.chances.groups import Conn, data_as_of
from interconnection_agent.settings import Settings

SKILL = Path(__file__).resolve().parents[1] / "skills/writing-an-assessment/SKILL.md"
MODEL = "claude-opus-5-5"
# A submission with rejected claims is sent back once to be fixed; the next is final.
SUBMISSIONS = 2


class Model(Protocol):
    """Where requests go: Claude in the product, a scripted stand-in in tests."""

    def create(self, **request: Any) -> BetaMessage: ...


class Claude:
    """The real model, through the Anthropic API. If a request is declined on safety
    grounds, the API retries it on a fallback model it picks (``fallbacks="default"``)."""

    def __init__(self, settings: Settings) -> None:
        import anthropic

        self._messages = anthropic.Anthropic(api_key=settings.api_key).beta.messages

    def create(self, **request: Any) -> BetaMessage:
        message: BetaMessage = self._messages.create(
            **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
        )
        return message


class AgentStopped(RuntimeError):
    """The model declined, or stopped without submitting anything usable."""


_PLACE = {"type": "string", "description": "A voltage section, such as 'Whirlwind 230 kV'."}
_SITE = {"type": "string", "description": "A substation, such as 'Whirlwind'."}
_TYPE = {"type": "string", "enum": [str(t) for t in ProjectType]}
_VALUE = {
    "type": "object",
    "properties": {
        "value": {"type": "number"},
        "unit": {"type": "string", "enum": ["MW", "years", "%", "projects"]},
        "derivation": {"type": "string", "enum": ["direct", "sum", "count", "median", "ratio"]},
        "of": {"type": "string"},
        "source": {"type": "string", "enum": ["caiso_raw", "lbnl"]},
        "tool_call_id": {"type": "string"},
        "source_row_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["value", "unit", "derivation", "of", "source", "tool_call_id"],
}
_CLAIMS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["factual", "judgement"]},
            "id": {"type": "string"},
            "text": {"type": "string"},
            "values": {"type": "array", "items": _VALUE},
            "based_on": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["kind", "id", "text"],
    },
}
LOOKUP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "chance_of_being_built",
        "description": "The chance that projects like this one are built within N years of "
        "applying, its likely range, the typical wait, and the past projects it rests on.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place": _PLACE,
                "project_type": _TYPE,
                "mw": {"type": "number", "description": "MW to grid."},
                "within_years": {"type": "number"},
                "group": {
                    "type": "string",
                    "description": "Use this comparison group instead, by its description.",
                },
            },
            "required": ["within_years"],
        },
    },
    {
        "name": "realistic_mw_ahead",
        "description": "MW waiting at a substation or voltage section, each project counted "
        "by its chance of still being built; and the 2023 batch's waiting MW on its own.",
        "input_schema": {"type": "object", "properties": {"place": _PLACE, "site": _SITE}},
    },
    {
        "name": "list_projects",
        "description": "Projects at a substation or voltage section, filtered by status, "
        "rules and type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place": _PLACE,
                "site": _SITE,
                "status": {"type": "string", "enum": ["waiting", "built", "withdrawn"]},
                "rules": {"type": "string", "enum": ["old", "2023 batch", "any"]},
                "project_type": _TYPE,
            },
            "required": ["status"],
        },
    },
]
PROPOSE_ADJUSTMENT = {
    "name": "propose_adjustment",
    "description": "Propose leaving projects out of the assessment, when a person asks for "
    "that. Nothing changes until a person confirms. Give projects by id, or "
    "waiting_since_year to leave out projects still waiting at this substation that "
    "joined the queue in that year or earlier.",
    "input_schema": {
        "type": "object",
        "properties": {
            "projects": {"type": "array", "items": {"type": "string"}},
            "waiting_since_year": {"type": "integer"},
            "why": {"type": "string", "description": "The reason, in the person's words."},
        },
        "required": ["why"],
    },
}
SUBMIT_ASSESSMENT = {
    "name": "submit_assessment",
    "description": "Submit the assessment: Factual Claims and Judgements only.",
    "input_schema": {"type": "object", "properties": {"claims": _CLAIMS}, "required": ["claims"]},
}


def write_assessment(
    conn: Conn,
    model: Model,
    *,
    site: str,
    project: Project,
    limits: Limits | None = None,
    model_id: str = MODEL,
) -> Assessment:
    """Have the model write an assessment for ``project`` at ``site``, checked claim by
    claim. Raises a :class:`~interconnection_agent.budget.BudgetExceeded` if it goes over
    its limits, and :class:`AgentStopped` if it ends without submitting."""
    lookups = Lookups(conn)
    brief = (
        f"Write an assessment for a {project.describe()} connecting at the {site} "
        f"substation. Its voltage sections: {', '.join(places_at(conn, site))}. "
        f"The data was taken on {data_as_of(conn).isoformat()}. Look things up, then submit "
        "with submit_assessment."
    )
    outcome = _run(
        model,
        lookups,
        brief,
        tools=[*LOOKUP_TOOLS, SUBMIT_ASSESSMENT],
        limits=limits or Limits(),
        model_id=model_id,
    )
    parsed = outcome.parsed or Parsed()
    assessment = Assessment(site, project, lookups, parsed.claims, parsed.rejected)
    assessment.log("the agent", "wrote the assessment")
    return assessment


@dataclass(frozen=True)
class ProposedAdjustment:
    """An Adjustment the agent proposes from a person's request. It does nothing until a
    person confirms it with ``Assessment.adjust``."""

    adjustment: Adjustment
    description: str  # in plain words, naming every project it would leave out


@dataclass(frozen=True)
class Answer:
    claims: tuple[Claim, ...] = ()  # new claims, checked and added to the assessment
    rejected: tuple[Rejected, ...] = ()
    proposal: ProposedAdjustment | None = None


def ask(
    assessment: Assessment,
    model: Model,
    request: str,
    *,
    limits: Limits | None = None,
    model_id: str = MODEL,
) -> Answer:
    """Answer a person's plain request about an assessment: with new checked claims, which
    are added to it, or with a proposed Adjustment, which isn't applied."""
    assessment.still_open()
    shown = "\n".join(f"- {c.id}: {c.text}" for c in assessment.claims)
    brief = (
        f"This is an assessment for a {assessment.project.describe()} connecting at the "
        f"{assessment.site} substation (voltage sections: "
        f"{', '.join(places_at(assessment.lookups.conn, assessment.site))}). Its claims:\n"
        f"{shown}\n\nA person asks: {request!r}\n\nIf they want something left out of "
        "the assessment, call propose_adjustment. Otherwise look things up and submit new "
        "claims with submit_assessment, with ids not used above."
    )
    outcome = _run(
        model,
        assessment.lookups,
        brief,
        tools=[*LOOKUP_TOOLS, SUBMIT_ASSESSMENT, PROPOSE_ADJUSTMENT],
        limits=limits or Limits(),
        model_id=model_id,
        existing=assessment.claims,
        site=assessment.site,
    )
    if outcome.proposal is not None:
        return Answer(proposal=outcome.proposal)
    parsed = outcome.parsed or Parsed()
    assessment.claims.extend(parsed.claims)
    assessment.rejected.extend(parsed.rejected)
    assessment.log("the agent", f"answered: {request}")
    return Answer(tuple(parsed.claims), tuple(parsed.rejected))


@dataclass
class _Conversation:
    model: Model
    budget: AssessmentBudget
    model_id: str
    tools: list[dict[str, Any]]
    messages: list[dict[str, Any]]

    def next(self) -> BetaMessage:
        self.budget.before_call()
        response = self.model.create(
            model=self.model_id,
            max_tokens=self.budget.limits.max_output_tokens_per_call,
            system=SKILL.read_text(),
            tools=self.tools,
            messages=self.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
        )
        self.budget.record(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or "",
        )
        if response.stop_reason == "refusal":
            raise AgentStopped("The model declined to write this assessment.")
        # Sent back unchanged, thinking included, as the API requires.
        self.messages.append({"role": "assistant", "content": response.content})
        return response


@dataclass(frozen=True)
class _Outcome:
    parsed: Parsed | None = None
    proposal: ProposedAdjustment | None = None


def _run(
    model: Model,
    lookups: Lookups,
    brief: str,
    *,
    tools: list[dict[str, Any]],
    limits: Limits,
    model_id: str,
    existing: Sequence[Claim] = (),
    site: str | None = None,
) -> _Outcome:
    talk = _Conversation(
        model,
        AssessmentBudget(limits),
        model_id,
        tools,
        [{"role": "user", "content": brief}],
    )
    submissions = 0
    while True:
        response = talk.next()
        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            talk.messages.append(
                {"role": "user", "content": "Submit your claims with submit_assessment."}
            )
            continue
        results, final = [], None
        for block in calls:
            arguments = block.input if isinstance(block.input, dict) else {}
            if block.name == SUBMIT_ASSESSMENT["name"]:
                submissions += 1
                parsed = checked(arguments.get("claims"), lookups, existing)
                problems = problems_in(parsed)
                if problems and submissions < SUBMISSIONS:
                    results.append(_result(block.id, _sent_back(problems), error=True))
                else:
                    final = _Outcome(parsed=parsed)
                    results.append(_result(block.id, "Accepted."))
                continue
            if block.name == PROPOSE_ADJUSTMENT["name"] and site is not None:
                try:
                    final = _Outcome(proposal=_proposal(lookups, site, arguments))
                    results.append(_result(block.id, "Proposed; a person will confirm it."))
                except ValueError as e:
                    results.append(_result(block.id, str(e), error=True))
                continue
            try:
                results.append(
                    _result(block.id, lookups.run(block.name, arguments).for_the_model())
                )
            except LookupRefused as e:
                results.append(_result(block.id, str(e), error=True))
        talk.messages.append({"role": "user", "content": results})
        if final is not None:
            return final


def _proposal(lookups: Lookups, site: str, arguments: dict[str, Any]) -> ProposedAdjustment:
    """Turn what the model proposed into the exact projects it would leave out, found in
    SQL, so a person confirms a list rather than a description."""
    why = str(arguments.get("why") or "").strip()
    if not why:
        raise ValueError("Give the reason (why).")
    ids, said = set(), []
    named = arguments.get("projects") or []
    if named:
        found = lookups.conn.execute(
            "SELECT native_id FROM caiso_projects WHERE native_id = ANY(%s)",
            ([str(n) for n in named],),
        ).fetchall()
        unknown = {str(n) for n in named} - {str(r[0]) for r in found}
        if unknown:
            raise ValueError(f"No CAISO project called {sorted(unknown)}.")
        ids |= {str(n) for n in named}
        said.append(f"the projects {', '.join(sorted(ids))}")
    year = arguments.get("waiting_since_year")
    if year is not None:
        if isinstance(year, bool) or not isinstance(year, int):
            raise ValueError("waiting_since_year must be a year, such as 2019.")
        stuck = [
            str(r[0])
            for r in lookups.conn.execute(
                "SELECT p.native_id FROM caiso_projects p WHERE p.status = 'Active' "
                "AND extract(year FROM p.q_date) <= %s AND EXISTS (SELECT 1 FROM "
                "project_places pp WHERE pp.source = p.source AND pp.native_id = p.native_id "
                "AND pp.place = ANY(%s)) ORDER BY 1",
                (year, places_at(lookups.conn, site)),
            ).fetchall()
        ]
        if not stuck:
            raise ValueError(f"No project at {site} has been waiting since {year} or earlier.")
        ids |= set(stuck)
        said.append(
            f"the {len(stuck)} projects at {site} still waiting that joined the queue in "
            f"{year} or earlier ({', '.join(stuck)})"
        )
    if not ids:
        raise ValueError("Name the projects, or give waiting_since_year.")
    return ProposedAdjustment(
        Adjustment(frozenset(ids), why), f"Leave out {' and '.join(said)}. Reason: {why}"
    )


def checked(items: Any, lookups: Lookups, existing: Sequence[Claim] = ()) -> Parsed:
    """Parse what was submitted, then check every Factual Claim. A Judgement stating a
    number its claims don't is rejected: no number appears unless code checked it.
    ``existing`` are claims already in the assessment, which new ones may build on."""
    if not isinstance(items, list):
        return Parsed(rejected=[Rejected(items, "claims must be a list")])
    parsed = parse_claims(items, existing)
    claims: list[Claim] = []
    for claim in parsed.claims:
        if isinstance(claim, FactualClaim):
            claims.append(replace(claim, check=check(claim, lookups)))
            continue
        cited = [
            lookups.log[v.tool_call_id]
            for c in [*existing, *parsed.claims]
            if isinstance(c, FactualClaim) and c.id in claim.based_on
            for v in c.values
            if v.tool_call_id in lookups.log
        ]
        stray = unchecked_numbers(claim.text, cited)
        if stray:
            parsed.rejected.append(
                Rejected(claim, f"{claim.id}: a Judgement states numbers: {stray}")
            )
        else:
            claims.append(claim)
    return Parsed(claims, parsed.rejected)


def problems_in(parsed: Parsed) -> list[str]:
    return [r.reason for r in parsed.rejected] + [
        p
        for c in parsed.claims
        if isinstance(c, FactualClaim) and c.check is not None
        for p in c.check.problems
    ]


def _sent_back(problems: list[str]) -> str:
    return (
        "Some claims were rejected. Fix them or leave them out, and submit all your claims "
        "again:\n- " + "\n- ".join(problems)
    )


def _result(tool_use_id: str, content: str, *, error: bool = False) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": error,
    }
