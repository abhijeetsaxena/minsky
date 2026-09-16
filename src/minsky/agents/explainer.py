"""ExplainerAgent: assembles a plain-language rationale for a resolution.

This is the transparency layer SWAYAM's own filter UI lacks (see
docs/case-study-swayam.md) -- a learner should be able to read this and
correct a wrong inference, not just see a bare result grid.
"""

from __future__ import annotations

from minsky.schema import FilterSelection, Intent, RankedCourse

_FILTER_LABELS = {
    "national_coordinator": "National Coordinator",
    "course_mode": "Course Mode",
    "course_duration": "Course Duration",
    "course_language": "Course Language",
    "educational_level": "Educational Level",
    "industry_sector": "Industry/Sector",
    "credits": "Course Credits",
    "category": "Category",
}


class ExplainerAgent:
    """Turns an Intent + FilterSelection + ranked courses into readable text."""

    def explain(
        self,
        intent: Intent,
        filters: FilterSelection,
        ranked: list[RankedCourse],
    ) -> str:
        lines: list[str] = []

        lines.append("What I understood from your goal:")
        lines.append(f'  "{intent.raw_text.strip()}"')
        lines.append(f"  - Goal type: {intent.goal_type.value.replace('_', ' ')}")
        if intent.topics:
            lines.append(f"  - Topics: {', '.join(intent.topics)}")
        lines.append(f"  - Confidence in this reading: {intent.confidence:.0%}")
        lines.append("")

        resolved = self._non_none_filters(filters)
        lines.append("Filters I resolved against the real SWAYAM taxonomy:")
        if resolved:
            for key, value in resolved.items():
                label = _FILTER_LABELS.get(key, key)
                lines.append(f"  - {label}: {value}")
        else:
            lines.append("  - (not enough signal to narrow any facet confidently -- showing a broad shortlist)")
        lines.append("")

        if ranked:
            top = ranked[0]
            lines.append(f"Top match: {top.course.title} (score {top.score:g})")
            if top.reasons:
                lines.append("  Why this course:")
                for reason in top.reasons:
                    lines.append(f"    - {reason}")
            else:
                lines.append("  No strong signal matched this course specifically; it's a broad top pick.")
        else:
            lines.append("No courses matched -- try broadening your intent.")

        return "\n".join(lines)

    @staticmethod
    def _non_none_filters(filters: FilterSelection) -> dict[str, str]:
        return {
            key: value
            for key, value in vars(filters).items()
            if value is not None
        }
