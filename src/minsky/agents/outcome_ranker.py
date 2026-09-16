"""OutcomeRankerAgent: FilterSelection + catalog -> ranked list[RankedCourse].

Scoring is deliberately simple and fully explainable: +2 per resolved filter
field that matches the course, +1 per intent topic keyword found in the
course's title or keywords. This keeps ranking tied to the learner's
*original* goal (via intent.topics), not just the filters that were resolved
from it, per docs/architecture.md.
"""

from __future__ import annotations

from minsky.schema import Course, FilterSelection, Intent, RankedCourse

_FILTER_MATCH_SCORE = 2.0
_TOPIC_MATCH_SCORE = 1.0


class OutcomeRankerAgent:
    """Scores and ranks courses against resolved filters and the original intent."""

    def rank(
        self,
        filters: FilterSelection,
        courses: list[Course],
        intent: Intent,
        top_n: int = 5,
    ) -> list[RankedCourse]:
        ranked = [self._score(filters, course, intent) for course in courses]
        ranked.sort(key=lambda rc: rc.score, reverse=True)
        return ranked[:top_n]

    def _score(self, filters: FilterSelection, course: Course, intent: Intent) -> RankedCourse:
        score = 0.0
        reasons: list[str] = []

        if filters.national_coordinator and filters.national_coordinator == course.provider:
            score += _FILTER_MATCH_SCORE
            reasons.append(f"provider matches {filters.national_coordinator}")

        if filters.course_mode and filters.course_mode == course.mode:
            score += _FILTER_MATCH_SCORE
            reasons.append(f"mode matches {filters.course_mode}")

        if filters.course_duration:
            # duration match: the course fits within the resolved weeks bucket
            # (a course shorter than or equal to the cap still satisfies the
            # learner's time budget; an exact bucket match is a bonus signal
            # but not required).
            parsed_weeks = self._parse_weeks(filters.course_duration)
            if parsed_weeks is not None and course.duration_weeks <= parsed_weeks:
                score += _FILTER_MATCH_SCORE
                reasons.append(f"duration fits within {filters.course_duration}")

        if filters.educational_level and filters.educational_level == course.educational_level:
            score += _FILTER_MATCH_SCORE
            reasons.append(f"educational_level matches {filters.educational_level}")

        if filters.industry_sector and filters.industry_sector == course.industry_sector:
            score += _FILTER_MATCH_SCORE
            reasons.append(f"industry_sector matches {filters.industry_sector}")

        if filters.credits is not None:
            wants_credits = filters.credits == "Yes"
            if wants_credits == course.credits:
                score += _FILTER_MATCH_SCORE
                reasons.append(f"credits matches {filters.credits}")

        if filters.category and filters.category == course.category:
            score += _FILTER_MATCH_SCORE
            reasons.append(f"category matches {filters.category}")

        title_lower = course.title.lower()
        keywords_lower = [kw.lower() for kw in course.keywords]
        for topic in intent.topics:
            topic_lower = topic.lower()
            if topic_lower in title_lower:
                score += _TOPIC_MATCH_SCORE
                reasons.append(f"title mentions '{topic}'")
            elif any(topic_lower in kw for kw in keywords_lower):
                score += _TOPIC_MATCH_SCORE
                reasons.append(f"keywords mention '{topic}'")

        return RankedCourse(course=course, score=score, reasons=reasons)

    @staticmethod
    def _parse_weeks(course_duration: str) -> int | None:
        # course_duration is always built by ConstraintResolverAgent as "N Weeks"
        try:
            return int(course_duration.split()[0])
        except (ValueError, IndexError):
            return None
