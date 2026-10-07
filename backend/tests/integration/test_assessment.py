"""The agent writes a checked assessment, and a person reviews it.

The model is the one thing replaced here: a scripted stand-in plays its part, reading the
lookup results it is sent and answering the way the real model would. Everything else (the
lookups, the checking, the review) runs for real against the CAISO files in ``data/``.
Expected numbers come from hand-written SQL in each test, never from the code under test.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from anthropic.types.beta import BetaMessage

from interconnection_agent.assessment import (
    Adjustment,
    Assessment,
    AssessmentIsFinal,
    Decision,
    FactualClaim,
    NotReady,
    Project,
    ask,
    write_assessment,
)
from interconnection_agent.budget import Limits, TokenLimitExceeded, TurnLimitExceeded
from interconnection_agent.chances import ProjectType
from interconnection_agent.db import connect
from interconnection_agent.load import load_all

Conn = psycopg.Connection[tuple[object, ...]]
ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "src/interconnection_agent/skills/writing-an-assessment/SKILL.md"

SOLAR_100_MW = Project(project_type=ProjectType.SOLAR, mw=100)


@pytest.fixture(scope="module")
def conn() -> Iterator[Conn]:
    """Load everything once for this module; roll it all back afterwards."""
    with connect() as c:
        c.autocommit = False
        try:
            load_all(ROOT / "data", c)
            yield c
        finally:
            c.rollback()


# --- The scripted stand-in for the model -----------------------------------------------

Turn = Callable[[dict[str, Any]], list[dict[str, Any]]]


class ScriptedModel:
    """Answers each request with the next turn of a script. A turn is a function from the
    request to the content blocks of the reply; a reply that runs lookups or submits ends
    with ``tool_use``."""

    def __init__(self, *turns: Turn, usage: dict[str, int] | None = None) -> None:
        self.turns = list(turns)
        self.requests: list[dict[str, Any]] = []
        self.usage = usage or {"input_tokens": 1_000, "output_tokens": 200}

    def create(self, **request: Any) -> BetaMessage:
        # The conversation as it was when sent: the agent keeps adding to its own list.
        request = {**request, "messages": list(request["messages"])}
        self.requests.append(request)
        content = self.turns.pop(0)(request)
        calls = any(block["type"] == "tool_use" for block in content)
        return BetaMessage.model_validate(
            {
                "id": f"msg_{len(self.requests)}",
                "type": "message",
                "role": "assistant",
                "model": "scripted",
                "content": content,
                "stop_reason": "tool_use" if calls else "end_turn",
                "stop_sequence": None,
                "usage": self.usage,
            }
        )


def call(name: str, **arguments: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"call_{name}_{len(arguments)}", "name": name,
            "input": arguments}  # fmt: skip


def results(request: dict[str, Any]) -> list[dict[str, Any]]:
    """The tool results in the last message sent to the model, each parsed from JSON."""
    return [json.loads(block["content"]) for block in request["messages"][-1]["content"]]


def lookups_at_whirlwind(_: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        call("chance_of_being_built", place="Whirlwind 230 kV", project_type="Solar only",
             mw=100, within_years=10),
        call("realistic_mw_ahead", site="Whirlwind"),
        call("list_projects", site="Whirlwind", status="waiting", rules="old"),
    ]  # fmt: skip


def claims_from(lookups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What a model would write from the three lookups: every number quoted from a lookup."""
    chance, ahead, waiting = lookups
    rows = [row["native_id"] for row in waiting["rows"]]
    return [
        {
            "kind": "factual",
            "id": "chance",
            "text": "Of {1} like this one, {0} were built within 10 years of applying.",
            "values": [
                {"value": chance["figures"]["chance"]["value"], "unit": "%",
                 "derivation": "ratio", "of": "chance", "source": "caiso_raw",
                 "tool_call_id": chance["tool_call_id"]},
                {"value": chance["figures"]["past_projects"]["value"], "unit": "projects",
                 "derivation": "count", "of": "past_projects", "source": "caiso_raw",
                 "tool_call_id": chance["tool_call_id"]},
            ],
        },
        {
            "kind": "factual",
            "id": "ahead",
            "text": "Counting each by its chance of still being built, {0} of the {1} waiting "
            "under the old rules is realistically ahead.",
            "values": [
                {"value": ahead["figures"]["realistic_mw"]["value"], "unit": "MW",
                 "derivation": "sum", "of": "realistic_mw", "source": "caiso_raw",
                 "tool_call_id": ahead["tool_call_id"]},
                {"value": ahead["figures"]["waiting_mw"]["value"], "unit": "MW",
                 "derivation": "sum", "of": "waiting_mw", "source": "caiso_raw",
                 "tool_call_id": ahead["tool_call_id"]},
            ],
        },
        {
            "kind": "factual",
            "id": "waiting",
            "text": "{0} are waiting at Whirlwind under the old rules, {1} in all.",
            "values": [
                {"value": len(rows), "unit": "projects", "derivation": "count",
                 "of": "projects", "source": "caiso_raw", "source_row_ids": rows,
                 "tool_call_id": waiting["tool_call_id"]},
                {"value": sum(r["mw_to_grid"] or 0 for r in waiting["rows"]), "unit": "MW",
                 "derivation": "sum", "of": "mw_to_grid", "source": "caiso_raw",
                 "source_row_ids": rows, "tool_call_id": waiting["tool_call_id"]},
            ],
        },
        {
            "kind": "judgement",
            "id": "crowding",
            "text": "Most of what is waiting here is unlikely to be built, so the queue is "
            "less crowded than its total suggests.",
            "based_on": ["ahead"],
        },
    ]  # fmt: skip


