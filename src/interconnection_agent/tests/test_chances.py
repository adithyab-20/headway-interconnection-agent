"""The chance of being built within N years, and the typical wait, for a comparison group.

Each example is a handful of past projects, small enough to work the answer out by hand.
A project's ``years`` is how long it was watched: until it was built or withdrew, or, if it's
still waiting, until the data was taken.
"""

import pytest

from interconnection_agent.chances import (
    NotEnoughHistory,
    Outcome,
    PastProject,
    chance_of_reaching_operation,
    chance_of_still_being_built,
    outcomes_by_year,
)

BUILT, WITHDRAWN, WAITING = Outcome.BUILT, Outcome.WITHDRAWN, Outcome.WAITING


def project(name: str, years: float, outcome: Outcome) -> PastProject:
    return PastProject(source="caiso_raw", native_id=name, years=years, outcome=outcome)


def test_a_project_still_waiting_counts_for_the_years_it_was_watched_never_as_a_failure() -> None:
    group = [
        project("A", 1, BUILT),
        project("B", 2, WAITING),  # joined two years before the data was taken
        project("C", 3, BUILT),
        project("D", 5, WAITING),
    ]

    # Year 1: A of the 4 watched is built (1/4). B leaves the count at year 2 without an
    # outcome. Year 3: C is built, one of the 2 still watched, so another 3/4 x 1/2.
    # 1/4 + 3/8 = 5/8. Counting B as a failure would give 2/4; dropping it, 2/3.
    result = chance_of_reaching_operation(group, within_years=4)

    assert result.chance == pytest.approx(5 / 8)


def test_it_refuses_a_figure_beyond_the_years_any_project_has_been_watched() -> None:
    group = [project("A", 1, BUILT), project("B", 2, WITHDRAWN), project("C", 5, WAITING)]

    # C has been watched for 5 years, so a 5-year figure rests on it...
    assert chance_of_reaching_operation(group, within_years=5).watched_to_n_years == 1
    # ...but nobody has been watched for 6.
    with pytest.raises(NotEnoughHistory, match=r"6 years.*longest.*5\.0 years"):
        chance_of_reaching_operation(group, within_years=6)


def test_the_typical_wait_is_when_half_of_those_that_get_built_have_been_built() -> None:
    group = [project(f"built {n}", n, BUILT) for n in (1, 2, 3, 4)] + [
        project("waiting", 6, WAITING)
    ]

    # 4 of the 5 are built, at years 1 to 4; half of those 4 are built by year 2.
    result = chance_of_reaching_operation(group, within_years=6)

    assert result.chance == pytest.approx(4 / 5)
    assert result.typical_wait_years == 2


def test_with_nothing_built_there_is_no_typical_wait() -> None:
    group = [project("A", 1, WITHDRAWN), project("B", 3, WAITING)]

    result = chance_of_reaching_operation(group, within_years=2)

    assert result.chance == 0
    assert result.typical_wait_years is None


def _mixed_group(copies: int = 1) -> list[PastProject]:
    """3 built, 5 withdrawn and 2 waiting, repeated ``copies`` times."""
    shape = [
        (1, BUILT), (2, BUILT), (4, BUILT),
        (1, WITHDRAWN), (1.5, WITHDRAWN), (2, WITHDRAWN), (3, WITHDRAWN), (5, WITHDRAWN),
        (3, WAITING), (7, WAITING),
    ]  # fmt: skip
    return [
        project(f"{copy}-{i}", years, outcome)
        for copy in range(copies)
        for i, (years, outcome) in enumerate(shape)
    ]


def test_every_figure_comes_with_its_likely_range_its_project_counts_and_its_rows() -> None:
    group = _mixed_group()

    result = chance_of_reaching_operation(group, within_years=6)

    assert (result.projects, result.built, result.withdrawn, result.waiting) == (10, 3, 5, 2)
    assert result.rows == tuple(sorted(group, key=lambda p: p.native_id))
    low, high = result.likely_range
    assert low <= result.chance <= high and low < high
    assert result.typical_wait_years is not None and result.typical_wait_range is not None
    wait_low, wait_high = result.typical_wait_range
    assert wait_low <= result.typical_wait_years <= wait_high
    # Worked out again, it's the same range: a checked number has to reproduce.
    assert chance_of_reaching_operation(group, within_years=6).likely_range == (low, high)


def test_the_same_history_from_more_projects_gives_a_narrower_range() -> None:
    few = chance_of_reaching_operation(_mixed_group(), within_years=6)
    many = chance_of_reaching_operation(_mixed_group(copies=10), within_years=6)

    assert many.chance == pytest.approx(few.chance)
    (few_low, few_high), (many_low, many_high) = few.likely_range, many.likely_range
    assert many_high - many_low < (few_high - few_low) / 2


def test_a_project_that_has_already_waited_is_judged_only_against_those_that_waited_as_long() -> (
    None
):
    group = [
        project("A", 1, BUILT),
        project("B", 2, WITHDRAWN),
        project("C", 3, BUILT),
        project("D", 5, WAITING),
    ]

    # After 1.5 years, A is out of the picture: of B, C and D, B withdraws (2 of 3 left) and
    # then C is built, one of the 2 still watched: 2/3 x 1/2 = 1/3.
    assert chance_of_still_being_built(group, waited_years=1.5) == pytest.approx(1 / 3)
    # Within one more year only B's withdrawal has happened.
    assert chance_of_still_being_built(group, waited_years=1.5, within_more_years=1) == 0
    # Nobody has been watched for 1.5 + 4 years.
    with pytest.raises(NotEnoughHistory):
        chance_of_still_being_built(group, waited_years=1.5, within_more_years=4)


def test_year_by_year_it_gives_the_share_built_withdrawn_and_still_waiting() -> None:
    group = [
        project("A", 1, BUILT),
        project("B", 2, WITHDRAWN),
        project("C", 3, WAITING),
        project("D", 4, BUILT),
    ]

    # Year 1: A is 1 of the 4 watched, built: 1/4 built, 3/4 waiting. Year 2: B withdraws, 1
    # of the 3 watched: 3/4 x 1/3 = 1/4 withdrawn, 1/2 waiting. C leaves the count at year 3
    # with no outcome. Year 4: D is the only one watched, built: another 1/2 built.
    years = outcomes_by_year(group, [0, 2, 4])

    assert [y.years for y in years] == [0, 2, 4]
    assert [(y.built, y.withdrawn, y.still_waiting) for y in years] == [
        pytest.approx((0, 0, 1)),
        pytest.approx((1 / 4, 1 / 4, 1 / 2)),
        pytest.approx((3 / 4, 1 / 4, 0)),
    ]
    assert all(y.built_range[0] <= y.built <= y.built_range[1] for y in years)
    # Past the longest any project was watched, there's nothing to say.
    with pytest.raises(NotEnoughHistory):
        outcomes_by_year(group, [5])
