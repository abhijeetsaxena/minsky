"""Tests for the FastAPI HTTP wrapper (src/minsky/api.py).

Fully offline / deterministic by default: every test uses course_source
"sample" except the one gated integration test at the bottom, which is
skipped unless MINSKY_LIVE_TESTS=1 is set (same gate used in
tests/test_swayam_client.py) so the default suite never touches the network.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from minsky.agents.constraint_resolver import load_facets
from minsky.api import app

client = TestClient(app)

_SAMPLE_INTENT = "I want to become job-ready in data analytics within 3 months"


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_facets_returns_real_taxonomy():
    response = client.get("/facets")
    assert response.status_code == 200
    body = response.json()
    for key in ("national_coordinator", "industry_sector", "credits", "category"):
        assert key in body
    assert body == load_facets()


def test_resolve_with_defaults():
    response = client.post("/resolve", json={"intent": _SAMPLE_INTENT})
    assert response.status_code == 200
    body = response.json()

    assert {"intent", "filters", "ranked_courses", "rationale", "parser_used"} <= set(body.keys())
    assert body["parser_used"] == "rule_based"

    # GoalType is a str Enum -- must serialize as its plain value, not an
    # Enum repr like "GoalType.JOB_READINESS".
    assert body["intent"]["goal_type"] == "job_readiness"
    assert isinstance(body["intent"]["goal_type"], str)

    facets = load_facets()
    checks = {
        "national_coordinator": facets["national_coordinator"],
        "course_mode": facets["course_mode"],
        "educational_level": facets["educational_level"],
        "industry_sector": facets["industry_sector"],
        "credits": facets["credits"],
        "category": facets["category"],
    }
    for field_name, taxonomy in checks.items():
        value = body["filters"].get(field_name)
        assert value is None or value in taxonomy

    if body["filters"].get("course_duration") is not None:
        valid_durations = {f"{w} Weeks" for w in facets["course_duration_weeks"]}
        assert body["filters"]["course_duration"] in valid_durations

    course_language_taxonomy = facets.get("course_language") or []
    if body["filters"].get("course_language") is not None:
        assert body["filters"]["course_language"] in course_language_taxonomy


def test_resolve_with_llm_parser_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.post(
        "/resolve",
        json={"intent": _SAMPLE_INTENT, "parser": "llm"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["goal_type"] in {
        "job_readiness",
        "exam_prep",
        "certification_credits",
        "skill_upgrade",
        "curiosity",
    }
    # No ANTHROPIC_API_KEY -> LLMIntentParser silently falls back internally;
    # parser_used must surface that rather than hiding it behind a plain 200.
    assert body["parser_used"] == "llm_fallback_rule_based"


def test_resolve_with_llm_parser_reports_llm_when_it_actually_ran(monkeypatch):
    # Patch the *class* minsky.api uses for both construction (LLMIntentParser())
    # and the isinstance() check inside _parser_used() -- a lambda wouldn't
    # work as isinstance()'s second argument.
    monkeypatch.setattr("minsky.api.LLMIntentParser", _StubLLMIntentParser)
    response = client.post(
        "/resolve",
        json={"intent": _SAMPLE_INTENT, "parser": "llm"},
    )
    assert response.status_code == 200
    assert response.json()["parser_used"] == "llm"


def test_resolve_with_local_llm_parser_reports_local_llm_when_it_actually_ran(monkeypatch):
    # Same pattern as test_resolve_with_llm_parser_reports_llm_when_it_actually_ran above,
    # but for parser: "local_llm" -- patches minsky.api.LLMIntentParser (not LocalGGUFClient
    # directly) so the default test suite never needs the real llama-cpp-python /
    # huggingface_hub packages or a real model download.
    monkeypatch.setattr("minsky.api.LLMIntentParser", _StubLLMIntentParser)
    response = client.post(
        "/resolve",
        json={"intent": _SAMPLE_INTENT, "parser": "local_llm"},
    )
    assert response.status_code == 200
    assert response.json()["parser_used"] == "local_llm"


class _StubLLMIntentParser:
    """Minimal stand-in that behaves as if the real LLM call succeeded.

    Used for both `parser: "llm"` and `parser: "local_llm"` -- `_build_coordinator()`
    constructs `LLMIntentParser(...)` for both, so patching the class covers either
    request's `_build_coordinator()` call once `minsky.api.LLMIntentParser` is patched.
    """

    def __init__(self, *args, **kwargs):
        self.last_backend = None

    def parse(self, raw_text):
        from minsky.agents.intent_parser import RuleBasedIntentParser

        intent = RuleBasedIntentParser().parse(raw_text)
        self.last_backend = "llm"
        return intent


@pytest.mark.parametrize("intent", ["", "   ", "\t\n"])
def test_resolve_rejects_blank_intent(intent):
    response = client.post("/resolve", json={"intent": intent})
    assert response.status_code in (400, 422)


def test_resolve_rejects_invalid_parser():
    response = client.post("/resolve", json={"intent": _SAMPLE_INTENT, "parser": "nonsense"})
    assert response.status_code == 422


def test_resolve_rejects_invalid_course_source():
    response = client.post(
        "/resolve", json={"intent": _SAMPLE_INTENT, "course_source": "nonsense"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("top_n", [0, 26, -1])
def test_resolve_rejects_top_n_out_of_range(top_n):
    response = client.post("/resolve", json={"intent": _SAMPLE_INTENT, "top_n": top_n})
    assert response.status_code == 422


@pytest.mark.skipif(
    os.environ.get("MINSKY_LIVE_TESTS") != "1",
    reason="hits live SWAYAM API",
)
def test_resolve_with_live_course_source():
    response = client.post(
        "/resolve", json={"intent": _SAMPLE_INTENT, "course_source": "live", "top_n": 3}
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["ranked_courses"], list)
