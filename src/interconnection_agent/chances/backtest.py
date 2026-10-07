"""The backtest: predictions made from past cut-off days, compared with what happened.

On each cut-off day (1 January of a past year) the history is replayed as it stood then:
only projects that had joined, only outcomes that had happened. Every project waiting on
that day gets the chance of being built within the next N years, given how long it had
waited, the way realistic MW ahead weights it. Then the files say whether it was.

Calibration is what's reported, not accuracy (decision #26): most projects withdraw, so a
model that always says "won't be built" would look accurate and be useless. Calibration asks
whether, of the projects given about 20%, about 20% were built.

What it checks is the chance of being built within the next five years given the wait so
far. Projects that had joined less than a year before a cut-off stand in for the chance from
the day a project joins. Two things the product shows can't be checked this way:

  * the chance "at any point the history covers" that realistic MW ahead uses, because the
    years after the last cut-off haven't happened yet;
  * size and place, which narrow the live comparison groups. Both are recorded as of today
    (projects resize, connection points move), so using them would let the future leak into
    the past. Only the project type narrows the group here.

The replay leans on two small leaks it can't avoid: project types as recorded today, and the
51 estimated outcome dates, which were estimated from the whole history.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from interconnection_agent.chances.estimate import ChanceGivenWait, NotEnoughHistory, Outcome
from interconnection_agent.chances.groups import (
    SOURCE,
    ComparisonGroup,
    Conn,
    comparison_ladder,
    data_as_of,
    history,
    members,
    usable_groups,
)

WITHIN_YEARS = 5
FIRST_CUTOFF_YEAR = 2010
# Bands of predicted chance the calibration is measured over.
BANDS = ((0.0, 0.05), (0.05, 0.1), (0.1, 0.2), (0.2, 0.35), (0.35, 0.5), (0.5, 1.0))


@dataclass(frozen=True)
class Prediction:
    source: str
    native_id: str
    cutoff: datetime.date
    waited_years: float
    chance: float
    compared_with: str  # the comparison group, as of the cut-off
    built: bool  # built within the N years after the cut-off


@dataclass(frozen=True)
class Band:
    low: float
    high: float
    predictions: int
    predicted_share: float  # average chance given
    actual_share: float  # share actually built


@dataclass(frozen=True)
class Backtest:
    within_years: float
    cutoffs: tuple[datetime.date, ...]
    predictions: tuple[Prediction, ...]
    # Waiting projects no group of their type could give a figure for, as of the cut-off.
    no_figure: tuple[tuple[str, datetime.date], ...]
    bands: tuple[Band, ...]
    calibration_error: float  # gap between predicted and actual share, averaged over bands
    predicted_share: float
    actual_share: float
    brier_score: float  # average squared gap between chance given and outcome (0 or 1)
    # The same, for always giving the share actually built: the score of knowing nothing.
    no_skill_brier_score: float

    def summary(self) -> str:
        lines = [
            f"{len(self.predictions)} predictions from {len(self.cutoffs)} cut-offs "
            f"({self.cutoffs[0].year}-{self.cutoffs[-1].year}), {self.within_years:g} years on; "
            f"{len(self.no_figure)} with no figure",
            f"expected built {self.predicted_share:.1%}, actually built {self.actual_share:.1%}",
            f"calibration error {self.calibration_error:.3f}, Brier score {self.brier_score:.4f} "
            f"(knowing nothing: {self.no_skill_brier_score:.4f})",
        ]
        lines += [
            f"  {b.low:.0%}-{b.high:.0%}: {b.predictions} predictions, "
            f"expected {b.predicted_share:.1%}, built {b.actual_share:.1%}"
            for b in self.bands
        ]
        return "\n".join(lines)


def backtest(conn: Conn, within_years: float = WITHIN_YEARS) -> Backtest:
    """Predict from every cut-off whose N years have passed by the day the data was taken."""
    taken = data_as_of(conn)
    cutoffs = []
    year = FIRST_CUTOFF_YEAR
    while _years_on(datetime.date(year, 1, 1), within_years) <= taken:
        cutoffs.append(datetime.date(year, 1, 1))
        year += 1

    predictions: list[Prediction] = []
    no_figure: list[tuple[str, datetime.date]] = []
    for cutoff in cutoffs:
        built_by_then = {
            str(r[0])
            for r in conn.execute(
                "SELECT native_id FROM caiso_projects WHERE status = 'Operational' "
                "AND batch IS DISTINCT FROM 'C15' AND outcome_date <= %s",
                (_years_on(cutoff, within_years),),
            ).fetchall()
        }
        known_then = history(conn, as_of=cutoff)
        estimates: dict[ComparisonGroup, ChanceGivenWait] = {}
        for record in known_then:
            if record.past.outcome is not Outcome.WAITING:
                continue
            ladder = comparison_ladder(known_then, conn, record.project_type, None, None)
            for group in usable_groups(ladder):
                if group not in estimates:
                    estimates[group] = ChanceGivenWait(members(known_then, group))
                try:
                    chance = estimates[group].after(record.past.years, within_years)
                except NotEnoughHistory:
                    continue
                predictions.append(
                    Prediction(
                        SOURCE,
                        record.past.native_id,
                        cutoff,
                        record.past.years,
                        chance,
                        group.description,
                        record.past.native_id in built_by_then,
                    )
                )
                break
            else:
                no_figure.append((record.past.native_id, cutoff))

    return _score(within_years, tuple(cutoffs), tuple(predictions), tuple(no_figure))


def _years_on(day: datetime.date, years: float) -> datetime.date:
    return day.replace(year=day.year + int(years))


def _score(
    within_years: float,
    cutoffs: tuple[datetime.date, ...],
    predictions: tuple[Prediction, ...],
    no_figure: tuple[tuple[str, datetime.date], ...],
) -> Backtest:
    n = len(predictions)
    actual = sum(p.built for p in predictions) / n
    bands = []
    for low, high in BANDS:
        inside = [p for p in predictions if low <= p.chance < high or (high == 1.0 == p.chance)]
        if inside:
            bands.append(
                Band(
                    low,
                    high,
                    len(inside),
                    sum(p.chance for p in inside) / len(inside),
                    sum(p.built for p in inside) / len(inside),
                )
            )
    return Backtest(
        within_years=within_years,
        cutoffs=cutoffs,
        predictions=predictions,
        no_figure=no_figure,
        bands=tuple(bands),
        calibration_error=sum(
            b.predictions * abs(b.predicted_share - b.actual_share) for b in bands
        )
        / n,
        predicted_share=sum(p.chance for p in predictions) / n,
        actual_share=actual,
        brier_score=sum((p.chance - p.built) ** 2 for p in predictions) / n,
        no_skill_brier_score=actual * (1 - actual),
    )
