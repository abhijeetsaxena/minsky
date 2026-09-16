"""IntentParserAgent: free text -> Intent.

Ships one implementation, `RuleBasedIntentParser`, built on keyword/regex
heuristics only -- no network, no external deps, fully deterministic. This is
the interface an `LLMIntentParser` would later implement (see
docs/architecture.md's extension points); v1 does not ship that backend.
"""

from __future__ import annotations

import re
from typing import Protocol

from minsky.schema import GoalType, Intent

# --- goal type keyword tables, checked in this priority order -------------

_JOB_READINESS_PHRASES = ("job-ready", "job ready", "job", "career", "hire", "hireable")
_EXAM_PREP_PHRASES = ("exam", "gate", "prepare for", "entrance test", "entrance exam")
_CREDIT_PHRASES = ("credit", "certificate for", "degree")
_SKILL_UPGRADE_PHRASES = ("teacher", "upskill", "up-skill", "refresh", "in-service")

# --- duration -----------------------------------------------------------

_MONTH_RE = re.compile(r"(\d+)\s*(?:month|months|mo)\b")
_WEEK_RE = re.compile(r"(\d+)\s*(?:week|weeks|wk)\b")

# --- mode -----------------------------------------------------------------

_SELF_PACED_PHRASES = ("self paced", "self-paced", "flexible")
_REGULAR_PHRASES = ("regular", "cohort", "live")

# --- credits ----------------------------------------------------------------

_CREDIT_NEED_PHRASES = ("credit", "credits", "degree credit")

# --- educational level cues, ordered most-specific first -------------------

_EDU_LEVEL_PHRASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("phd", "doctoral", "post-doctoral", "postdoctoral"), "Doctoral / Post-Doctoral"),
    (("postgraduate", "post graduate", "pg student", "masters"), "PG-Year 1"),
    (
        ("undergraduate", "under graduate", "ug student", "bachelor", "college student"),
        "UG-Year 1",
    ),
    (("senior secondary", "12th", "class 12", "higher secondary"), "Senior Secondary"),
    (("school student", "school", "secondary school"), "Up to Secondary School"),
)

# --- industry sector hints: keyword -> real swayam_facets.json value ------

_INDUSTRY_SECTOR_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("data", "analytics", "software", "programming", "developer", "it", "tech", "coding"),
        "IT & ITES",
    ),
    (("teacher", "school", "education", "teaching"), "Education and Training"),
    (("finance", "accounting", "accountant", "financial"), "Accounting and Financial Services"),
    (("health", "medical", "clinical", "nursing", "hospital"), "Healthcare"),
)

# --- topic extraction -------------------------------------------------------

# Curated multi-word domain terms, checked as substrings before falling back
# to single-token extraction. Longer/more-specific phrases first so e.g.
# "data analytics" wins over a bare "data".
_CURATED_TOPICS = (
    "data analytics",
    "data science",
    "machine learning",
    "artificial intelligence",
    "web development",
    "cloud computing",
    "cyber security",
    "cybersecurity",
    "digital marketing",
    "financial accounting",
    "cost accounting",
    "clinical research",
    "civil engineering",
    "electrical engineering",
    "python programming",
    "teacher training",
    "gate exam",
    "gate preparation",
)

_STOPWORDS = {
    "i",
    "a",
    "an",
    "the",
    "to",
    "in",
    "of",
    "for",
    "and",
    "or",
    "want",
    "wants",
    "wanting",
    "would",
    "like",
    "become",
    "get",
    "getting",
    "within",
    "next",
    "my",
    "me",
    "as",
    "am",
    "is",
    "are",
    "be",
    "with",
    "on",
    "job",
    "ready",
    "job-ready",
    "career",
    "months",
    "month",
    "weeks",
    "week",
    "course",
    "courses",
    "some",
    "something",
    "need",
    "needs",
    "looking",
    "who",
    "that",
    "this",
    "so",
    "can",
    "i'm",
    "im",
    "working",
    "professional",
}

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z+-]*")


class IntentParser(Protocol):
    """Strategy interface: free text -> Intent."""

    def parse(self, raw_text: str) -> Intent: ...


