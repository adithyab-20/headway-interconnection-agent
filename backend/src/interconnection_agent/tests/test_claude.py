"""What the site sends to Anthropic for each model call, without calling the API.

A stand-in for the Anthropic client records each request. The agent's own requests (tools,
messages, thinking) are covered by the assessment tests; these cover what ``Claude`` adds.
"""

from __future__ import annotations

from typing import Any

import pytest
from anthropic.types.beta import BetaMessage

from interconnection_agent.assessment import Claude
from interconnection_agent.settings import Settings

REQUEST = {"max_tokens": 1_000, "messages": [{"role": "user", "content": "Hello"}]}


class RecordedMessages:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def create(self, **request: Any) -> BetaMessage:
        self.sent.append(request)
        return BetaMessage.model_validate(
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": request["model"],
                "content": [{"type": "text", "text": "Hi"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 2},
            }
        )


def sent_with(model: str) -> dict[str, Any]:
    messages = RecordedMessages()
    Claude(Settings(api_key="sk-test", model=model), messages=messages).create(**REQUEST)
    return messages.sent[0]


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"])
def test_each_call_uses_the_chosen_model_and_caches_the_conversation_so_far(model: str) -> None:
    sent = sent_with(model)

    assert sent["model"] == model
    assert sent["cache_control"] == {"type": "ephemeral"}
    assert sent["messages"] == REQUEST["messages"]


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-opus-5-5"])
def test_a_declined_call_falls_back_to_another_model_where_the_model_offers_one(
    model: str,
) -> None:
    sent = sent_with(model)

    assert sent["fallbacks"] == "default"
    assert sent["betas"] == ["server-side-fallback-2026-07-01"]


def test_haiku_offers_no_fallback_so_none_is_asked_for() -> None:
    sent = sent_with("claude-haiku-5-5")

    assert "fallbacks" not in sent
    assert "betas" not in sent
