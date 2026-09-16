"""Thin CLI entry point over Coordinator. Usage: python -m minsky "<intent text>"."""

from __future__ import annotations

import argparse
import sys

from minsky.coordinator import Coordinator
from minsky.schema import FilterSelection

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minsky",
        description=(
            "Turn a free-text learner intent into resolved SWAYAM filters, "
            "a ranked course shortlist, and a plain-language explanation."
        ),
    )
    parser.add_argument(
        "intent",
        nargs="+",
        help="the learner's intent, e.g. minsky I want to become job-ready in data analytics",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="number of ranked courses to show (default: 3)",
    )
    return parser


def _print_filters(filters: FilterSelection) -> None:
    non_none = {k: v for k, v in vars(filters).items() if v is not None}
    if not non_none:
        print("  (none resolved confidently)")
        return
    for key, value in non_none.items():
        print(f"  - {_FILTER_LABELS.get(key, key)}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    raw_text = " ".join(args.intent)

    coordinator = Coordinator()
    result = coordinator.solve(raw_text, top_n=args.top_n)

    print("Intent")
    print(f"  Raw text: {result.intent.raw_text}")
    print(f"  Goal type: {result.intent.goal_type.value}")
    print(f"  Topics: {', '.join(result.intent.topics) if result.intent.topics else '(none detected)'}")
    print(f"  Confidence: {result.intent.confidence:.0%}")
    print()

    print("Resolved filters")
    _print_filters(result.filters)
    print()

    print(f"Top {len(result.ranked_courses)} ranked courses")
    for rank, ranked_course in enumerate(result.ranked_courses, start=1):
        course = ranked_course.course
        print(f"  {rank}. {course.title} [{course.provider}] -- score {ranked_course.score:g}")
        for reason in ranked_course.reasons:
            print(f"       - {reason}")
    print()

    print("Rationale")
    print(result.rationale)

    return 0


if __name__ == "__main__":
    sys.exit(main())
