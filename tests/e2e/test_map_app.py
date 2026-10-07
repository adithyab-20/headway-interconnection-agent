"""The map app: the three behaviours of ticket "The map app", in a real browser.

Everything runs for real: the website (``web/``), the API and the database, loaded with
``load_all`` beforehand. The one stand-in is the model, scripted below, so
writing and asking need no API key. Expected values come from hand-written SQL, or, for the
estimates themselves, from the tested functions in ``interconnection_agent.chances``.

Needs the data loaded (``load_all``), ``npm install`` in ``web/`` and Playwright's Chromium
(``uv run playwright install chromium``); skipped otherwise.
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
import uvicorn
from anthropic.types.beta import BetaMessage
from playwright.sync_api import Browser, Page, expect, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from interconnection_agent.api import create_app
from interconnection_agent.chances import ProjectType, odds_for, realistic_mw_ahead
from interconnection_agent.db import connect

Conn = psycopg.Connection[tuple[object, ...]]
ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
API_PORT, WEB_PORT = 8765, 3765
SLOW = 90_000  # ms: the first map load works out every substation's figures


def _loaded() -> bool:
    try:
        with connect() as c:
            return (
                c.execute("SELECT 1 FROM data_as_of WHERE source = 'caiso_raw'").fetchone()
                is not None
            )
    except psycopg.Error:
        return False


def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The website, talking to the API, which talks to the database and the stand-in."""
    if not _loaded():
        pytest.skip("The data isn't loaded: run load_all first.")
    if not (WEB / "node_modules").exists():
        pytest.skip("Run npm install in web/ first.")
    if not (_free(API_PORT) and _free(WEB_PORT)):
        pytest.skip(f"Ports {API_PORT} and {WEB_PORT} must be free.")

    model = StandInModel()
    api = uvicorn.Server(
        uvicorn.Config(create_app(lambda: model), port=API_PORT, log_level="warning")
    )
    threading.Thread(target=api.run, daemon=True).start()
    log = tmp_path_factory.mktemp("web") / "next.log"
    web = subprocess.Popen(
        ["npx", "next", "dev", "--port", str(WEB_PORT)],
        cwd=WEB,
        env={
            **os.environ,
            "HEADWAY_API": f"http://127.0.0.1:{API_PORT}",
            "HEADWAY_DIST_DIR": ".next-e2e",
        },
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    url = f"http://localhost:{WEB_PORT}"
    try:
        deadline = time.monotonic() + 180
        while True:
            try:
                urllib.request.urlopen(url + "/map", timeout=60)
                break
            except OSError as e:
                if time.monotonic() > deadline:
                    pytest.fail(
                        f"The website didn't come up ({e}). Its output:\n{log.read_text()[-4000:]}"
                    )
                time.sleep(1)
        yield url
    finally:
        os.killpg(web.pid, signal.SIGTERM)
        web.wait(timeout=30)
        api.should_exit = True


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        try:
            launched = p.chromium.launch()
        except PlaywrightError:
            pytest.skip("Run `uv run playwright install chromium` first.")
        yield launched
        launched.close()


@pytest.fixture
def p(browser: Browser, site: str) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1400, "height": 950}, base_url=site)
    context.set_default_timeout(30_000)
    yield context.new_page()
    context.close()


@pytest.fixture(scope="module")
def conn() -> Iterator[Conn]:
    with connect() as c:
        yield c


def mw(value: float) -> str:
    """MW as the page shows it: to the nearest 10."""
    return f"{int(value / 10 + 0.5) * 10:,} MW"


# --- A scripted stand-in for the model ------------------------------------------------
#
# It reads the brief and the lookup results it is sent and answers the way the real model
# would: it looks things up, then quotes the lookups in claims the checker accepts.


def _call(name: str, **arguments: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"call_{name}", "name": name, "input": arguments}


def _figure(lookup: dict[str, Any], name: str, unit: str, derivation: str) -> dict[str, Any]:
    return {
        "value": lookup["figures"][name]["value"],
        "unit": unit,
        "derivation": derivation,
        "of": name,
        "source": "caiso_raw",
        "tool_call_id": lookup["tool_call_id"],
    }


