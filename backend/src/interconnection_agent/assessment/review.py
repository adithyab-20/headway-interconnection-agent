"""An assessment: checked claims a person can review.

What is shown is built from the claims, never the other way round: a Factual Claim appears
only if it passed the check, with the numbers the data gives filled into its slots; a
Judgement always appears as a Judgement, never as checked.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field, replace

from interconnection_agent.assessment.check import SLOT, check, work_out
from interconnection_agent.assessment.claims import (
    Check,
    Claim,
    Decision,
    FactualClaim,
    Judgement,
    Rejected,
    Value,
)
from interconnection_agent.assessment.lookups import Derivation, Lookup, LookupRefused, Lookups
from interconnection_agent.budget import AssessmentBudget, Limits
from interconnection_agent.chances import ProjectType


@dataclass(frozen=True)
class Project:
    """The proposed project an assessment is about."""

    project_type: ProjectType | None = None
    mw: float | None = None  # MW to grid

    def describe(self) -> str:
        kind = str(self.project_type) if self.project_type else "Any type of"
        return f"{kind} project" + (f" of {self.mw:g} MW" if self.mw is not None else "")


@dataclass(frozen=True)
class Change:
    """One entry in an assessment's log: who did what, when, and why."""

    when: datetime.datetime
    who: str
    what: str
    why: str = ""


@dataclass(frozen=True)
class Adjustment:
    """A change to what goes into an assessment, and why: projects left out, or a narrower
    or broader comparison group. The numbers are then worked out again and checked again;
    they are never typed over."""

    why: str
    leave_out: frozenset[str] = frozenset()
    comparison_group: str | None = None  # one the assessment's chance lookups offer


@dataclass(frozen=True)
class ProposedAdjustment:
    """An Adjustment the agent proposes from a person's request. It does nothing until a
    person confirms it with ``Assessment.adjust``."""

    adjustment: Adjustment
    description: str  # in plain words, naming every project it would leave out


@dataclass(frozen=True)
class Answer:
    """The agent's answer to one request. Its claims are checked, but held: they join the
    assessment only when a person adds them (``Assessment.add``)."""

    id: str
    request: str
    claims: tuple[Claim, ...] = ()
    rejected: tuple[Rejected, ...] = ()
    proposal: ProposedAdjustment | None = None
    # The data can't answer the request: why, in plain words.
    cant_answer: str | None = None


class NotReady(ValueError):
    """Asked to finalise while a Judgement is still waiting for a decision."""


class AssessmentIsFinal(ValueError):
    """Asked to change an assessment that has been finalised."""