class RuleBasedIntentParser:
    """Deterministic, dependency-free IntentParser backed by keyword/regex rules."""

    def parse(self, raw_text: str) -> Intent:
        text = raw_text.lower()

        goal_type = self._infer_goal_type(text)
        max_duration_weeks = self._infer_duration_weeks(text)
        preferred_mode = self._infer_mode(text)
        needs_credits = self._infer_needs_credits(text)
        educational_level = self._infer_educational_level(text)
        topics = self._infer_topics(text)
        industry_sector = self._infer_industry_sector(text, topics)

        confidence = self._infer_confidence(
            max_duration_weeks=max_duration_weeks,
            preferred_mode=preferred_mode,
            industry_sector=industry_sector,
        )

        return Intent(
            raw_text=raw_text,
            goal_type=goal_type,
            topics=topics,
            max_duration_weeks=max_duration_weeks,
            preferred_mode=preferred_mode,
            preferred_language=None,
            needs_credits=needs_credits,
            educational_level=educational_level,
            industry_sector=industry_sector,
            confidence=confidence,
        )

    # -- individual inference steps, kept small and independently testable --

    @staticmethod
    def _infer_goal_type(text: str) -> GoalType:
        if any(p in text for p in _JOB_READINESS_PHRASES):
            return GoalType.JOB_READINESS
        if any(p in text for p in _EXAM_PREP_PHRASES):
            return GoalType.EXAM_PREP
        if any(p in text for p in _CREDIT_PHRASES):
            return GoalType.CERTIFICATION_CREDITS
        if any(p in text for p in _SKILL_UPGRADE_PHRASES):
            return GoalType.SKILL_UPGRADE
        return GoalType.CURIOSITY

    @staticmethod
    def _infer_duration_weeks(text: str) -> int | None:
        month_match = _MONTH_RE.search(text)
        if month_match:
            return round(int(month_match.group(1)) * 4)
        week_match = _WEEK_RE.search(text)
        if week_match:
            return int(week_match.group(1))
        return None

    @staticmethod
    def _infer_mode(text: str) -> str | None:
        if any(p in text for p in _SELF_PACED_PHRASES):
            return "Self Paced"
        if any(p in text for p in _REGULAR_PHRASES):
            return "Regular"
        return None

    @staticmethod
    def _infer_needs_credits(text: str) -> bool | None:
        if any(p in text for p in _CREDIT_NEED_PHRASES):
            return True
        return None

    @staticmethod
    def _infer_educational_level(text: str) -> str | None:
        for phrases, level in _EDU_LEVEL_PHRASES:
            if any(p in text for p in phrases):
                return level
        return None

    @staticmethod
    def _infer_topics(text: str) -> list[str]:
        topics: list[str] = []
        remaining = text
        for phrase in _CURATED_TOPICS:
            if phrase in remaining:
                topics.append(phrase)
                remaining = remaining.replace(phrase, " ")

        # Fallback: single non-stopword tokens not already covered above.
        for token in _WORD_RE.findall(remaining):
            lower = token.lower()
            if len(lower) < 3 or lower in _STOPWORDS:
                continue
            if lower not in topics:
                topics.append(lower)

        return topics

    @staticmethod
    def _infer_industry_sector(text: str, topics: list[str]) -> str | None:
        for keywords, sector in _INDUSTRY_SECTOR_HINTS:
            if any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in keywords):
                return sector
        # also check curated/extracted topics directly, in case the raw text
        # phrasing didn't literally contain a hint keyword
        for topic in topics:
            for keywords, sector in _INDUSTRY_SECTOR_HINTS:
                if any(re.search(rf"\b{re.escape(kw)}\b", topic) for kw in keywords):
                    return sector
        return None

    @staticmethod
    def _infer_confidence(
        *,
        max_duration_weeks: int | None,
        preferred_mode: str | None,
        industry_sector: str | None,
    ) -> float:
        # Penalize a bit for each optional signal we couldn't infer; this is
        # a coarse heuristic used for downstream explanation, not enforced.
        penalty = 0.0
        for value in (max_duration_weeks, preferred_mode, industry_sector):
            if value is None:
                penalty += 0.15
        return max(0.3, round(1.0 - penalty, 2))
