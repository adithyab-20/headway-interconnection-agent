"""The chance of reaching operation within N years, worked out from past projects.

Each past project either was built, withdrew, or is still waiting. A waiting project is only
known to be waiting for the years it has been watched, so it counts for those years and
then leaves the count: never as a success, never as a failure. This is the Aalen-Johansen
estimate (decision #26): walk forward through time and, at each moment a project is built
or withdraws, take the share of the projects still being watched that it represents.

It pools every year projects joined into one estimate. ADR 0002's per-year rates exist
because a single rate over all years ignores the projects still waiting; this estimate counts
them for the years they were watched instead, which is why decision #26 chose it.
"""

from __future__ import annotations

import bisect
import math
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

# Shares that are equal on paper can differ in the last bits after a long product.
_ROUNDING = 1e-12


class Outcome(StrEnum):
    BUILT = "built"
    WITHDRAWN = "withdrawn"
    WAITING = "waiting"


@dataclass(frozen=True)
class PastProject:
    """One past project, as the calculation uses it.

    ``years`` runs from the day it joined the queue to the day it was built or withdrew, or,
    if it's still waiting, to the day the data was taken.
    """

    source: str  # the dataset the row came from (always "caiso_raw" so far, decision #38)
    native_id: str
    years: float
    outcome: Outcome
    # The outcome date was estimated by the load (the operator's file has none).
    date_estimated: bool = False


class NotEnoughHistory(ValueError):
    """Asked for a figure further out than any project in the group has been watched."""


@dataclass(frozen=True)
class Chance:
    within_years: float
    chance: float
    # The likely range: 95% of the estimates from the group redrawn at random (a bootstrap).
    likely_range: tuple[float, float]
    # Projects watched for at least the N years: built or withdrew after N, or still waiting
    # and joined at least N years before the data was taken. The figure rests on these.
    watched_to_n_years: int
    # When half of the projects that get built (as far as the history goes) have been built.
    # None when none were built.
    typical_wait_years: float | None
    typical_wait_range: tuple[float, float] | None
    projects: int
    built: int
    withdrawn: int
    waiting: int
    rows: tuple[PastProject, ...]  # every project the figures were worked out from


# How many times the group is redrawn for the likely range, and the fixed seed that makes the
# range reproducible: a checked number has to come out the same every time.
RESAMPLES = 400
SEED = 2026


@dataclass(frozen=True)
class _Step:
    years: float
    built: float  # chance of having been built by then
    still_waiting: float  # chance of being neither built nor withdrawn by then


class _Ordered:
    """The group sorted by years watched, once, so it can be redrawn cheaply."""

    def __init__(self, group: Sequence[PastProject]) -> None:
        self.projects = sorted(group, key=lambda p: p.years)
        # Each run of projects watched for the same years, as (start, end) indexes.
        self.runs: list[tuple[int, int]] = []
        for i, p in enumerate(self.projects):
            if self.runs and self.projects[self.runs[-1][0]].years == p.years:
                self.runs[-1] = (self.runs[-1][0], i + 1)
            else:
                self.runs.append((i, i + 1))

    def curve(self, copies: Sequence[int] | None = None) -> list[_Step]:
        """The estimate at every moment a project was built or withdrew. ``copies`` says how
        many times each project is counted (a redrawn group); by default, once each."""
        weight = copies or [1] * len(self.projects)
        steps: list[_Step] = []
        built, still_waiting = 0.0, 1.0
        watched = sum(weight)
        for start, end in self.runs:
            n_built = n_withdrawn = n_all = 0
            for i in range(start, end):
                n_all += weight[i]
                if self.projects[i].outcome is Outcome.BUILT:
                    n_built += weight[i]
                elif self.projects[i].outcome is Outcome.WITHDRAWN:
                    n_withdrawn += weight[i]
            if n_built or n_withdrawn:
                built += still_waiting * n_built / watched
                still_waiting *= 1 - (n_built + n_withdrawn) / watched
                steps.append(_Step(self.projects[start].years, built, still_waiting))
            watched -= n_all
        return steps

    def redrawn(self, rng: random.Random) -> list[int]:
        copies = [0] * len(self.projects)
        for i in rng.choices(range(len(self.projects)), k=len(self.projects)):
            copies[i] += 1
        return copies


def _built_by(steps: list[_Step], years: float) -> float:
    built = 0.0
    for step in steps:
        if step.years > years:
            break
        built = step.built
    return built


def _typical_wait(steps: list[_Step]) -> float | None:
    eventually = steps[-1].built if steps else 0.0
    if not eventually:
        return None
    return next(step.years for step in steps if step.built >= eventually / 2 - _ROUNDING)


