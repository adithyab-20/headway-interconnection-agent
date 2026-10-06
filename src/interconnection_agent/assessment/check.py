"""The number checker: code, no model, the same answer every time (ADR 0003).

For every number in a Factual Claim it confirms:

* the lookup it names is in the log, and the number names the same dataset as the lookup;
* the derivation is one of the fixed list, and is how that figure or column is worked out;
* it uses exactly the rows the lookup returned (a ``direct`` quote: one of them), so citing
  some of them, or rows the lookup never returned, fails even when the arithmetic is right;
* every cited row is a row of that dataset;
* the number reproduces within the margin written down for its unit (``MARGINS``): counts,
  sums, middles and single values of the operator's own columns are worked out again from
  the database; figures and columns a tested function worked out are compared with what the
  function returned, not recalculated (ADR 0003). The middle of a column is the exception
  that proves the rule: ADR 0003 compares medians rather than redo them because a claim
  would have to cite hundreds of rows; a project list is short and its rows are cited
  anyway, so redoing it costs nothing;
* every number in the sentence is in a slot, so nothing unchecked can be shown. Names the
  lookups used or returned ("Whirlwind 230 kV", "the 2023 batch") may contain digits.

What it can't prove is that the lookup was the right one. See ADR 0003.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from typing import Any

from interconnection_agent.assessment.claims import (
    Check,
    Claim,
    FactualClaim,
    Parsed,
    Rejected,
    Value,
    parse_claims,
)
from interconnection_agent.assessment.lookups import COLUMNS, VIEWS, Derivation, Lookup, Lookups

SOURCES = tuple(VIEWS)
# How close a stated number must be to the number the data gives, per unit. Written down
# here so "close enough" is a rule, not a feeling (ADR 0003).
MARGINS: dict[str, Callable[[float, float], bool]] = {
    # To the nearest 10, or within 5%.
    "MW": lambda stated, data: abs(stated - data) <= max(5.0, 0.05 * abs(data)) + 1e-9,
    # To one decimal place.
    "years": lambda stated, data: abs(stated - data) <= 0.05 + 1e-9,
    # To the whole point.
    "%": lambda stated, data: abs(stated - data) <= 0.5 + 1e-9,
    # Exactly.
    "projects": lambda stated, data: stated == data,
}
DERIVATIONS = frozenset(d.value for d in Derivation)
SLOT = re.compile(r"\{(\d+)\}")


def check(claim: FactualClaim, lookups: Lookups) -> Check:
    problems: list[str] = []
    worked_out: list[float | None] = []
    rows: list[frozenset[str]] = []
    for i, value in enumerate(claim.values):
        said = f"{claim.id}, number {{{i}}}"
        found, value_rows, value_problems = work_out(value, lookups)
        problems += [f"{said}: {p}" for p in value_problems]
        worked_out.append(found)
        rows.append(value_rows)
    problems += [f"{claim.id}: {p}" for p in _text_problems(claim, lookups.log)]
    return Check(tuple(problems), tuple(worked_out), tuple(rows))


def work_out(v: Value, lookups: Lookups) -> tuple[float | None, frozenset[str], list[str]]:
    """The number the data gives for one value, the rows behind it, and what's wrong with
    the value as stated (nothing, if it passes)."""
    if v.derivation not in DERIVATIONS:
        return (
            None,
            frozenset(),
            [f"derivation {v.derivation!r} isn't one of {sorted(DERIVATIONS)}"],
        )
    if v.source not in SOURCES:
        return None, frozenset(), [f"source {v.source!r} isn't one of {list(SOURCES)}"]
    lookup = lookups.log.get(v.tool_call_id)
    if lookup is None:
        return None, frozenset(), [f"lookup {v.tool_call_id!r} isn't in the log"]
    if v.source != lookup.source:
        return (
            None,
            frozenset(),
            [f"names {v.source} but lookup {lookup.tool_call_id} read {lookup.source}"],
        )
    if v.of in lookup.figures:
        return _check_figure(v, lookup)
    if v.of == "projects" or v.of in COLUMNS:
        return _check_rows(v, lookup, lookups)
    return (
        None,
        frozenset(),
        [f"lookup {lookup.tool_call_id} has no figure or column called {v.of!r}"],
    )


def _check_figure(v: Value, lookup: Lookup) -> tuple[float | None, frozenset[str], list[str]]:
    figure = lookup.figures[v.of]
    problems = []
    if v.unit != figure.unit:
        problems.append(f"unit {v.unit!r}, but {v.of} is in {figure.unit}")
    if v.derivation != figure.derivation:
        problems.append(f"says {v.derivation}, but {v.of} is a {figure.derivation.value}")
    if v.source_row_ids is not None:
        problems += _same_rows(set(v.source_row_ids), figure.rows, lookup)
    problems += _within(v, figure.value)
    return figure.value, figure.rows, problems


def _check_rows(
    v: Value, lookup: Lookup, lookups: Lookups
) -> tuple[float | None, frozenset[str], list[str]]:
    if not v.source_row_ids:
        if (
            lookup.tool != "list_projects"
            or lookup.rows
            or v.of != "projects"
            or v.derivation != Derivation.COUNT
        ):
            return None, frozenset(), ["cites no rows"]
        # "None are waiting": a count of nothing, from a lookup that returned nothing.
        return 0.0, frozenset(), _within(v, 0)
    cited = set(v.source_row_ids)
    if v.derivation == Derivation.DIRECT:
        if len(cited) != 1:
            return None, frozenset(), [f"a direct quote cites one row, not {len(cited)}"]
        problems = (
            []
            if cited <= lookup.row_ids
            else [f"row {next(iter(cited))} isn't one lookup {lookup.tool_call_id} returned"]
        )
    else:
        problems = _same_rows(cited, lookup.row_ids, lookup)
    unknown = cited - lookups.rows_in(v.source, cited)
    if unknown:
        problems.append(f"{sorted(unknown)} aren't {v.source} rows")
    if problems:
        return None, frozenset(), problems

    if v.of == "projects":
        if v.derivation != Derivation.COUNT or v.unit != "projects":
            return None, frozenset(), ["projects can only be counted, in projects"]
        return float(len(cited)), frozenset(cited), _within(v, len(cited))

    column = COLUMNS[v.of]
    if v.unit != column.unit:
        return None, frozenset(), [f"unit {v.unit!r}, but {v.of} is in {column.unit}"]
    if v.derivation not in (Derivation.DIRECT, Derivation.SUM, Derivation.MEDIAN):
        return (
            None,
            frozenset(),
            [f"{v.derivation} of {v.of} isn't worked out by this lookup; quote a figure"],
        )
    if column.from_the_data:
        data = lookups.column_in(v.source, v.of, cited)
    else:
        data = {str(r["native_id"]): r.get(v.of) for r in lookup.rows if r["native_id"] in cited}
    numbers = [float(x) for x in data.values() if isinstance(x, (int, float))]
    if v.derivation == Derivation.DIRECT:
        if not numbers:
            return None, frozenset(), [f"{next(iter(cited))} has no {v.of}"]
        found = numbers[0]
    elif v.derivation == Derivation.SUM:
        found = sum(numbers)
    else:
        if not numbers:
            return None, frozenset(), [f"none of these rows has a {v.of}"]
        found = statistics.median(numbers)
    return found, frozenset(cited), _within(v, found)


def _same_rows(cited: set[str], returned: frozenset[str], lookup: Lookup) -> list[str]:
    if cited == returned:
        return []
    problems = []
    missing, extra = returned - cited, cited - returned
    if missing:
        problems.append(
            f"uses {len(cited & returned)} of the {len(returned)} rows lookup "
            f"{lookup.tool_call_id} returned (leaves out {_some(missing)})"
        )
    if extra:
        problems.append(f"cites rows lookup {lookup.tool_call_id} didn't return: {_some(extra)}")
    return problems


def _within(v: Value, data: float) -> list[str]:
    margin = MARGINS.get(v.unit)
    if margin is None:
        return [f"unit {v.unit!r} has no written margin; use one of {sorted(MARGINS)}"]
    if margin(v.value, data):
        return []
    return [f"says {v.value:g} {v.unit}, the data gives {data:.4g} {v.unit}"]


def _text_problems(claim: FactualClaim, log: dict[str, Lookup]) -> list[str]:
    slots = {int(n) for n in SLOT.findall(claim.text)}
    wanted = set(range(len(claim.values)))
    problems = []
    if slots - wanted:
        problems.append(f"slots {sorted(slots - wanted)} have no number")
    if wanted - slots:
        problems.append(f"numbers {sorted(wanted - slots)} have no slot in the text")
    cited = [log[v.tool_call_id] for v in claim.values if v.tool_call_id in log]
    stray = unchecked_numbers(SLOT.sub("", claim.text), cited)
    if stray:
        problems.append(f"states numbers that aren't checked: {stray}")
    return problems


def unchecked_numbers(text: str, lookups: Iterable[Lookup]) -> list[str]:
    """Numbers in ``text`` that aren't part of a name or description the lookups used, or of
    a number they were asked for, with its unit ("10 years"). Numbers written as words
    ("half", "twice") can't be caught this way; the writing skill rules them out."""
    labels = {x for lookup in lookups for x in lookup.labels} | set(NAMES)
    for label in sorted(labels, key=len, reverse=True):
        text = text.replace(label, " ")
    return NUMBER.findall(text)


NUMBER = re.compile(r"\d[\d,.]*")
# Names in the data that contain digits, which any claim may use.
NAMES = ("2023 batch", "2023 rule change")


def _some(ids: Iterable[str]) -> str:
    ordered = sorted(ids)
    return ", ".join(ordered[:5]) + (f" and {len(ordered) - 5} more" if len(ordered) > 5 else "")


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
