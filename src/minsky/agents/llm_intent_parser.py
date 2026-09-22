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

from minsky.agents.constraint_resolver import load_facets
from minsky.agents.intent_parser import IntentParser, RuleBasedIntentParser
from minsky.schema import GoalType, Intent

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def _build_system_prompt() -> str:
    """Build the extraction prompt from the real SWAYAM facet taxonomy.

    `educational_level`/`industry_sector` are posed as a closed choice from
    the actual taxonomy values rather than open freeform text. This was
    measured (see docs/local-llm.md) to take a small local model's accuracy
    on the golden-case eval from 47% to 93% -- ConstraintResolverAgent's
    fuzzy-matcher can't reliably bridge a model's loose paraphrase (e.g.
    "IT") onto the real value ("IT & ITES"), but a model asked to choose
    from the explicit list gets it right far more often. This is a strict
    improvement for any backend, not a local-model-specific hack, so both
    AnthropicLLMClient and a local GGUF client share this one prompt.
    """
    facets = load_facets()
    sectors = ", ".join(f'"{s}"' for s in facets["industry_sector"])
    levels = ", ".join(f'"{s}"' for s in facets["educational_level"])
    return f"""\
You extract a structured "learning intent" from a learner's free-text goal.

Respond with ONLY a single JSON object -- no prose, no explanation, no \
markdown code fence -- with exactly these keys:

- "goal_type": one of "job_readiness", "exam_prep", "certification_credits", \
"skill_upgrade", "curiosity"
- "topics": array of short strings naming the subject(s) the learner wants \
to study
- "max_duration_weeks": integer number of WEEKS the learner is willing to \
spend, or null if not stated. Always convert: 1 month = 4 weeks \
(e.g. "3 months" -> 12, "6 weeks" -> 6).
- "preferred_mode": "Self Paced", "Regular", or null if not stated
- "preferred_language": string language name, or null if not stated
- "needs_credits": true, false, or null if not stated
- "educational_level": pick the SINGLE closest matching value EXACTLY as \
written from this list: [{levels}], or null if nothing fits.
- "industry_sector": pick the SINGLE closest matching value EXACTLY as \
written from this list: [{sectors}], or null if nothing fits. Infer the \
sector even if not explicitly named -- e.g. "software"/"data"/"programming"/\
"machine learning" -> "IT & ITES"; "teacher"/"teaching"/"school" -> \
"Education and Training"; "accounting"/"financial"/"banking" -> \
"Accounting and Financial Services"; "clinical"/"health"/"medical" -> \
"Healthcare".
- "confidence": your own self-rated confidence in this extraction, a float \
between 0 and 1

Output ONLY the JSON object, no other text.
"""


_SYSTEM_PROMPT = _build_system_prompt()

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
    """`IntentParser` backed by an LLM, with graceful fallback on any failure.

    `last_backend` records which path the most recent `.parse()` call actually
    took ("llm" or "fallback") -- since the fallback is silent by design (see
    `.parse()`'s docstring below), callers who need to know whether the LLM
    call actually succeeded (e.g. the HTTP API's `parser_used` response field)
    can inspect this after calling `.parse()`, rather than that fact being
    unobservable from the outside.
    """

    def __init__(self, client: LLMClient | None = None, fallback: IntentParser | None = None) -> None:
        self.client = client if client is not None else AnthropicLLMClient()
        self.fallback = fallback if fallback is not None else RuleBasedIntentParser()
        self.last_backend: str | None = None

    def parse(self, raw_text: str) -> Intent:
        try:
            raw_response = self.client.complete(system=_SYSTEM_PROMPT, user=raw_text)
            intent = self._parse_response(raw_text, raw_response)
        except Exception:  # noqa: BLE001 -- intentional: any LLM/parsing failure degrades gracefully
            # Any failure whatsoever -- missing key, network error, rate
            # limit, malformed JSON, invalid field values -- degrades to the
            # fallback parser rather than crashing the pipeline.
            self.last_backend = "fallback"
            return self.fallback.parse(raw_text)
        self.last_backend = "llm"
        return intent

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