def _counted(lookup: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [r["native_id"] for r in lookup["rows"]]
    return [
        {"value": len(rows), "unit": "projects", "derivation": "count", "of": "projects",
         "source": "caiso_raw", "source_row_ids": rows, "tool_call_id": lookup["tool_call_id"]},
        {"value": sum(r["mw_to_grid"] or 0 for r in lookup["rows"]), "unit": "MW",
         "derivation": "sum", "of": "mw_to_grid", "source": "caiso_raw",
         "source_row_ids": rows, "tool_call_id": lookup["tool_call_id"]},
    ]  # fmt: skip


class StandInModel:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def create(self, **request: Any) -> BetaMessage:
        self.requests.append(request)
        messages = request["messages"]
        brief = str(messages[0]["content"])
        results = [] if len(messages) == 1 else _results(messages[-1]["content"])
        content = (
            self._writing(brief, results)
            if "Write an assessment" in brief
            else (self._answering(brief, results))
        )
        return BetaMessage.model_validate(
            {
                "id": f"msg_{len(self.requests)}",
                "type": "message",
                "role": "assistant",
                "model": "stand-in",
                "content": content,
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 1_000, "output_tokens": 200},
            }
        )

    def _writing(self, brief: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        found = re.search(r"Write an assessment for a (.+?) project(?: of ([\d.]+) MW)? "
                          r"connecting at the (.+?) substation\. Its voltage sections: "
                          r"([^.]+?)\. The data", brief)  # fmt: skip
        assert found, brief
        kind, mw, site, places = found.groups()
        if not results:
            asked: dict[str, Any] = {"place": places.split(", ")[0], "within_years": 10}
            if kind != "Any type of":
                asked["project_type"] = kind
                if mw:
                    asked["mw"] = float(mw)
            return [
                _call("chance_of_being_built", **asked),
                _call("realistic_mw_ahead", site=site),
                _call("list_projects", site=site, status="waiting", rules="old"),
            ]
        chance, ahead, waiting = results
        return [_call("submit_assessment", claims=[
            {"kind": "factual", "id": "chance",
             "text": "Of {1} like this one, {0} were built within 10 years of applying.",
             "values": [_figure(chance, "chance", "%", "ratio"),
                        _figure(chance, "past_projects", "projects", "count")]},
            {"kind": "factual", "id": "ahead",
             "text": "Counting each by its chance of still being built, {0} of the {1} waiting "
                     "under the old rules is realistically ahead.",
             "values": [_figure(ahead, "realistic_mw", "MW", "sum"),
                        _figure(ahead, "waiting_mw", "MW", "sum")]},
            {"kind": "factual", "id": "waiting",
             "text": f"{{0}} are waiting at {site} under the old rules, {{1}} in all.",
             "values": _counted(waiting)},
            {"kind": "judgement", "id": "crowding",
             "text": "Most of what is waiting here is unlikely to be built, so the queue is "
                     "less crowded than its total suggests.",
             "based_on": ["ahead"]},
            {"kind": "judgement", "id": "comparison",
             "text": "Projects across California are a fair guide for this one.",
             "based_on": ["chance"]},
        ])]  # fmt: skip

    def _answering(self, brief: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        found = re.search(r"connecting at the (.+?) substation", brief)
        asked = re.search(r"A person asks: (['\"])(.+?)\1", brief)
        assert found and asked, brief
        site, request = found.group(1), asked.group(2).lower()
        if "stuck since" in request:
            year = int(re.search(r"\d{4}", request).group(0))  # type: ignore[union-attr]
            return [_call("propose_adjustment", waiting_since_year=year, why=asked.group(2))]
        if "withdrawn" in request:
            if not results:
                return [_call("list_projects", site=site, status="withdrawn")]
            (withdrawn,) = results
            return [_call("submit_assessment", claims=[
                {"kind": "factual", "id": "withdrawn",
                 "text": f"{{0}} have withdrawn at {site}, {{1}} in all.",
                 "values": _counted(withdrawn)},
            ])]  # fmt: skip
        return [_call("cant_answer", reason="The queue report doesn't say that.")]


def _results(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, list):
        return []
    found = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            try:
                found.append(json.loads(block["content"]))
            except (ValueError, TypeError):
                continue
    return found


# --- 1. The map ------------------------------------------------------------------------


def test_the_map_shows_substations_coloured_by_realistic_mw_ahead_with_unplaced_ones_listed_by_county(  # noqa: E501
    p: Page, conn: Conn
) -> None:
    p.goto("/map")

    # Coloured by realistic MW ahead: four plain classes, from under 300 to 2,000 and over.
    realistic = realistic_mw_ahead(conn, site="Midway").realistic_mw
    band = sum(realistic >= edge for edge in (300, 1_000, 2_000))
    expect(p.locator('path[data-site="Midway"]')).to_have_class(
        re.compile(rf"\bk{band}\b"), timeout=SLOW
    )
    search = p.get_by_role("searchbox", name="Search a town, county or substation")
    search.fill("Midway")
    p.get_by_role("button", name=re.compile(r"^Midway\b.*Kern")).click()
    panel = p.get_by_role("complementary", name="Find a place")
    expect(panel.get_by_role("heading", name="Midway")).to_be_visible()
    expect(panel).to_contain_text(mw(realistic))

    # A substation with no reviewed position is never drawn at a guessed point: it's
    # counted on its county and listed when that county is picked.
    unplaced = conn.execute(
        "SELECT pl.site, pl.county FROM places pl JOIN project_places pp USING (place) "
        "JOIN caiso_projects p USING (source, native_id) "
        "WHERE pl.positioned_by = 'county' AND pl.state = 'CA' AND p.status = 'Active' "
        "GROUP BY 1, 2 ORDER BY sum(p.mw_to_grid) DESC LIMIT 1"
    ).fetchone()
    assert unplaced is not None
    biggest, county = str(unplaced[0]), str(unplaced[1])
    in_county = [
        str(r[0])
        for r in conn.execute(
            "SELECT DISTINCT pl.site FROM places pl JOIN project_places pp USING (place) "
            "JOIN caiso_projects p USING (source, native_id) "
            "WHERE pl.positioned_by = 'county' AND pl.county = %s AND p.status = 'Active'",
            (county,),
        ).fetchall()
    ]
    expect(p.locator(f'path[data-site="{biggest}"]')).to_have_count(0)

    p.goto("/map")
    p.get_by_role("searchbox", name="Search a town, county or substation").fill(county)
    p.get_by_role("button", name=re.compile(rf"^{county} County")).click()
    somewhere = panel.get_by_role("region", name="Somewhere in the area, location not exact")
    for name in in_county:
        expect(
            somewhere.get_by_role("button", name=re.compile(rf"^{re.escape(name)}\b"))
        ).to_be_visible()
    expect(p.locator(f'.cbadge[title*="{county} County"]')).to_have_text(f"+{len(in_county)}")


# --- 2. A substation page ------------------------------------------------------------


def test_a_substation_page_shows_its_numbers_ladder_upgrades_and_costs_and_every_number_opens_its_rows(  # noqa: E501
    p: Page, conn: Conn
) -> None:
    p.goto("/substations/Midway")

    # Its numbers: for the page's starting project, a 200 MW solar + battery project at
    # Midway 230 kV.
    odds = odds_for(
        conn, within_years=10, project_type=ProjectType.SOLAR_BATTERY, mw=200,
        place="Midway 230 kV",
    )  # fmt: skip
    built = round(odds.chance.chance * 100)
    chance = p.get_by_role("article", name="Will it get built?")
    expect(chance).to_contain_text(f"{built} in 100", timeout=SLOW)
    assert odds.chance.typical_wait_years is not None
    expect(p.get_by_role("article", name="How long does it take?")).to_contain_text(
        f"{round(odds.chance.typical_wait_years)} years"
    )
    ahead = realistic_mw_ahead(conn, site="Midway")
    expect(p.get_by_role("article", name="How crowded is it?")).to_contain_text(
        mw(ahead.realistic_mw)
    )

    # The history ladder: from Midway outwards, the step in use marked.
    p.get_by_role("tab", name="Who we compared with").click()
    ladder = p.get_by_role("list", name="Comparison groups, closest first")
    expect(ladder.get_by_role("listitem").first).to_contain_text("Midway 230 kV only")
    expect(ladder.get_by_role("listitem").filter(has_text="in use")).to_contain_text(
        "Across California"
    )

    # The upgrades box and the cost box.
    p.get_by_role("tab", name="Upgrades and costs").click()
    upgrades = [
        str(r[0])
        for r in conn.execute(
            "SELECT DISTINCT u.name FROM upgrades u JOIN upgrade_places USING (plan_id) "
            "JOIN places pl USING (place) WHERE pl.site = 'Midway'"
        ).fetchall()
    ]
    box = p.get_by_role("region", name="Planned grid upgrades")
    for name in upgrades:
        expect(box).to_contain_text(name)
    costed = conn.execute(
        "SELECT b.bottleneck, b.cost_musd_2022 * 1000 / b.added_mw FROM bottlenecks b "
        "JOIN place_bottlenecks pb USING (bottleneck) JOIN places pl USING (place) "
        "WHERE pl.site = 'Midway' AND b.added_mw > 0 AND b.cost_musd_2022 IS NOT NULL LIMIT 1"
    ).fetchone()
    assert costed is not None
    costs = p.get_by_role("region", name="Bottlenecks nearby")
    expect(costs).to_contain_text(str(costed[0]))
    expect(costs).to_contain_text(f"${round(float(str(costed[1])))}/kW")

    # Clicking a number shows the rows it was worked out from: every past solar + battery
    # project of 150-300 MW in California under the old rules, dated.
    group = {
        str(r[0])
        for r in conn.execute(
            "SELECT p.native_id FROM caiso_projects p WHERE p.batch IS DISTINCT FROM 'C15' "
            "AND p.q_date IS NOT NULL AND (p.status = 'Active' OR p.outcome_date IS NOT NULL) "
            "AND p.mw_to_grid >= 150 AND p.mw_to_grid < 300 "
            "AND ARRAY(SELECT r.type FROM project_resources r WHERE r.source = p.source "
            "          AND r.native_id = p.native_id ORDER BY r.type) = ARRAY['Battery', 'Solar']"
        ).fetchall()
    }
    p.get_by_role("tab", name="How similar projects fared").click()
    chance.get_by_role("button", name=f"{built} in 100").click()
    drawer = p.get_by_role("dialog")
    drawer.get_by_text(f"See all {len(group)} source rows").click()
    expect(drawer.locator("tbody tr")).to_have_count(len(group))
    expect(drawer).to_contain_text(min(group))


# --- 3. Adjusting, reviewing and asking -----------------------------------------------


def test_adjusting_reviewing_and_asking_all_work_from_the_page(p: Page, conn: Conn) -> None:
    p.goto("/substations/Midway")
    at_midway = (
        "p.native_id IN (SELECT native_id FROM project_places JOIN places USING (place) "
        "WHERE places.site = 'Midway')"
    )

    # Reviewing: the agent writes it; a person agrees with one Judgement and rewords another.
    p.get_by_role("tab", name=re.compile("^Write-up")).click()
    p.get_by_role("button", name="Write it").click()
    crowding = p.get_by_role("group", name=re.compile("^Most of what is waiting here"))
    crowding.get_by_role("button", name="Agree", exact=True).click()
    expect(crowding).to_contain_text("You agreed")
    comparison = p.get_by_role("group", name=re.compile("^Projects across California"))
    comparison.get_by_role("button", name="Reword").click()
    comparison.get_by_role("textbox", name="Say it your way").fill(
        "Statewide history is the best guide available here."
    )
    comparison.get_by_role("button", name="Save").click()
    expect(p.get_by_role("group", name=re.compile("^Statewide history"))).to_contain_text(
        "Reworded by you"
    )

    # Asking: a checked answer, added to the write-up only when the person chooses.
    (withdrawn,) = conn.execute(
        f"SELECT count(*) FROM caiso_projects p WHERE p.status = 'Withdrawn' AND {at_midway}"
    ).fetchone() or (None,)
    p.get_by_role("tab", name="Ask").click()
    question = p.get_by_role("textbox", name="Your question")
    question.fill("How many projects have withdrawn at Midway?")
    p.get_by_role("button", name="Ask", exact=True).click()
    answer = p.locator(".msg.bot").filter(has_text="have withdrawn at Midway")
    expect(answer).to_contain_text(f"{withdrawn} projects have withdrawn at Midway")
    answer.get_by_role("button", name="Add to write-up").click()
    expect(answer).to_contain_text("Added to the write-up")

    # Asking something the data can't answer gets a plain reason, not a guess.
    question.fill("What would it cost to connect here?")
    p.get_by_role("button", name="Ask", exact=True).click()
    expect(p.locator(".msg.bot").last).to_contain_text("outside what this data can answer")

    # Adjusting: a plain request becomes a proposal, applied once the person confirms.
    stuck = frozenset(
        str(r[0])
        for r in conn.execute(
            "SELECT native_id FROM caiso_projects p WHERE p.status = 'Active' "
            f"AND extract(year FROM p.q_date) <= 2019 AND {at_midway}"
        ).fetchall()
    )
    after = realistic_mw_ahead(conn, site="Midway", leave_out=stuck)
    question.fill("Ignore projects stuck since 2019")
    p.get_by_role("button", name="Ask", exact=True).click()
    proposal = p.locator(".prop").last
    expect(proposal).to_contain_text("nothing applied yet")
    for native_id in stuck:
        expect(proposal).to_contain_text(native_id)
    proposal.get_by_role("button", name="Make this change").click()
    expect(proposal).to_contain_text("Change applied")

    p.get_by_role("tab", name="The odds").click()
    expect(p.get_by_role("article", name="How crowded is it?")).to_contain_text(
        mw(after.realistic_mw)
    )

    # In the write-up: the answer is there, the numbers are worked out again, and the
    # Judgement resting on a number that moved comes back for review.
    p.get_by_role("tab", name=re.compile("^Write-up")).click()
    doc = p.get_by_role("article", name=re.compile("at Midway$"))
    expect(doc).to_contain_text(f"{withdrawn} projects have withdrawn at Midway")
    expect(doc).to_contain_text(f"{len(after.projects)} projects are waiting at Midway")
    expect(
        p.get_by_role("group", name=re.compile("^Most of what is waiting here"))
    ).to_contain_text("do you agree?")
    expect(doc.get_by_role("button", name="Finalise")).to_be_disabled()
    p.get_by_role("group", name=re.compile("^Most of what is waiting here")).get_by_role(
        "button", name="Disagree"
    ).click()
    doc.get_by_role("button", name="Finalise").click()
    expect(doc).to_contain_text("Final.")