def middle_95(values: Sequence[float]) -> tuple[float, float]:
    """The range holding the middle 95% of the values."""
    ordered = sorted(values)
    return ordered[int(0.025 * (len(ordered) - 1))], ordered[round(0.975 * (len(ordered) - 1))]


def chance_of_reaching_operation(group: Sequence[PastProject], within_years: float) -> Chance:
    """The chance that a project like these is built within ``within_years`` of joining, and
    the typical wait, each with its likely range.

    Raises :class:`NotEnoughHistory` if no project in the group has been watched that long.
    """
    watched = sum(p.years >= within_years for p in group)
    if not watched:
        longest = max((p.years for p in group), default=0.0)
        raise NotEnoughHistory(
            f"No figure for {within_years:g} years: the longest any of these {len(group)} "
            f"projects has been watched is {longest:.1f} years."
        )
    ordered = _Ordered(group)
    steps = ordered.curve()
    rng = random.Random(SEED)
    chances, waits = [], []
    for _ in range(RESAMPLES):
        redrawn = ordered.curve(ordered.redrawn(rng))
        chances.append(_built_by(redrawn, within_years))
        wait = _typical_wait(redrawn)
        if wait is not None:
            waits.append(wait)
    typical_wait = _typical_wait(steps)
    count = Counter(p.outcome for p in group)
    return Chance(
        within_years=within_years,
        chance=_built_by(steps, within_years),
        likely_range=middle_95(chances),
        watched_to_n_years=watched,
        typical_wait_years=typical_wait,
        typical_wait_range=middle_95(waits) if typical_wait is not None and waits else None,
        projects=len(group),
        built=count[Outcome.BUILT],
        withdrawn=count[Outcome.WITHDRAWN],
        waiting=count[Outcome.WAITING],
        rows=tuple(sorted(group, key=lambda p: p.native_id)),
    )


class ChanceGivenWait:
    """A group's estimate, worked out once, then read for any time a project has waited.

    Only the projects still waiting after that long count: those built or withdrawn sooner
    say nothing about a project that is still here. Read off the whole group's curve, this is
    the share built from then on divided by the share still waiting then.
    """

    def __init__(self, group: Sequence[PastProject]) -> None:
        self._size = len(group)
        self._watched = sorted(p.years for p in group)
        self._ordered = _Ordered(group)
        self._curve = _Curve(self._ordered.curve())

    def redrawn(self, rng: random.Random) -> _Curve:
        """The estimate from the group redrawn at random, for a likely range."""
        return _Curve(self._ordered.curve(self._ordered.redrawn(rng)))

    def after(self, waited_years: float, within_more_years: float | None = None) -> float:
        """The chance of being built within ``within_more_years`` more or, by default, at any
        point the history covers. Raises :class:`NotEnoughHistory` if nobody in the group has
        been watched that long."""
        until = math.inf if within_more_years is None else waited_years + within_more_years
        if bisect.bisect_left(self._watched, min(until, waited_years)) == self._size or (
            until < math.inf and bisect.bisect_left(self._watched, until) == self._size
        ):
            raise NotEnoughHistory(
                f"No figure for a project that has waited {waited_years:.1f} years"
                + (f", {within_more_years:g} years on" if within_more_years is not None else "")
                + f": the longest any of these {self._size} projects has been watched is "
                f"{self._watched[-1] if self._watched else 0.0:.1f} years."
            )
        return self._curve.after(waited_years, until)


class _Curve:
    def __init__(self, steps: list[_Step]) -> None:
        self._steps = steps
        self._step_years = [step.years for step in steps]

    def after(self, waited_years: float, until: float = math.inf) -> float:
        """The share built after ``waited_years`` and by ``until``, over the share still
        waiting at ``waited_years``. Zero if nobody was still waiting then."""
        before = bisect.bisect_left(self._step_years, waited_years)
        built_then, waiting_then = (
            (self._steps[before - 1].built, self._steps[before - 1].still_waiting)
            if before
            else (0.0, 1.0)
        )
        if waiting_then <= 0:
            return 0.0
        by = bisect.bisect_right(self._step_years, until)
        built_by = self._steps[by - 1].built if by else 0.0
        return min(1.0, max(0.0, (built_by - built_then) / waiting_then))


def chance_of_still_being_built(
    group: Sequence[PastProject], waited_years: float, within_more_years: float | None = None
) -> float:
    """The chance that a project which has already waited ``waited_years`` is built, within
    ``within_more_years`` more or, by default, at any point the history covers. See
    :class:`ChanceGivenWait`, which is quicker for many projects against one group."""
    return ChanceGivenWait(group).after(waited_years, within_more_years)
