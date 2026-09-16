"""ConstraintResolverAgent: Intent + real facet taxonomy -> FilterSelection.

The one hard rule this agent enforces: every non-None field it emits must be
a literal member of data/swayam_facets.json. Values are snapped onto the
taxonomy (bucketed for duration, fuzzy-matched via difflib for free-text
fields) rather than invented -- if nothing snaps closely enough, the field is
left None.
"""

from __future__ import annotations

import difflib
import json
import re
from importlib import resources

from minsky.schema import FilterSelection, Intent

# Minimum similarity ratio (see difflib.get_close_matches) required before we
# trust a fuzzy match onto the taxonomy. Below this we'd rather leave the
# field unset than emit a wrong-but-plausible-looking value.
_FUZZY_CUTOFF = 0.6

# Loose keyword -> real `category` taxonomy value, used only when we have
# some signal (goal type or topics) pointing at teaching/ARPIT.
_CATEGORY_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("arpit", "refresher"), "Annual Refresher Programme in Teaching (ARPIT)"),
    (("teacher", "teaching", "in-service"), "Teacher Education"),
    (("engineering", "software", "programming", "developer", "it"), "Engineering and Technology"),
    (("accounting", "finance", "commerce", "management"), "Management & Commerce"),
    (("health", "medical", "clinical", "nursing"), "Health Sciences"),
    (("maths", "math", "mathematics", "science", "physics", "chemistry"), "Maths & Sciences"),
    (("law", "legal"), "Law"),
    (("design",), "Design"),
    (("architecture", "planning"), "Architecture and Planning"),
)

# Fallback keyword-free mapping: if no direct category keyword hit but we
# did resolve an industry_sector, this gives category a sensible default
# (e.g. "data analytics job" -> industry_sector IT & ITES -> category
# Engineering and Technology, per docs/case-study-swayam.md's own example).
_SECTOR_TO_CATEGORY_FALLBACK: dict[str, str] = {
    "IT & ITES": "Engineering and Technology",
    "Healthcare": "Health Sciences",
    "Education and Training": "Teacher Education",
    "Accounting and Financial Services": "Management & Commerce",
}


def load_facets() -> dict:
    """Load the packaged SWAYAM facet taxonomy as a plain dict."""
    data_path = resources.files("minsky.data").joinpath("swayam_facets.json")
    with data_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class ConstraintResolverAgent:
    """Resolves an Intent into a FilterSelection valid against the real taxonomy."""

    def __init__(self, facets: dict | None = None) -> None:
        self.facets = facets if facets is not None else load_facets()

    def resolve(self, intent: Intent) -> FilterSelection:
        industry_sector = self._fuzzy_snap(intent.industry_sector, self.facets["industry_sector"])
        filters = FilterSelection(
            course_duration=self._resolve_duration(intent.max_duration_weeks),
            course_mode=self._fuzzy_snap(intent.preferred_mode, self.facets["course_mode"]),
            educational_level=self._fuzzy_snap(
                intent.educational_level, self.facets["educational_level"]
            ),
            industry_sector=industry_sector,
            credits=self._resolve_credits(intent.needs_credits),
            category=self._resolve_category(intent, industry_sector),
            national_coordinator=None,  # no learner-facing signal maps to this facet
            course_language=self._fuzzy_snap(
                intent.preferred_language, self.facets.get("course_language") or []
            ),
        )
        self._validate(filters)
        return filters

    # -- individual facet resolutions ---------------------------------------

    def _resolve_duration(self, max_weeks: int | None) -> str | None:
        if max_weeks is None:
            return None
        buckets: list[int] = sorted(self.facets["course_duration_weeks"])
        if not buckets:
            return None
        # snap to the smallest bucket that is >= the learner's cap, falling
        # back to the largest bucket if the cap exceeds every option.
        chosen = next((b for b in buckets if b >= max_weeks), buckets[-1])
        return f"{chosen} Weeks"

    def _resolve_credits(self, needs_credits: bool | None) -> str | None:
        if needs_credits is None:
            return None
        value = "Yes" if needs_credits else "No"
        return value if value in self.facets["credits"] else None

    def _resolve_category(self, intent: Intent, industry_sector: str | None) -> str | None:
        haystack = " ".join([intent.raw_text.lower(), *intent.topics])
        for keywords, category in _CATEGORY_HINTS:
            if any(
                re.search(rf"\b{re.escape(kw)}\b", haystack) for kw in keywords
            ) and category in self.facets["category"]:
                return category
        # no direct keyword hint -- fall back to a sector-implied category.
        if industry_sector is not None:
            fallback = _SECTOR_TO_CATEGORY_FALLBACK.get(industry_sector)
            if fallback is not None and fallback in self.facets["category"]:
                return fallback
        return None

    def _fuzzy_snap(self, value: str | None, taxonomy: list[str]) -> str | None:
        if not value or not taxonomy:
            return None
        if value in taxonomy:
            return value
        matches = difflib.get_close_matches(value, taxonomy, n=1, cutoff=_FUZZY_CUTOFF)
        return matches[0] if matches else None

    # -- correctness gate ------------------------------------------------------

    def _validate(self, filters: FilterSelection) -> None:
        """Assert every non-None field is a real taxonomy value.

        This is the hard correctness property described in
        docs/evaluation.md -- a resolved value that isn't a real SWAYAM
        option is a bug, not a quality judgment call, so we fail fast here.
        """
        checks = (
            ("national_coordinator", filters.national_coordinator, self.facets["national_coordinator"]),
            ("course_mode", filters.course_mode, self.facets["course_mode"]),
            ("educational_level", filters.educational_level, self.facets["educational_level"]),
            ("industry_sector", filters.industry_sector, self.facets["industry_sector"]),
            ("credits", filters.credits, self.facets["credits"]),
            ("category", filters.category, self.facets["category"]),
        )
        for field_name, value, taxonomy in checks:
            if value is not None and value not in taxonomy:
                raise ValueError(
                    f"ConstraintResolverAgent produced an invalid value for "
                    f"{field_name!r}: {value!r} is not in the taxonomy"
                )
        if filters.course_duration is not None:
            valid_durations = {f"{w} Weeks" for w in self.facets["course_duration_weeks"]}
            if filters.course_duration not in valid_durations:
                raise ValueError(
                    f"ConstraintResolverAgent produced an invalid course_duration: "
                    f"{filters.course_duration!r}"
                )
        course_language_taxonomy = self.facets.get("course_language") or []
        if filters.course_language is not None and filters.course_language not in course_language_taxonomy:
            raise ValueError(
                f"ConstraintResolverAgent produced an invalid course_language: "
                f"{filters.course_language!r}"
            )