def submit(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [call("submit_assessment", claims=claims)]


def whirlwind_waiting_old_rules(conn: Conn) -> tuple[int, float]:
    """Projects waiting at any voltage section of Whirlwind, outside the 2023 batch."""
    row = conn.execute(
        "SELECT count(*), sum(mw_to_grid) FROM projects p WHERE p.source = 'caiso_raw' "
        "AND p.status = 'Active' AND p.batch IS DISTINCT FROM 'C15' AND p.native_id IN ("
        "  SELECT native_id FROM project_places pp JOIN places USING (place) "
        "  WHERE places.site = 'Whirlwind')"
    ).fetchone()
    assert row is not None
    count, mw = row
    assert isinstance(count, int) and isinstance(mw, float)
    return count, mw


# --- 1. Writing an assessment ----------------------------------------------------------


def test_the_agent_writes_only_factual_claims_and_judgements_following_the_writing_skill(
    conn: Conn,
) -> None:
    lookups: list[dict[str, Any]] = []

    def first_draft(request: dict[str, Any]) -> list[dict[str, Any]]:
        lookups.extend(results(request))
        # Something that is neither a Factual Claim nor a Judgement.
        summary = {"kind": "summary", "text": "Whirlwind is a busy substation."}
        return submit(claims_from(lookups) + [summary])

    model = ScriptedModel(lookups_at_whirlwind, first_draft, lambda _: submit(claims_from(lookups)))
    assessment = write_assessment(conn, model, site="Whirlwind", project=SOLAR_100_MW)

    # It follows the writing skill: the skill is what the model is told to do.
    assert all(r["system"] == SKILL.read_text() for r in model.requests)
    # The summary was sent back as neither kind; the second draft left it out.
    sent_back = model.requests[2]["messages"][-1]["content"][0]
    assert sent_back["is_error"] and "neither a Factual Claim nor a Judgement" in str(
        sent_back["content"]
    )
    assert [c.id for c in assessment.claims] == ["chance", "ahead", "waiting", "crowding"]
    assert {c.kind for c in assessment.claims} == {"factual", "judgement"}
    assert all(c.check is not None and c.check.passed for c in assessment.factual_claims)

    # The text is built from the checked claims, numbers filled in by code.
    count, mw = whirlwind_waiting_old_rules(conn)
    assert f"{count} projects are waiting at Whirlwind under the old rules, {mw:,.0f} MW" in (
        assessment.text()
    )


def test_every_model_call_goes_through_the_spending_limits(conn: Conn) -> None:
    model = ScriptedModel(lookups_at_whirlwind, lambda r: submit(claims_from(results(r))))

    with pytest.raises(TurnLimitExceeded):
        write_assessment(
            conn, model, site="Whirlwind", project=SOLAR_100_MW, limits=Limits(max_turns=1)
        )
    assert len(model.requests) == 1
    assert model.requests[0]["max_tokens"] == Limits().max_output_tokens_per_call


def test_tokens_read_from_or_written_to_the_cache_count_toward_the_spending_limits(
    conn: Conn,
) -> None:
    # Once caching is on, most of each request is reported as read from the cache, apart
    # from the uncached input.
    model = ScriptedModel(
        lookups_at_whirlwind,
        lambda r: submit(claims_from(results(r))),
        usage={
            "input_tokens": 1_000,
            "output_tokens": 200,
            "cache_creation_input_tokens": 10_000,
            "cache_read_input_tokens": 50_000,
        },
    )

    with pytest.raises(TokenLimitExceeded):
        write_assessment(
            conn,
            model,
            site="Whirlwind",
            project=SOLAR_100_MW,
            limits=Limits(max_tokens_per_assessment=100_000),
        )
    assert len(model.requests) == 2


# --- 3. Reviewing an assessment --------------------------------------------------------


def written(conn: Conn) -> Assessment:
    """An assessment of a 100 MW solar project at Whirlwind, as the scripted model writes it."""
    model = ScriptedModel(lookups_at_whirlwind, lambda r: submit(claims_from(results(r))))
    return write_assessment(conn, model, site="Whirlwind", project=SOLAR_100_MW)


def biggest_waiting_at_whirlwind(conn: Conn) -> tuple[str, float]:
    row = conn.execute(
        "SELECT native_id, mw_to_grid FROM projects p WHERE p.source = 'caiso_raw' "
        "AND p.status = 'Active' AND p.batch IS DISTINCT FROM 'C15' AND p.native_id IN ("
        "  SELECT native_id FROM project_places JOIN places USING (place) "
        "  WHERE places.site = 'Whirlwind') ORDER BY mw_to_grid DESC LIMIT 1"
    ).fetchone()
    assert row is not None and isinstance(row[1], float)
    return str(row[0]), row[1]


def worked_out(assessment: Assessment, claim_id: str) -> tuple[float | None, ...]:
    claim = next(c for c in assessment.factual_claims if c.id == claim_id)
    assert claim.check is not None and claim.check.passed, claim.check
    return claim.check.worked_out


def test_an_adjustment_recalculates_and_rechecks_the_numbers_it_affects(conn: Conn) -> None:
    assessment = written(conn)
    count, mw = whirlwind_waiting_old_rules(conn)
    biggest, its_mw = biggest_waiting_at_whirlwind(conn)
    realistic_before, waiting_before = worked_out(assessment, "ahead")
    assessment.decide("crowding", Decision.APPROVED, by="Dana")

    assessment.adjust(
        Adjustment(leave_out=frozenset({biggest}), why="It duplicates another request."),
        by="Dana",
    )

    # The numbers are worked out again without it, and checked again.
    count_after, mw_after = worked_out(assessment, "waiting")
    assert count_after == count - 1 and mw_after == pytest.approx(mw - its_mw)
    _, waiting_after = worked_out(assessment, "ahead")
    assert waiting_after == pytest.approx((waiting_before or 0) - its_mw)
    assert f"{count - 1} projects are waiting at Whirlwind under the old rules, " \
        f"{mw - its_mw:,.0f} MW in all" in assessment.text()  # fmt: skip
    # The Judgement resting on a changed number needs deciding again.
    crowding = next(j for j in assessment.judgements if j.id == "crowding")
    assert crowding.decision is Decision.AWAITING
    # Who, what, when and why.
    change = assessment.changes[-1]
    assert change.who == "Dana" and change.why == "It duplicates another request."
    assert biggest in change.what and "waiting" in change.what and change.when is not None


AT_THE_WHIRLWIND_SUBSTATION = "Solar only, 50-150 MW, at the Whirlwind substation"


def test_an_adjustment_can_narrow_the_comparison_group(conn: Conn) -> None:
    assessment = written(conn)
    why = "Only this substation's own history is comparable."

    assessment.adjust(Adjustment(comparison_group=AT_THE_WHIRLWIND_SUBSTATION, why=why), by="Dana")

    # Past solar-only projects of 50-150 MW at any voltage section of Whirlwind, under the
    # old rules, that have a queue date and, if they ended, an end date.
    (past,) = conn.execute(
        "SELECT count(*) FROM caiso_projects p WHERE p.batch IS DISTINCT FROM 'C15' "
        "AND p.q_date IS NOT NULL AND (p.status = 'Active' OR p.outcome_date IS NOT NULL) "
        "AND p.mw_to_grid >= 50 AND p.mw_to_grid < 150 "
        "AND ARRAY(SELECT r.type FROM project_resources r WHERE r.source = p.source "
        "          AND r.native_id = p.native_id) = ARRAY['Solar'] "
        "AND p.native_id IN (SELECT native_id FROM project_places JOIN places USING (place) "
        "                    WHERE places.site = 'Whirlwind')"
    ).fetchone() or (None,)
    _, past_projects = worked_out(assessment, "chance")
    assert past_projects == past
    assert f"Of {past} projects like this one" in assessment.text()
    change = assessment.changes[-1]
    assert AT_THE_WHIRLWIND_SUBSTATION in change.what and change.why == why

    # Only a group the assessment's comparisons offer.
    with pytest.raises(ValueError, match="comparison group"):
        assessment.adjust(Adjustment(comparison_group="Made up", why=why), by="Dana")


def test_an_adjustment_never_brings_back_a_rejected_claim(conn: Conn) -> None:
    lookups: list[dict[str, Any]] = []

    def with_some_rows(request: dict[str, Any]) -> list[dict[str, Any]]:
        """Both drafts count only some of the waiting projects: the second is accepted, with
        that claim rejected."""
        lookups.extend([] if lookups else results(request))
        claims = claims_from(lookups)
        waiting = claims[2]["values"][0]
        waiting["source_row_ids"] = waiting["source_row_ids"][1:]
        waiting["value"] = len(waiting["source_row_ids"])
        return submit(claims)

    model = ScriptedModel(lookups_at_whirlwind, with_some_rows, with_some_rows)
    assessment = write_assessment(conn, model, site="Whirlwind", project=SOLAR_100_MW)
    biggest, _ = biggest_waiting_at_whirlwind(conn)

    assessment.adjust(Adjustment(leave_out=frozenset({biggest}), why="A duplicate."), by="Dana")

    waiting = next(c for c in assessment.factual_claims if c.id == "waiting")
    assert waiting.check is not None and not waiting.check.passed
    assert "are waiting at Whirlwind" not in assessment.text()


def test_questions_share_the_assessments_spending_limits(conn: Conn) -> None:
    model = ScriptedModel(lookups_at_whirlwind, lambda r: submit(claims_from(results(r))))
    assessment = write_assessment(
        conn, model, site="Whirlwind", project=SOLAR_100_MW, limits=Limits(max_turns=2)
    )

    with pytest.raises(TurnLimitExceeded):
        ask(assessment, ScriptedModel(), "How many projects have withdrawn here?")


def test_judgements_are_decided_by_a_person_and_final_needs_every_one_decided(
    conn: Conn,
) -> None:
    assessment = written(conn)

    with pytest.raises(NotReady, match="crowding"):
        assessment.finalise(by="Dana")

    assessment.rewrite(
        "crowding",
        "Old, stalled requests make the queue here look more crowded than it is.",
        by="Dana",
        why="Clearer.",
    )
    assessment.finalise(by="Dana")

    assert assessment.final
    assert "Old, stalled requests make the queue here look more crowded than it is. " \
        "[Judgement, not checked by code: rewritten]" in assessment.text()  # fmt: skip
    assert [(c.who, c.why) for c in assessment.changes[-2:]] == [("Dana", "Clearer."), ("Dana", "")]
    # Once final, nothing changes.
    with pytest.raises(AssessmentIsFinal):
        assessment.decide("crowding", Decision.REJECTED, by="Dana")


def test_a_judgement_is_never_shown_as_checked(conn: Conn) -> None:
    lookups: list[dict[str, Any]] = []

    def judgements(request: dict[str, Any]) -> list[dict[str, Any]]:
        lookups.extend([] if lookups else results(request))
        claims = claims_from(lookups)
        claims.append(
            {"kind": "judgement", "id": "says-checked", "text": "This one is checked.",
             "checked": True, "check": {"passed": True}, "based_on": ["ahead"]}
        )  # fmt: skip
        claims.append(
            {"kind": "judgement", "id": "with-a-number", "text": "About 900 MW will drop out.",
             "based_on": ["ahead"]}
        )  # fmt: skip
        return submit(claims)

    model = ScriptedModel(lookups_at_whirlwind, judgements, judgements)
    assessment = write_assessment(conn, model, site="Whirlwind", project=SOLAR_100_MW)
    assessment.decide("crowding", Decision.APPROVED, by="Dana")

    shown = {c.id: c for c in assessment.judgements}
    assert set(shown) == {"crowding", "says-checked"}  # a number no code checked: rejected
    assert not any(hasattr(j, "check") for j in shown.values())
    lines = [line for line in assessment.text().splitlines() if "Judgement" in line]
    assert len(lines) == 2 and not any("[checked]" in line for line in lines)
    assert any("[Judgement, not checked by code: approved]" in line for line in lines)


# --- 4. Asking about the assessment ----------------------------------------------------


def test_a_plain_request_becomes_a_proposed_adjustment_that_applies_only_once_confirmed(
    conn: Conn,
) -> None:
    assessment = written(conn)
    before = assessment.text()
    why = "Projects stuck since 2019 are unlikely to be built."
    model = ScriptedModel(lambda _: [call("propose_adjustment", waiting_since_year=2019, why=why)])

    answer = ask(assessment, model, "ignore projects stuck since 2019")

    assert "ignore projects stuck since 2019" in model.requests[0]["messages"][0]["content"]
    # Waiting at Whirlwind since 2019 or earlier, under either rules.
    stuck = {
        str(r[0])
        for r in conn.execute(
            "SELECT native_id FROM projects p WHERE p.source = 'caiso_raw' "
            "AND p.status = 'Active' AND extract(year FROM p.q_date) <= 2019 AND p.native_id IN ("
            "  SELECT native_id FROM project_places JOIN places USING (place) "
            "  WHERE places.site = 'Whirlwind')"
        ).fetchall()
    }
    assert stuck and answer.proposal is not None
    assert answer.proposal.adjustment.leave_out == stuck
    assert answer.proposal.adjustment.why == why
    assert all(native_id in answer.proposal.description for native_id in stuck)
    # Nothing has changed yet; the proposal is logged.
    assert assessment.text() == before
    assert assessment.changes[-1].what == f"proposed: {answer.proposal.description}"

    assessment.confirm(answer.id, by="Dana")

    after_2019 = conn.execute(
        "SELECT count(*), sum(mw_to_grid) FROM projects p WHERE p.source = 'caiso_raw' "
        "AND p.status = 'Active' AND p.batch IS DISTINCT FROM 'C15' "
        "AND extract(year FROM p.q_date) > 2019 AND p.native_id IN ("
        "  SELECT native_id FROM project_places JOIN places USING (place) "
        "  WHERE places.site = 'Whirlwind')"
    ).fetchone()
    assert after_2019 is not None
    count, mw = worked_out(assessment, "waiting")
    assert count == after_2019[0] and mw == pytest.approx(after_2019[1])
    assert assessment.changes[-1].who == "Dana" and assessment.changes[-1].why == why
    with pytest.raises(KeyError):
        assessment.confirm(answer.id, by="Dana")  # once only


def test_a_question_gets_new_checked_claims_held_until_a_person_adds_them(conn: Conn) -> None:
    assessment = written(conn)
    before = assessment.text()

    def answer(request: dict[str, Any]) -> list[dict[str, Any]]:
        (withdrawn,) = results(request)
        rows = [row["native_id"] for row in withdrawn["rows"]]
        return submit([
            {"kind": "factual", "id": "withdrawn", "text": "{0} have withdrawn at Whirlwind.",
             "values": [{"value": len(rows), "unit": "projects", "derivation": "count",
                         "of": "projects", "source": "caiso_raw", "source_row_ids": rows,
                         "tool_call_id": withdrawn["tool_call_id"]}]},
        ])  # fmt: skip

    model = ScriptedModel(
        lambda _: [call("list_projects", site="Whirlwind", status="withdrawn")], answer
    )
    held = ask(assessment, model, "How many projects have withdrawn here?")

    (withdrawn,) = conn.execute(
        "SELECT count(*) FROM projects p WHERE p.source = 'caiso_raw' "
        "AND p.status = 'Withdrawn' AND p.native_id IN ("
        "  SELECT native_id FROM project_places JOIN places USING (place) "
        "  WHERE places.site = 'Whirlwind')"
    ).fetchone() or (None,)
    # Checked, but held: the write-up doesn't change until a person adds the answer.
    (claim,) = held.claims
    assert isinstance(claim, FactualClaim) and claim.check is not None and claim.check.passed
    assert claim.check.worked_out == (withdrawn,)
    assert assessment.text() == before
    assert assessment.changes[-1].what == "answered: How many projects have withdrawn here?"

    assessment.add(held.id, by="Dana")

    assert f"{withdrawn} projects have withdrawn at Whirlwind. [checked]" in assessment.text()
    assert assessment.changes[-1].who == "Dana" and "withdrawn" in assessment.changes[-1].what
    with pytest.raises(KeyError):
        assessment.add(held.id, by="Dana")  # once only


def test_a_request_to_compare_more_narrowly_becomes_a_proposed_adjustment(conn: Conn) -> None:
    assessment = written(conn)
    why = "Compare only with this substation."
    model = ScriptedModel(
        lambda _: [call("propose_adjustment", comparison_group="Made up", why=why)],
        lambda _: [
            call("propose_adjustment", comparison_group=AT_THE_WHIRLWIND_SUBSTATION, why=why)
        ],
    )

    answer = ask(assessment, model, "only compare with projects at this substation")

    # The made-up group was sent back; the real one is proposed, and nothing applied yet.
    assert model.requests[1]["messages"][-1]["content"][0]["is_error"]
    assert answer.proposal is not None
    assert answer.proposal.adjustment.comparison_group == AT_THE_WHIRLWIND_SUBSTATION
    assert AT_THE_WHIRLWIND_SUBSTATION in answer.proposal.description
    assert assessment.changes[-1].what.startswith("proposed:")


def test_a_question_the_data_cant_answer_gets_a_plain_reason_instead_of_a_guess(
    conn: Conn,
) -> None:
    assessment = written(conn)
    before, turns = assessment.text(), assessment.budget.turns_used
    reason = "The queue report doesn't say what a project pays to connect."
    model = ScriptedModel(
        # A reason may not state numbers no code checked: sent back.
        lambda _: [call("cant_answer", reason="It would cost about $40 million to connect.")],
        lambda _: [call("cant_answer", reason=reason)],
    )

    answer = ask(assessment, model, "What would it cost to connect here?")

    assert model.requests[1]["messages"][-1]["content"][0]["is_error"]
    assert answer.cant_answer == reason
    assert not answer.claims and answer.proposal is None
    assert assessment.text() == before
    # It stops there: two model calls, nowhere near the spending limit.
    assert assessment.budget.turns_used == turns + 2
    assert "cant_answer" in SKILL.read_text()
    assert reason in assessment.changes[-1].what
