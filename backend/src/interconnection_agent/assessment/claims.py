"""Claims: the only two things an assessment is made of.

A **Factual Claim** is a sentence with a numbered slot (``{0}``, ``{1}``, ...) for each of its
numbers. Each number says which lookup it came from and how it was worked out, so code can
check it (ADR 0003). The sentence is never parsed: the shown text is the sentence with the
checked numbers filled in by code.

A **Judgement** interprets the numbers. Code can't check it, so a person decides on it. It
carries no numbers of its own.

``parse_claims`` turns what the model submitted into claims, and turns anything that is
neither kind, or malformed, into a :class:`Rejected` item with the reason.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


@dataclass(frozen=True)
class Value:
    """One number in a Factual Claim, as the model stated it."""

    value: float
    # As the model wrote them, not yet trusted: the checker says if they're on the fixed lists.
    unit: str
    derivation: str
    of: str  # the figure quoted, or the column of the rows (or "projects", to count them)
    source: str
    tool_call_id: str
    # The rows it was worked out from. Quoting a figure, these may be left out: the figure's
    # own rows are then attached from the log.
    source_row_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Check:
    """The checker's verdict on one Factual Claim."""

    problems: tuple[str, ...]
    # Per value, in order: the number the data gives and the rows it comes from. Empty for a
    # value that couldn't be worked out.
    worked_out: tuple[float | None, ...] = ()
    rows: tuple[frozenset[str], ...] = ()

    @property
    def passed(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class FactualClaim:
    id: str
    text: str
    values: tuple[Value, ...]
    check: Check | None = None  # None until it has been checked

    kind = "factual"


class Decision(StrEnum):
    AWAITING = "awaiting decision"
    APPROVED = "approved"
    REJECTED = "rejected"
    REWRITTEN = "rewritten"


@dataclass(frozen=True)
class Judgement:
    id: str
    text: str
    based_on: tuple[str, ...] = ()  # the Factual Claims it interprets
    decision: Decision = Decision.AWAITING
    decided_by: str | None = None

    kind = "judgement"


Claim = FactualClaim | Judgement


@dataclass(frozen=True)
class Rejected:
    """Something submitted that isn't a usable claim, and why."""

    item: Any
    reason: str


@dataclass
class Parsed:
    claims: list[Claim] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)


NOT_EITHER_KIND = "is neither a Factual Claim nor a Judgement"


def parse_claims(items: Sequence[Any], existing: Sequence[Claim] = ()) -> Parsed:
    """Claims from what was submitted. ``existing`` claims are already in the assessment:
    new ones can't reuse their ids, and a new Judgement may rest on them."""
    parsed = Parsed()
    seen: set[str] = {c.id for c in existing}
    for item in items:
        try:
            claim = _parse(item)
        except ClaimError as e:
            parsed.rejected.append(Rejected(item, str(e)))
            continue
        if claim.id in seen:
            parsed.rejected.append(Rejected(item, f"{claim.id}: the id is used twice"))
            continue
        seen.add(claim.id)
        parsed.claims.append(claim)
    factual = {c.id for c in [*existing, *parsed.claims] if isinstance(c, FactualClaim)}
    for claim in list(parsed.claims):
        if isinstance(claim, Judgement):
            unknown = [i for i in claim.based_on if i not in factual]
            if unknown:
                parsed.claims.remove(claim)
                parsed.rejected.append(
                    Rejected(claim, f"{claim.id}: based on {unknown}, which aren't Factual Claims")
                )
    return parsed


class ClaimError(ValueError):
    pass


def _parse(item: Any) -> Claim:
    if not isinstance(item, dict):
        raise ClaimError(f"{item!r} {NOT_EITHER_KIND}")
    name = item.get("id")
    label = name if isinstance(name, str) and name else repr(item.get("text", item))[:60]
    kind = item.get("kind")
    if kind not in ("factual", "judgement"):
        raise ClaimError(f"{label} (kind {kind!r}) {NOT_EITHER_KIND}")
    if not isinstance(name, str) or not name:
        raise ClaimError(f"{label}: every claim needs an id")
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ClaimError(f"{name}: every claim needs its text")
    if kind == "judgement":
        if item.get("values"):
            raise ClaimError(
                f"{name}: a Judgement can't carry numbers to check; make them a Factual Claim "
                "and base the Judgement on it"
            )
        based_on = item.get("based_on", [])
        if not isinstance(based_on, list) or not all(isinstance(i, str) for i in based_on):
            raise ClaimError(f"{name}: based_on must be a list of claim ids")
        return Judgement(name, text, tuple(based_on))
    values = item.get("values")
    if not isinstance(values, list) or not values:
        raise ClaimError(f"{name}: a Factual Claim needs at least one number")
    return FactualClaim(name, text, tuple(_value(name, v) for v in values))


def _value(name: str, v: Any) -> Value:
    if not isinstance(v, dict):
        raise ClaimError(f"{name}: each number must be an object")
    number = v.get("value")
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        raise ClaimError(f"{name}: {number!r} isn't a number")
    texts = {}
    for key in ("unit", "derivation", "of", "source", "tool_call_id"):
        if not isinstance(v.get(key), str):
            raise ClaimError(f"{name}: each number needs {key}")
        texts[key] = v[key]
    rows = v.get("source_row_ids")
    if rows is not None and (
        not isinstance(rows, list) or not all(isinstance(r, str) for r in rows)
    ):
        raise ClaimError(f"{name}: source_row_ids must be a list of row ids")
    return Value(
        value=float(number),
        source_row_ids=tuple(rows) if rows is not None else None,
        **texts,
    )
