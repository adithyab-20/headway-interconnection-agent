"""Chances, waits, and who's ahead, worked out from the real CAISO files in ``data/``.

Expected values come from outside the code under test: the research notes behind decisions
#26 and #38 (measured with separate scripts on the same files), or the spreadsheets.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import openpyxl
import psycopg
import pytest

from interconnection_agent.chances import (
    NotEnoughHistory,
    Outcome,
    ProjectType,
    backtest,
    odds_for,
    realistic_mw_ahead,
)
from interconnection_agent.db import connect
from interconnection_agent.load import load_all
from interconnection_agent.poi import normalize_station

Conn = psycopg.Connection[tuple[object, ...]]
DATA = Path(__file__).resolve().parents[2] / "data"
PLACES = Path(__file__).resolve().parents[2] / "src/interconnection_agent/places"


@pytest.fixture(scope="module")
def conn() -> Iterator[Conn]:
    """Load everything once for this module; roll it all back afterwards."""
    with connect() as c:
        c.autocommit = False
        try:
            load_all(DATA, c)
            yield c
        finally:
            c.rollback()


def test_across_all_of_california_the_chances_match_the_research_measurement(conn: Conn) -> None:
    # Research note for #38: CAISO's own file, undated outcomes kept with an estimated date,
    # the 2023 batch left out: 12.4% by year 10 and 15.3% by year 15.
    by_10 = odds_for(conn, within_years=10)
    by_15 = odds_for(conn, within_years=15)

    assert by_10.used.description == "All projects, across California"
    # Every figure says which rules its history comes from (decision #39).
    assert by_10.history_from == (
        "projects that applied before the 2023 rule change (CAISO queue report of 2026-07-24)"
    )
    assert by_10.chance.chance == pytest.approx(0.124, abs=0.002)
    assert by_15.chance.chance == pytest.approx(0.153, abs=0.002)
    # Its bootstrap range around the baseline was 10.4%-13.7%.
    low, high = by_10.chance.likely_range
    assert low == pytest.approx(0.104, abs=0.01) and high == pytest.approx(0.137, abs=0.01)
    # 2,278 projects in the main report: 249 built, 1,759 withdrawn, 270 waiting.
    assert (by_10.chance.built, by_10.chance.withdrawn, by_10.chance.waiting) == (249, 1759, 270)


def test_it_uses_the_most_specific_group_and_place_with_enough_history_and_says_which(
    conn: Conn,
) -> None:
    # A 20 MW solar project at Smyrna 115 kV (Tulare County). Counts of small solar projects
    # (under 50 MW) that reached an outcome, worked out from the files: 11 at Smyrna (5
    # built), then behind each bottleneck Smyrna sits behind, narrowest first: 12 (5 built),
    # 15 (7), 23 (9), 24 (10), 28 (11), and 77 (20) behind Mustang-Henrietta, the first with
    # enough (at least 30, of which at least 10 built).
    odds = odds_for(
        conn, project_type=ProjectType.SOLAR, mw=20, place="Smyrna 115 kV", within_years=5
    )

    assert odds.used.description == (
        "Solar only, under 50 MW, behind the Mustang-Henrietta 230 kV line bottleneck"
    )
    tried = odds.ladder[: odds.ladder.index(odds.used)]
    assert [(level.resolved, level.built) for level in tried] == [
        (11, 5), (11, 5), (12, 5), (15, 7), (23, 9), (24, 10), (28, 11),
    ]  # fmt: skip
    assert not any(level.enough for level in tried) and odds.used.enough
    # The narrower and broader choices stay on offer, out to all projects in California.
    assert odds.ladder[0].description == "Solar only, under 50 MW, at Smyrna 115 kV"
    assert [level.description for level in odds.ladder[-3:]] == [
        "Solar only, under 50 MW, across California",
        "Solar only, across California",
        "All projects, across California",
    ]
    assert odds.chance.projects == odds.used.projects

    # A narrower group can still be chosen. Its figure comes from its own projects, and it
    # stays marked as too few to rely on.
    smyrna = odds_for(
        conn,
        project_type=ProjectType.SOLAR,
        mw=20,
        place="Smyrna 115 kV",
        within_years=5,
        use=odds.ladder[0],
    )
    assert smyrna.used == odds.ladder[0] and not smyrna.used.enough
    assert {row.native_id for row in smyrna.chance.rows} == odds.ladder[0].native_ids

    # A 200 MW battery: 97 batteries of 150-300 MW reached an outcome but only 6 were built,
    # so size is dropped. Batteries of any size have enough.
    battery = odds_for(conn, project_type=ProjectType.BATTERY, mw=200, within_years=10)
    assert battery.used.description == "Battery only, across California"


def test_it_widens_the_place_to_reach_further_out_but_never_changes_the_project_type(
    conn: Conn,
) -> None:
    # No small solar project behind Mustang-Henrietta has been watched for 10 years, so a
    # 10-year figure comes from a wider area that has watched one that long.
    odds = odds_for(
        conn, project_type=ProjectType.SOLAR, mw=20, place="Smyrna 115 kV", within_years=10
    )
    narrower = odds.ladder[: odds.ladder.index(odds.used)]
    mustang = next(level for level in narrower if "Mustang-Henrietta" in level.description)
    assert mustang.enough and mustang.longest_watched_years < 10
    assert odds.used.project_type is ProjectType.SOLAR and odds.used.longest_watched_years >= 10
    assert odds.chance.watched_to_n_years > 0

    # No standalone battery has been watched for 15 years (research note for #38). Rather
    # than answer with some other kind of project, it refuses.
    with pytest.raises(NotEnoughHistory, match="15 years"):
        odds_for(conn, project_type=ProjectType.BATTERY, within_years=15)


def test_every_figure_comes_with_the_exact_rows_it_was_worked_out_from(conn: Conn) -> None:
    odds = odds_for(conn, project_type=ProjectType.WIND, within_years=10)
    rows = {row.native_id: row for row in odds.chance.rows}

    # Exactly the projects in the group it used: no more, no fewer, each naming its dataset.
    assert set(rows) == odds.used.native_ids
    assert {row.source for row in rows.values()} == {"caiso_raw"}
    assert len(rows) == odds.chance.projects

    # Montezuma (queue 22), wind + battery, isn't a wind-only project.
    assert "CAISO-0022" not in rows
    everything = {row.native_id: row for row in odds_for(conn, within_years=10).chance.rows}
    # It joined on 2003-11-18 and is still waiting on the report's run date, 2026-07-24.
    montezuma = everything["CAISO-0022"]
    assert montezuma.outcome is Outcome.WAITING
    assert montezuma.years == pytest.approx((date(2026, 7, 24) - date(2003, 11, 18)).days / 365.25)
    # Red Bluff (queue 146) was built but has no online date: its row says the date is
    # estimated.
    assert everything["CAISO-0146"].outcome is Outcome.BUILT
    assert everything["CAISO-0146"].date_estimated
    # The 2023 batch, under the new rules, is never part of the history.
    assert "CAISO-2244" not in everything


def _waiting_in_the_files(site: str, kv: int) -> dict[str, tuple[float, str]]:
    """Projects waiting at a voltage section, read straight from the two reports through the
    reviewed spelling table: queue id -> (MW to grid, "main" or "2023 batch")."""
    with (PLACES / "spellings.csv").open(newline="") as f:
        here = {
            r["poi_key"]
            for r in csv.DictReader(f)
            if site in (r["site"], r["other_end_site"]) and r["voltage_kv"] == str(kv)
        }
    found: dict[str, tuple[float, str]] = {}
    main = openpyxl.load_workbook(DATA / "publicqueuereport.xlsx", read_only=True)
    rows = list(main["Grid GenerationQueue"].iter_rows(min_row=4, values_only=True))
    header = [" ".join(str(c).split()) if c else "" for c in rows[0]]
    queue, mw = header.index("Queue Position"), header.index("Net MWs to Grid")
    poi = header.index("Station or Transmission Line")
    for r in rows[1:]:
        if r[queue] is not None and normalize_station(str(r[poi])) in here:
            q = r[queue]
            found[f"CAISO-{q:04d}" if isinstance(q, int) else f"CAISO-{q}"] = (
                float(str(r[mw])),
                "main",
            )
    batch = openpyxl.load_workbook(
        DATA / "cluster-15-interconnection-requests.xlsx", read_only=True
    )
    rows = list(batch["Cluster 15 "].iter_rows(values_only=True))
    queue, mw, poi = (rows[0].index(h) for h in ("Queue Number", "NET MW POI", "POI"))
    for r in rows[1:]:
        if r[queue] is not None and normalize_station(str(r[poi])) in here:
            found[f"CAISO-{int(str(r[queue])):04d}"] = (float(str(r[mw])), "2023 batch")
    return found


def test_realistic_mw_ahead_counts_each_waiting_project_by_its_chance_given_its_wait(
    conn: Conn,
) -> None:
    ahead = realistic_mw_ahead(conn, place="Whirlwind 230 kV")

    # The projects and MW waiting there under the old rules, as the main report lists them.
    in_the_files = {
        queue: mw for queue, (mw, report) in _waiting_in_the_files("Whirlwind", 230).items()
        if report == "main"
    }  # fmt: skip
    assert {p.native_id: p.mw_to_grid for p in ahead.projects} == in_the_files
    assert ahead.waiting_mw == pytest.approx(sum(in_the_files.values()))
    # Each counts only by its chance of still being built, so the total is well below,
    # and it comes with its likely range.
    assert 0 < ahead.realistic_mw < ahead.waiting_mw
    low, high = ahead.likely_range
    assert low <= ahead.realistic_mw <= high and low < high
    assert ahead.left_out == ()  # every waiting project here states its MW and queue date
    assert all(p.chance_still_built is not None for p in ahead.projects)
    assert all(0 <= (p.chance_still_built or 0) <= 1 for p in ahead.projects)

    # Montezuma (queue 22, 38 MW at Birds Landing) has waited since 2003, longer than any
    # CAISO project has waited and still been built (15.8 years at most, research note for
    # #38): it counts for nothing.
    birds_landing = realistic_mw_ahead(conn, place="Birds Landing 230 kV")
    montezuma = next(p for p in birds_landing.projects if p.native_id == "CAISO-0022")
    assert montezuma.waited_years > 22 and montezuma.chance_still_built == 0


def test_a_project_on_a_line_counts_at_both_ends_but_never_twice_in_one_number(
    conn: Conn,
) -> None:
    # Queue 61 (73.27 MW to grid in the main report) connects partway along the Helm-Kerman
    # 70 kV line: it counts in full at each end.
    at_helm = {p.native_id: p for p in realistic_mw_ahead(conn, place="Helm 70 kV").projects}
    at_kerman = {p.native_id: p for p in realistic_mw_ahead(conn, place="Kerman 70 kV").projects}
    assert at_helm["CAISO-0061"] == at_kerman["CAISO-0061"]
    assert at_helm["CAISO-0061"].on_a_line and at_helm["CAISO-0061"].mw_to_grid == 73.27

    # Queue 900 is on the Midway-Temblor 115 kV line. Behind a bottleneck that both ends sit
    # behind, it is still one project.
    (bottleneck,) = conn.execute(
        "SELECT bottleneck FROM place_bottlenecks WHERE place IN ('Midway 115 kV', "
        "'Temblor 115 kV') GROUP BY 1 HAVING count(DISTINCT place) = 2 ORDER BY 1 LIMIT 1"
    ).fetchone() or (None,)
    area = realistic_mw_ahead(conn, bottleneck=str(bottleneck))
    ids = [p.native_id for p in area.projects]
    assert ids.count("CAISO-0900") == 1 and len(ids) == len(set(ids))
    assert area.waiting_mw == pytest.approx(sum(p.mw_to_grid for p in area.projects))


def test_the_2023_batch_is_shown_beside_realistic_mw_ahead_never_weighted_or_added_in(
    conn: Conn,
) -> None:
    ahead = realistic_mw_ahead(conn, place="Whirlwind 230 kV")

    # Three 2023-batch projects wait at Whirlwind 230 kV, per that batch's own report.
    batch = {
        queue: mw for queue, (mw, report) in _waiting_in_the_files("Whirlwind", 230).items()
        if report == "2023 batch"
    }  # fmt: skip
    assert len(batch) == 3
    assert {p.native_id: p.mw_to_grid for p in ahead.new_rules_projects} == batch
    assert ahead.new_rules_mw == pytest.approx(sum(batch.values()))
    assert all(p.chance_still_built is None for p in ahead.new_rules_projects)
    assert not set(batch) & {p.native_id for p in ahead.projects}


def test_realistic_mw_ahead_reproduces_from_its_rows(conn: Conn) -> None:
    ahead = realistic_mw_ahead(conn, site="Whirlwind")

    assert ahead.realistic_mw == pytest.approx(
        sum(p.mw_to_grid * (p.chance_still_built or 0) for p in ahead.projects)
    )
    assert {p.source for p in ahead.projects} == {"caiso_raw"}
    for p in ahead.projects:
        # Each chance names the past projects it was worked out from, which include this
        # project itself (watched for as long as it has waited), and has enough history.
        assert p.compared_with is not None and p.compared_with.enough
        assert p.native_id in p.compared_with.native_ids


# The accepted calibration (decisions #26, #30). Measured when the backtest was written
# (October 2026, report of 2026-07-24): calibration error 0.055, expected 20.5% built against
# 18.2% actually built, Brier score 0.142. A change that makes any of these worse than the
# levels below fails the build; loosen them only with a written reason.
ACCEPTED_CALIBRATION_ERROR = 0.06
ACCEPTED_SHARE_GAP = 0.03
ACCEPTED_BRIER_SCORE = 0.145


def test_predictions_from_past_cutoffs_stay_as_close_to_what_happened_as_accepted(
    conn: Conn,
) -> None:
    result = backtest(conn)

    # A cut-off every 1 January from 2010 to 2021: each looks 5 years on, and all of those
    # 5 years had passed by the report's run date (2026-07-24).
    assert [c.year for c in result.cutoffs] == list(range(2010, 2022))
    assert result.within_years == 5
    print(result.summary())

    # It never peeks: every prediction is for a project that had joined before the cut-off
    # and had neither been built nor withdrawn by then.
    dates = {
        str(native_id): (joined, ended)
        for native_id, joined, ended in conn.execute(
            "SELECT native_id, q_date, outcome_date FROM caiso_projects"
        ).fetchall()
    }
    for p in result.predictions:
        joined, ended = dates[p.native_id]
        assert isinstance(joined, date) and joined <= p.cutoff
        assert ended is None or (isinstance(ended, date) and ended > p.cutoff)

    # When it says 20%, about 20% were built: the gap between predicted and actual share,
    # averaged over bands of prediction weighted by how many fall in each.
    assert result.calibration_error <= ACCEPTED_CALIBRATION_ERROR
    # Overall, the share it expected to be built against the share that was.
    assert abs(result.predicted_share - result.actual_share) <= ACCEPTED_SHARE_GAP
    assert result.brier_score <= ACCEPTED_BRIER_SCORE
    # And it does better than always guessing the share that was built.
    assert result.brier_score < result.no_skill_brier_score
