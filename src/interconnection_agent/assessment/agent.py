"""The agent: the model looks things up and writes claims; code checks them.

The model's only way to state anything is a claim submitted through a tool. It never
writes the text a reader sees. Every model call goes through the assessment's spending
limits (``interconnection_agent.budget``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from anthropic.types.beta import BetaMessage

from interconnection_agent.assessment.check import MARGINS, SOURCES, checked, problems_in
from interconnection_agent.assessment.claims import Claim, Parsed, Rejected
from interconnection_agent.assessment.lookups import Derivation, LookupRefused, Lookups, places_at
from interconnection_agent.assessment.review import Adjustment, Assessment, Project
from interconnection_agent.budget import AssessmentBudget, Limits
from interconnection_agent.chances import ProjectType
from interconnection_agent.chances.groups import Conn, data_as_of
from interconnection_agent.settings import Settings

SKILL = Path(__file__).resolve().parents[1] / "skills/writing-an-assessment/SKILL.md"
MODEL = "claude-opus-5-5"
# A submission with rejected claims is sent back once to be fixed; the next is final.
MOST_SUBMISSIONS = 2


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
        "unit": {"type": "string", "enum": list(MARGINS)},
        "derivation": {"type": "string", "enum": [d.value for d in Derivation]},
        "of": {"type": "string"},
        "source": {"type": "string", "enum": list(SOURCES)},
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
    "description": "Propose a change to what goes into the assessment, when a person asks "
    "for one. Nothing changes until a person confirms. Leave projects out by id, or with "
    "waiting_since_year (projects still waiting at this substation that joined the queue "
    "in that year or earlier); or compare with another comparison_group, by its "
    "description from chance_of_being_built.",
    "input_schema": {
        "type": "object",
        "properties": {
            "projects": {"type": "array", "items": {"type": "string"}},
            "waiting_since_year": {"type": "integer"},
            "comparison_group": {"type": "string"},
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
) -> Assessment:
    """Have the model write an assessment for ``project`` at ``site``, checked claim by
    claim. Raises a :class:`~interconnection_agent.budget.BudgetExceeded` if it goes over
    its limits, and :class:`AgentStopped` if it ends without submitting."""
    lookups = Lookups(conn)
    brief = (
        f"Write an assessment for a {project.describe()} connecting at the {site} "
        f"substation. Its voltage sections: {', '.join(places_at(conn, site=site))}. "
        f"The data was taken on {data_as_of(conn).isoformat()}. Look things up, then submit "
        "with submit_assessment."
    )
    budget = AssessmentBudget(limits or Limits())
    outcome = _run(model, budget, lookups, brief, tools=[*LOOKUP_TOOLS, SUBMIT_ASSESSMENT])
    parsed = outcome.parsed or Parsed()
    assessment = Assessment(site, project, lookups, parsed.claims, parsed.rejected, budget=budget)
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


def ask(assessment: Assessment, model: Model, request: str) -> Answer:
    """Answer a person's plain request about an assessment: with new checked claims, which
    are added to it, or with a proposed Adjustment, which isn't applied. Its model calls
    count against the assessment's own spending limits."""
    assessment.still_open()
    shown = "\n".join(f"- {c.id}: {c.text}" for c in assessment.claims)
    brief = (
        f"This is an assessment for a {assessment.project.describe()} connecting at the "
        f"{assessment.site} substation (voltage sections: "
        f"{', '.join(places_at(assessment.lookups.conn, site=assessment.site))}). Its claims:\n"
        f"{shown}\n\nA person asks: {request!r}\n\nIf they want something left out of "
        "the assessment, call propose_adjustment. Otherwise look things up and submit new "
        "claims with submit_assessment, with ids not used above."
    )
    outcome = _run(
        model,
        assessment.budget,
        assessment.lookups,
        brief,
        tools=[*LOOKUP_TOOLS, SUBMIT_ASSESSMENT, PROPOSE_ADJUSTMENT],
        existing=assessment.claims,
        site=assessment.site,
    )
    if outcome.proposal is not None:
        assessment.log("the agent", f"proposed: {outcome.proposal.description}", request)
        return Answer(proposal=outcome.proposal)
    parsed = outcome.parsed or Parsed()
    assessment.claims.extend(parsed.claims)
    assessment.rejected.extend(parsed.rejected)
    added = ", ".join(c.id for c in parsed.claims) or "nothing"
    assessment.log("the agent", f"answered: {request}", f"added {added}")
    return Answer(tuple(parsed.claims), tuple(parsed.rejected))


@dataclass
class _Conversation:
    model: Model
    budget: AssessmentBudget
    tools: list[dict[str, Any]]
    messages: list[dict[str, Any]]

    def next(self) -> BetaMessage:
        self.budget.before_call()
        response = self.model.create(
            model=MODEL,
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
class _Finished:
    parsed: Parsed | None = None
    proposal: ProposedAdjustment | None = None


def _run(
    model: Model,
    budget: AssessmentBudget,
    lookups: Lookups,
    brief: str,
    *,
    tools: list[dict[str, Any]],
    existing: Sequence[Claim] = (),
    site: str | None = None,
) -> _Finished:
    conversation = _Conversation(model, budget, tools, [{"role": "user", "content": brief}])
    submissions = 0
    while True:
        response = conversation.next()
        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            conversation.messages.append(
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
                if problems and submissions < MOST_SUBMISSIONS:
                    results.append(_result(block.id, _sent_back(problems), error=True))
                else:
                    final = _Finished(parsed=parsed)
                    results.append(_result(block.id, "Accepted."))
                continue
            if block.name == PROPOSE_ADJUSTMENT["name"] and site is not None:
                try:
                    final = _Finished(proposal=_proposal(lookups, site, arguments))
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
        conversation.messages.append({"role": "user", "content": results})
        if final is not None:
            return final


def _proposal(lookups: Lookups, site: str, arguments: dict[str, Any]) -> ProposedAdjustment:
    """Turn what the model proposed into exactly what would change: the projects it would
    leave out, found in SQL, and a comparison group the assessment offers. A person
    confirms that, rather than a description."""
    why = str(arguments.get("why") or "").strip()
    if not why:
        raise ValueError("Give the reason (why).")
    ids, said = set(), []
    named = {str(n) for n in arguments.get("projects") or []}
    if named:
        unknown = named - lookups.rows_in("caiso_raw", named)
        if unknown:
            raise ValueError(f"No CAISO project called {sorted(unknown)}.")
        ids |= named
        said.append(f"leave out the projects {', '.join(sorted(named))}")
    year = arguments.get("waiting_since_year")
    if year is not None:
        if isinstance(year, bool) or not isinstance(year, int):
            raise ValueError("waiting_since_year must be a year, such as 2019.")
        stuck = lookups.waiting_since(site, year)
        if not stuck:
            raise ValueError(f"No project at {site} has been waiting since {year} or earlier.")
        ids |= set(stuck)
        said.append(
            f"leave out the {len(stuck)} projects at {site} still waiting that joined the "
            f"queue in {year} or earlier ({', '.join(stuck)})"
        )
    group = arguments.get("comparison_group")
    if group is not None:
        if str(group) not in lookups.comparison_groups():
            lookups.compare_with(str(group))  # raises, naming the groups on offer
        said.append(f"compare with {group}")
    if not said:
        raise ValueError("Name the projects, give waiting_since_year, or a comparison_group.")
    adjustment = Adjustment(
        why, leave_out=frozenset(ids), comparison_group=str(group) if group else None
    )
    plan = "; ".join(said)
    return ProposedAdjustment(adjustment, f"{plan[0].upper()}{plan[1:]}. Reason: {why}")


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
