"""Typed data model shared by all minsky agents.

See docs/architecture.md for how these types flow through the pipeline:
raw text -> Intent -> FilterSelection -> list[RankedCourse] -> ResolutionResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GoalType(str, Enum):
    """The learner's high-level motivation, inferred from free text."""

    JOB_READINESS = "job_readiness"
    EXAM_PREP = "exam_prep"
    CERTIFICATION_CREDITS = "certification_credits"
    SKILL_UPGRADE = "skill_upgrade"
    CURIOSITY = "curiosity"


@dataclass
class Intent:
    """Structured representation of a learner's free-text goal.

    Produced by an IntentParser. Fields beyond `raw_text` and `goal_type` are
    best-effort hints; `None` means "not stated / not confidently inferred",
    never "explicitly excluded".
    """

    raw_text: str
    goal_type: GoalType
    topics: list[str]
    max_duration_weeks: int | None = None
    preferred_mode: str | None = None
    preferred_language: str | None = None
    needs_credits: bool | None = None
    educational_level: str | None = None
    industry_sector: str | None = None
    confidence: float = 1.0


@dataclass
class FilterSelection:
    """A selection across SWAYAM's nine facets.

    Every non-None value here must be a literal member of the taxonomy in
    data/swayam_facets.json -- ConstraintResolverAgent enforces this.
    """

    national_coordinator: str | None = None
    course_mode: str | None = None
    course_duration: str | None = None
    course_language: str | None = None
    educational_level: str | None = None
    industry_sector: str | None = None
    credits: str | None = None
    category: str | None = None


@dataclass
class Course:
    """One catalog entry (synthetic in v1, see data/sample_courses.json).

    `url` defaults to "" for the synthetic catalog (which has none); the
    live SwayamClient always populates it with a real, clickable course link.
    """

    id: str
    title: str
    provider: str
    mode: str
    duration_weeks: int
    language: str
    educational_level: str
    industry_sector: str
    credits: bool
    category: str
    keywords: list[str] = field(default_factory=list)
    url: str = ""


@dataclass
class RankedCourse:
    """A course annotated with its score and the reasons behind it."""

    course: Course
    score: float
    reasons: list[str]


@dataclass
class ResolutionResult:
    """The full output of one Coordinator.solve() call."""

    intent: Intent
    filters: FilterSelection
    ranked_courses: list[RankedCourse]
    rationale: str
