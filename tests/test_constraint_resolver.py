import pytest

from minsky.agents.constraint_resolver import ConstraintResolverAgent, load_facets
from minsky.schema import FilterSelection, GoalType, Intent


@pytest.fixture(scope="module")
def facets():
    return load_facets()


@pytest.fixture()
def resolver(facets):
    return ConstraintResolverAgent(facets)


def _assert_all_values_are_real_or_none(filters: FilterSelection, facets: dict) -> None:
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
        assert value is None or value in taxonomy, f"{field_name}={value!r} not in taxonomy"

    if filters.course_duration is not None:
        valid_durations = {f"{w} Weeks" for w in facets["course_duration_weeks"]}
        assert filters.course_duration in valid_durations


def test_duration_snaps_to_smallest_bucket_ge_target(resolver):
    intent = Intent(
        raw_text="anything",
        goal_type=GoalType.JOB_READINESS,
        topics=[],
        max_duration_weeks=11,
    )
    filters = resolver.resolve(intent)
    assert filters.course_duration == "12 Weeks"


def test_duration_falls_back_to_largest_bucket_when_over_max(resolver):
    intent = Intent(
        raw_text="anything",
        goal_type=GoalType.JOB_READINESS,
        topics=[],
        max_duration_weeks=100,
    )
    filters = resolver.resolve(intent)
    assert filters.course_duration == "24 Weeks"


def test_credits_true_maps_to_yes(resolver):
    intent = Intent(
        raw_text="anything",
        goal_type=GoalType.CERTIFICATION_CREDITS,
        topics=[],
        needs_credits=True,
    )
    filters = resolver.resolve(intent)
    assert filters.credits == "Yes"


def test_credits_none_stays_none(resolver):
    intent = Intent(raw_text="anything", goal_type=GoalType.CURIOSITY, topics=[])
    filters = resolver.resolve(intent)
    assert filters.credits is None


def test_industry_sector_fuzzy_snaps_to_real_taxonomy_value(resolver):
    intent = Intent(
        raw_text="anything",
        goal_type=GoalType.JOB_READINESS,
        topics=[],
        industry_sector="IT & ITES",  # exact taxonomy value already
    )
    filters = resolver.resolve(intent)
    assert filters.industry_sector == "IT & ITES"


def test_unrecognizable_hint_left_none_rather_than_invented(resolver):
    intent = Intent(
        raw_text="anything",
        goal_type=GoalType.CURIOSITY,
        topics=[],
        industry_sector="Completely Made Up Sector That Does Not Exist",
    )
    filters = resolver.resolve(intent)
    assert filters.industry_sector is None


def test_every_resolved_field_is_a_real_taxonomy_value_or_none(resolver, facets):
    intents = [
        Intent(
            raw_text="I want to become job-ready in data analytics within 3 months",
            goal_type=GoalType.JOB_READINESS,
            topics=["data analytics"],
            max_duration_weeks=12,
            industry_sector="IT & ITES",
        ),
        Intent(
            raw_text="I am an in-service teacher wanting ARPIT credits",
            goal_type=GoalType.CERTIFICATION_CREDITS,
            topics=["arpit", "teacher"],
            needs_credits=True,
            industry_sector="Education and Training",
        ),
        Intent(raw_text="I'm just curious", goal_type=GoalType.CURIOSITY, topics=[]),
    ]
    for intent in intents:
        filters = resolver.resolve(intent)
        _assert_all_values_are_real_or_none(filters, facets)


def test_resolve_raises_if_an_invalid_value_would_be_emitted(resolver, facets, monkeypatch):
    # Sanity-check the validation gate itself: force an invalid value through
    # and confirm resolve() refuses to return it silently.
    bad_facets = dict(facets)
    bad_facets["credits"] = ["Yes", "No"]
    resolver = ConstraintResolverAgent(bad_facets)

    def _bad_resolve_credits(_needs_credits):
        return "Maybe"

    monkeypatch.setattr(resolver, "_resolve_credits", _bad_resolve_credits)

    intent = Intent(raw_text="x", goal_type=GoalType.CURIOSITY, topics=[], needs_credits=True)
    with pytest.raises(ValueError):
        resolver.resolve(intent)
