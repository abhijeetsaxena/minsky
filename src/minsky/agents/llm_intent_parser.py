"""LLMIntentParser: free text -> Intent, backed by an LLM instead of rules.

This is the LLM-backed counterpart to `RuleBasedIntentParser`
(see intent_parser.py): same `IntentParser` protocol, but delegates the
free-text -> Intent extraction to a language model for better recall on
phrasing the deterministic rules miss.

Design goals:
- `LLMClient` is a narrow Protocol (system + user prompt in, text out) so
  this module never hard-codes a specific SDK into the rest of the pipeline.
- The `anthropic` package is imported lazily, so this module -- and any
  pipeline that only uses `RuleBasedIntentParser` -- stays fully importable
  and usable even when `anthropic` isn't installed at all.
- `LLMIntentParser.parse()` never raises. Any failure (missing package,
  missing API key, network error, malformed/invalid model output) is caught
  and silently degrades to a fallback `IntentParser` (by default
  `RuleBasedIntentParser`). This mirrors the "prefer no answer over a wrong
  one" philosophy already used by `ConstraintResolverAgent`, which leaves
  fields `None` rather than guessing -- here it means falling back to the
  deterministic parser rather than crashing or returning garbage.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from minsky.agents.intent_parser import IntentParser, RuleBasedIntentParser
from minsky.schema import GoalType, Intent

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You extract a structured "learning intent" from a learner's free-text goal.

Respond with ONLY a single JSON object -- no prose, no explanation, no \
markdown code fence -- with exactly these keys:

- "goal_type": one of "job_readiness", "exam_prep", "certification_credits", \
"skill_upgrade", "curiosity"
- "topics": array of short strings naming the subject(s) the learner wants \
to study
- "max_duration_weeks": integer number of weeks the learner is willing to \
spend, or null if not stated
- "preferred_mode": "Self Paced", "Regular", or null if not stated
- "preferred_language": string language name, or null if not stated
- "needs_credits": true, false, or null if not stated
- "educational_level": freeform string describing the learner's current \
educational level (e.g. "undergraduate"), or null if not stated
- "industry_sector": freeform string naming the industry/sector the intent \
relates to (e.g. "IT"), or null if not stated
- "confidence": your own self-rated confidence in this extraction, a float \
between 0 and 1

Output ONLY the JSON object.
"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

_VALID_MODES = {"Self Paced", "Regular"}


class LLMClient(Protocol):
    """Narrow interface: system + user prompt in, raw text response out.

    Kept deliberately minimal so `LLMIntentParser` doesn't depend on any
    specific LLM SDK -- only on something that can complete a prompt.
    """

    def complete(self, *, system: str, user: str) -> str: ...


class AnthropicLLMClient:
    """`LLMClient` backed by the Anthropic Messages API.

    The `anthropic` package is imported lazily (only when this client is
    actually used), and the API key is only required at `.complete()` time --
    neither missing dependency crashes import or construction of this class.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("MINSKY_LLM_MODEL") or _DEFAULT_MODEL

    def complete(self, *, system: str, user: str) -> str:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "AnthropicLLMClient requires the 'anthropic' package -- install it "
                "(this will become the 'llm' extra)."
            ) from exc

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "AnthropicLLMClient requires the ANTHROPIC_API_KEY environment "
                "variable to be set."
            )

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )


class LLMIntentParser:
    """`IntentParser` backed by an LLM, with graceful fallback on any failure."""

    def __init__(self, client: LLMClient | None = None, fallback: IntentParser | None = None) -> None:
        self.client = client if client is not None else AnthropicLLMClient()
        self.fallback = fallback if fallback is not None else RuleBasedIntentParser()

    def parse(self, raw_text: str) -> Intent:
        try:
            raw_response = self.client.complete(system=_SYSTEM_PROMPT, user=raw_text)
            return self._parse_response(raw_text, raw_response)
        except Exception:  # noqa: BLE001 -- intentional: any LLM/parsing failure degrades gracefully
            # Any failure whatsoever -- missing key, network error, rate
            # limit, malformed JSON, invalid field values -- degrades to the
            # fallback parser rather than crashing the pipeline.
            return self.fallback.parse(raw_text)

    # -- response parsing / validation --------------------------------------

    def _parse_response(self, raw_text: str, raw_response: str) -> Intent:
        payload = json.loads(_strip_fence(raw_response))
        if not isinstance(payload, dict):
            raise TypeError("LLM response is not a JSON object")

        return Intent(
            raw_text=raw_text,
            goal_type=_coerce_goal_type(payload.get("goal_type")),
            topics=_coerce_topics(payload.get("topics")),
            max_duration_weeks=_coerce_optional_int(payload.get("max_duration_weeks")),
            preferred_mode=_coerce_mode(payload.get("preferred_mode")),
            preferred_language=_coerce_optional_str(payload.get("preferred_language")),
            needs_credits=_coerce_optional_bool(payload.get("needs_credits")),
            educational_level=_coerce_optional_str(payload.get("educational_level")),
            industry_sector=_coerce_optional_str(payload.get("industry_sector")),
            confidence=_coerce_confidence(payload.get("confidence")),
        )


# -- defensive coercion/validation helpers ----------------------------------
#
# Each of these raises on anything unexpected; `LLMIntentParser.parse()`
# catches broadly and falls back, so these are intentionally strict rather
# than lenient.


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    return match.group(1) if match else stripped


def _coerce_goal_type(value: object) -> GoalType:
    if not isinstance(value, str):
        raise TypeError(f"goal_type must be a string, got {value!r}")
    normalized = value.strip().lower()
    for member in GoalType:
        if member.value == normalized:
            return member
    raise ValueError(f"goal_type {value!r} is not a valid GoalType")


def _coerce_topics(value: object) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"topics must be a list, got {value!r}")
    topics: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"topics must be a list of strings, got {item!r}")
        topics.append(item)
    return topics


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):  # bool is an int subclass -- reject explicitly
        raise TypeError(f"expected int or null, got bool {value!r}")
    if isinstance(value, int):
        return value
    raise TypeError(f"expected int or null, got {value!r}")


def _coerce_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise TypeError(f"expected bool or null, got {value!r}")


def _coerce_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError(f"expected string or null, got {value!r}")


def _coerce_mode(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value in _VALID_MODES:
        return value
    raise ValueError(f"preferred_mode must be one of {_VALID_MODES} or null, got {value!r}")


def _coerce_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"confidence must be a number, got {value!r}")
    return max(0.0, min(1.0, float(value)))