@dataclass
class Assessment:
    site: str
    project: Project
    lookups: Lookups
    claims: list[Claim]
    # Submitted items that weren't usable claims, and why. Never shown.
    rejected: list[Rejected] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    final: bool = False
    # Answers to requests, by id, whose claims a person hasn't added yet, or whose proposed
    # Adjustment they haven't confirmed.
    held: dict[str, Answer] = field(default_factory=dict)
    answers_given: int = 0
    # Every model call for this assessment, writing it and answering questions about it,
    # counts against one set of limits.
    budget: AssessmentBudget = field(default_factory=lambda: AssessmentBudget(Limits()))

    @property
    def factual_claims(self) -> list[FactualClaim]:
        return [c for c in self.claims if isinstance(c, FactualClaim)]

    @property
    def judgements(self) -> list[Judgement]:
        return [c for c in self.claims if isinstance(c, Judgement)]

    def text(self) -> str:
        """The assessment as a reader sees it."""
        lines = [f"{self.project.describe()} at {self.site}", ""]
        for claim in self.claims:
            if isinstance(claim, FactualClaim):
                if claim.check is not None and claim.check.passed:
                    lines.append(f"- {filled_in(claim)} [checked]")
            elif claim.decision is not Decision.REJECTED:
                lines.append(f"- {claim.text} [Judgement, not checked by code: {claim.decision}]")
        return "\n".join(lines)

    def log(self, who: str, what: str, why: str = "") -> None:
        self.changes.append(Change(datetime.datetime.now(datetime.UTC), who, what, why))

    @property
    def held_claims(self) -> list[Claim]:
        return [c for answer in self.held.values() for c in answer.claims]

    def next_answer_id(self) -> str:
        self.answers_given += 1
        return f"answer-{self.answers_given}"

    def hold(self, answer: Answer) -> Answer:
        """Keep an answer's claims, or its proposal, aside until a person acts on it."""
        if answer.claims or answer.proposal:
            self.held[answer.id] = answer
        return answer

    # --- what a person can do ---

    def add(self, answer_id: str, *, by: str) -> None:
        """Add a held answer's claims to the assessment. Its Judgements wait for a decision
        like any other."""
        self.still_open()
        if not (answer_id in self.held and self.held[answer_id].claims):
            raise KeyError(f"No answer called {answer_id!r} is waiting to be added.")
        answer = self.held.pop(answer_id)
        self.claims.extend(answer.claims)
        added = ", ".join(c.id for c in answer.claims)
        self.log(by, f"added {added} from the answer to: {answer.request}")

    def confirm(self, answer_id: str, *, by: str) -> None:
        """Make the Adjustment an answer proposed."""
        proposal = self.held[answer_id].proposal if answer_id in self.held else None
        if proposal is None:
            raise KeyError(f"No proposed change called {answer_id!r} is waiting.")
        self.adjust(proposal.adjustment, by=by)
        del self.held[answer_id]

    def adjust(self, adjustment: Adjustment, *, by: str) -> None:
        """Leave projects out, then work out every number again and check it again. A
        Judgement resting on a number that changed goes back to awaiting a decision. A claim
        the checker rejected stays rejected: working its numbers out again would only make
        them right, not the claim."""
        self.still_open()
        if adjustment.comparison_group is not None:
            self.lookups.compare_with(adjustment.comparison_group)  # before anything changes
        self.lookups.leave(adjustment.leave_out)
        rerun: dict[str, Lookup | str] = {}
        changed: list[str] = []
        moved: set[str] = set()
        self.claims = self._redone(self.claims, rerun, changed, moved)
        for answer_id, answer in self.held.items():
            claims = self._redone(list(answer.claims), rerun, [], moved)
            self.held[answer_id] = replace(answer, claims=tuple(claims))
        for i, claim in enumerate(self.claims):
            if (
                isinstance(claim, Judgement)
                and claim.decision is not Decision.AWAITING
                and moved & set(claim.based_on)
            ):
                self.claims[i] = replace(claim, decision=Decision.AWAITING, decided_by=None)
                changed.append(f"{claim.id}: back to awaiting a decision")
        made = (
            [f"left out {', '.join(sorted(adjustment.leave_out))}"] if adjustment.leave_out else []
        ) + (
            [f"compared with {adjustment.comparison_group}"] if adjustment.comparison_group else []
        )
        self.log(
            by,
            "; ".join(made + (changed or ["no number changed"])),
            adjustment.why,
        )

    def decide(self, judgement_id: str, decision: Decision, *, by: str, why: str = "") -> None:
        """Approve or reject a Judgement."""
        if decision not in (Decision.APPROVED, Decision.REJECTED):
            raise ValueError("A Judgement is approved or rejected; to change it, rewrite it.")
        self.still_open()
        i, judgement = self._judgement(judgement_id)
        self.claims[i] = replace(judgement, decision=decision, decided_by=by)
        self.log(by, f"{decision} {judgement_id}", why)

    def rewrite(self, judgement_id: str, text: str, *, by: str, why: str = "") -> None:
        """Replace a Judgement's text with a person's own. It counts as decided."""
        self.still_open()
        i, judgement = self._judgement(judgement_id)
        self.claims[i] = replace(judgement, text=text, decision=Decision.REWRITTEN, decided_by=by)
        self.log(by, f"rewrote {judgement_id}: {judgement.text!r} -> {text!r}", why)

    def finalise(self, *, by: str) -> None:
        """Mark the assessment final. Only once every Judgement is decided."""
        self.still_open()
        waiting = [j.id for j in self.judgements if j.decision is Decision.AWAITING]
        if waiting:
            raise NotReady(f"Every Judgement needs a decision first: {', '.join(waiting)}.")
        self.final = True
        self.log(by, "finalised the assessment")

    def still_open(self) -> None:
        if self.final:
            raise AssessmentIsFinal("This assessment is final and can't be changed.")

    def _redone(
        self,
        claims: list[Claim],
        rerun: dict[str, Lookup | str],
        changed: list[str],
        moved: set[str],
    ) -> list[Claim]:
        """Every Factual Claim that passed, worked out again and checked again. Notes in
        ``changed`` what moved or now fails, and adds the ids whose numbers moved to
        ``moved``."""
        redone_claims: list[Claim] = []
        for claim in claims:
            if not isinstance(claim, FactualClaim) or claim.check is None or not claim.check.passed:
                redone_claims.append(claim)
                continue
            values = tuple(self._recalculated(v, rerun) for v in claim.values)
            redone = replace(claim, values=values, check=None)
            redone = replace(redone, check=check(redone, self.lookups))
            redone_claims.append(redone)
            before, after = _numbers(claim.check), _numbers(redone.check)
            if before != after:
                moved.add(claim.id)
                changed.append(f"{claim.id}: {_listed(before)} -> {_listed(after)}")
            if redone.check is not None and not redone.check.passed:
                changed.append(f"{claim.id}: now rejected ({'; '.join(redone.check.problems)})")
        return redone_claims

    def _judgement(self, judgement_id: str) -> tuple[int, Judgement]:
        for i, claim in enumerate(self.claims):
            if isinstance(claim, Judgement) and claim.id == judgement_id:
                return i, claim
        raise KeyError(f"No Judgement called {judgement_id!r}.")

    def _recalculated(self, v: Value, rerun: dict[str, Lookup | str]) -> Value:
        """The value worked out again from its lookup, run again with the projects now
        left out. A value whose lookup can't be run again is left as it was, and fails."""
        if v.tool_call_id not in rerun:
            old = self.lookups.log.get(v.tool_call_id)
            if old is None:
                return v
            try:
                rerun[v.tool_call_id] = self.lookups.run(old.tool, old.arguments)
            except LookupRefused as e:
                rerun[v.tool_call_id] = str(e)
        new = rerun[v.tool_call_id]
        if isinstance(new, str):
            return v
        rows = v.source_row_ids
        if rows is not None and v.of in new.figures:
            rows = tuple(sorted(new.figures[v.of].rows))
        elif rows is not None and v.derivation != Derivation.DIRECT:
            rows = tuple(sorted(new.row_ids))
        redone = replace(v, tool_call_id=new.tool_call_id, source_row_ids=rows)
        found, _, _ = work_out(replace(redone, value=0), self.lookups)
        return replace(redone, value=found) if found is not None else redone


def _numbers(result: Check | None) -> tuple[float | None, ...]:
    return result.worked_out if result is not None else ()


def _listed(numbers: tuple[float | None, ...]) -> str:
    return "(" + ", ".join("-" if n is None else f"{n:,.4g}" for n in numbers) + ")"


def filled_in(claim: FactualClaim) -> str:
    """The sentence with each slot filled with the number the data gives, and its unit."""
    assert claim.check is not None and claim.check.passed
    numbers = claim.check.worked_out

    def fill(slot: re.Match[str]) -> str:
        i = int(slot.group(1))
        found = numbers[i]
        assert found is not None
        return shown(found, claim.values[i].unit)

    return SLOT.sub(fill, claim.text)


def shown(number: float, unit: str) -> str:
    if unit == "projects":
        return f"{number:,.0f} project" + ("" if number == 1 else "s")
    if unit == "%":
        return f"{number:.1f}%" if 0 < number < 1 else f"{number:.0f}%"
    if unit == "years":
        return f"{number:.1f} years"
    return f"{number:,.0f} {unit}" if abs(number) >= 10 else f"{number:,.1f} {unit}"
