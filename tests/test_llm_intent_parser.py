"""Tests for LLMIntentParser -- fully offline, no real network calls, and must
pass whether or not the `anthropic` package happens to be installed.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

from minsky.agents.intent_parser import RuleBasedIntentParser
from minsky.agents.llm_intent_parser import AnthropicLLMClient, LLMIntentParser
from minsky.schema import GoalType, Intent

_RAW_TEXT = "I want to become job-ready in data analytics within 3 months"

_WELL_FORMED_PAYLOAD = {
    "goal_type": "job_readiness",
    "topics": ["data analytics"],
    "max_duration_weeks": 12,
    "preferred_mode": "Self Paced",
    "preferred_language": "English",
    "needs_credits": False,
    "educational_level": "undergraduate",
    "industry_sector": "IT",
    "confidence": 0.9,
}


class _FakeClient:
    """Minimal `LLMClient` stub returning a canned response."""

    def __init__(self, response: str | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[dict] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        if self.exc is not None:
            raise self.exc
        assert self.response is not None
        return self.response


# -- (a) well-formed JSON ----------------------------------------------------


def test_well_formed_json_produces_matching_intent():
    client = _FakeClient(response=json.dumps(_WELL_FORMED_PAYLOAD))
    parser = LLMIntentParser(client=client)

    intent = parser.parse(_RAW_TEXT)

    assert isinstance(intent, Intent)
    assert intent.raw_text == _RAW_TEXT
    assert intent.goal_type == GoalType.JOB_READINESS
    assert intent.topics == ["data analytics"]
    assert intent.max_duration_weeks == 12
    assert intent.preferred_mode == "Self Paced"
    assert intent.preferred_language == "English"
    assert intent.needs_credits is False
    assert intent.educational_level == "undergraduate"
    assert intent.industry_sector == "IT"
    assert intent.confidence == 0.9
    # sanity: the client actually got called with the raw text
    assert client.calls[0]["user"] == _RAW_TEXT


# -- (b) fenced JSON ----------------------------------------------------------


def test_json_wrapped_in_markdown_fence_still_parses():
    fenced = "```json\n" + json.dumps(_WELL_FORMED_PAYLOAD) + "\n```"
    client = _FakeClient(response=fenced)
    parser = LLMIntentParser(client=client)

    intent = parser.parse(_RAW_TEXT)

    assert intent.goal_type == GoalType.JOB_READINESS
    assert intent.topics == ["data analytics"]
    assert intent.max_duration_weeks == 12


def test_json_wrapped_in_plain_fence_still_parses():
    fenced = "```\n" + json.dumps(_WELL_FORMED_PAYLOAD) + "\n```"
    client = _FakeClient(response=fenced)
    parser = LLMIntentParser(client=client)

    intent = parser.parse(_RAW_TEXT)

    assert intent.goal_type == GoalType.JOB_READINESS


# -- (c) garbage / non-JSON output -> fallback -------------------------------


def test_non_json_response_falls_back_to_rule_based_parser():
    client = _FakeClient(response="this is not json at all, sorry!")
    parser = LLMIntentParser(client=client)

    intent = parser.parse(_RAW_TEXT)
    expected = RuleBasedIntentParser().parse(_RAW_TEXT)

    assert intent == expected


# -- (d) client raises -> fallback -------------------------------------------


def test_client_exception_falls_back_cleanly():
    client = _FakeClient(exc=RuntimeError("network exploded"))
    parser = LLMIntentParser(client=client)

    intent = parser.parse(_RAW_TEXT)
    expected = RuleBasedIntentParser().parse(_RAW_TEXT)

    assert intent == expected


# -- (e) invalid goal_type / wrong types -> fallback -------------------------


def test_invalid_goal_type_falls_back():
    payload = dict(_WELL_FORMED_PAYLOAD, goal_type="not_a_real_goal_type")
    client = _FakeClient(response=json.dumps(payload))
    parser = LLMIntentParser(client=client)

    intent = parser.parse(_RAW_TEXT)
    expected = RuleBasedIntentParser().parse(_RAW_TEXT)

    assert intent == expected


def test_wrong_types_for_fields_falls_back():
    payload = dict(_WELL_FORMED_PAYLOAD, topics="data analytics", max_duration_weeks="twelve")
    client = _FakeClient(response=json.dumps(payload))
    parser = LLMIntentParser(client=client)

    intent = parser.parse(_RAW_TEXT)
    expected = RuleBasedIntentParser().parse(_RAW_TEXT)

    assert intent == expected


def test_invalid_preferred_mode_falls_back():
    payload = dict(_WELL_FORMED_PAYLOAD, preferred_mode="Whenever")
    client = _FakeClient(response=json.dumps(payload))
    parser = LLMIntentParser(client=client)

    intent = parser.parse(_RAW_TEXT)
    expected = RuleBasedIntentParser().parse(_RAW_TEXT)

    assert intent == expected


# -- defaults: LLMIntentParser() with no args should never explode ----------


def test_default_construction_and_parse_never_raises_without_credentials():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        parser = LLMIntentParser()
        intent = parser.parse(_RAW_TEXT)

    expected = RuleBasedIntentParser().parse(_RAW_TEXT)
    assert intent == expected


# -- AnthropicLLMClient lazy-import / lazy-key-check smoke test -------------


def test_anthropic_client_construction_never_raises():
    # Construction must never require the package or the API key -- only
    # `.complete()` should touch either.
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("MINSKY_LLM_MODEL", None)
        client = AnthropicLLMClient()
        assert client.model == "claude-haiku-4-5-20251001"


def test_anthropic_client_model_override_env_and_constructor():
    with patch.dict(os.environ, {"MINSKY_LLM_MODEL": "claude-env-model"}, clear=False):
        assert AnthropicLLMClient().model == "claude-env-model"
        assert AnthropicLLMClient(model="claude-explicit-model").model == "claude-explicit-model"


def test_anthropic_client_complete_raises_clear_error_without_key_or_package():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        client = AnthropicLLMClient()
        try:
            client.complete(system="sys", user="user")
        except RuntimeError as exc:
            message = str(exc)
            assert "anthropic" in message.lower() or "ANTHROPIC_API_KEY" in message
        else:
            raise AssertionError("expected RuntimeError when package/key is missing")
