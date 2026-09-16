from minsky.agents.constraint_resolver import load_facets
from minsky.coordinator import Coordinator
from minsky.schema import ResolutionResult

_TEST_INTENTS = [
    "I want to become job-ready in data analytics within 3 months",
    "I am an in-service teacher and want ARPIT credits for a refresher course",
    "I'm just curious about philosophy and ethics",
]


def _assert_filters_are_valid(filters, facets):
    checks = {
        "national_coordinator": facets["national_coordinator"],
        "course_mode": facets["course_mode"],
        "educational_level": facets["educational_level"],
        "industry_sector": facets["industry_sector"],
        "credits": facets["credits"],
        "category": facets["category"],
    }
    for field_name, taxonomy in checks.items():
        value = getattr(filters, field_name)
        assert value is None or value in taxonomy

    if filters.course_duration is not None:
        valid_durations = {f"{w} Weeks" for w in facets["course_duration_weeks"]}
        assert filters.course_duration in valid_durations


def test_full_pipeline_produces_valid_resolution_result():
    coordinator = Coordinator()
    facets = load_facets()

    for raw_text in _TEST_INTENTS:
        result = coordinator.solve(raw_text, top_n=3)

        assert isinstance(result, ResolutionResult)
        assert result.intent.raw_text == raw_text
        _assert_filters_are_valid(result.filters, facets)
        assert len(result.ranked_courses) > 0
        assert result.rationale.strip() != ""


def test_top_n_is_respected():
    coordinator = Coordinator()
    result = coordinator.solve(_TEST_INTENTS[0], top_n=2)
    assert len(result.ranked_courses) <= 2


def test_ranked_courses_are_sorted_descending():
    coordinator = Coordinator()
    result = coordinator.solve(_TEST_INTENTS[0], top_n=5)
    scores = [rc.score for rc in result.ranked_courses]
    assert scores == sorted(scores, reverse=True)
