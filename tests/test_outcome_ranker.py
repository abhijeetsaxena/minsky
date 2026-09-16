from minsky.agents.outcome_ranker import OutcomeRankerAgent
from minsky.schema import Course, FilterSelection, GoalType, Intent


def _course(**overrides) -> Course:
    defaults = {
        "id": "c1",
        "title": "Generic Course",
        "provider": "NPTEL",
        "mode": "Self Paced",
        "duration_weeks": 8,
        "language": "English",
        "educational_level": "UG-Year 1",
        "industry_sector": "IT & ITES",
        "credits": True,
        "category": "Engineering and Technology",
        "keywords": [],
    }
    defaults.update(overrides)
    return Course(**defaults)


def test_more_matching_course_ranks_first():
    ranker = OutcomeRankerAgent()
    filters = FilterSelection(industry_sector="IT & ITES", course_mode="Self Paced")
    intent = Intent(
        raw_text="I want data analytics",
        goal_type=GoalType.JOB_READINESS,
        topics=["data analytics"],
    )

    strong_match = _course(
        id="strong",
        title="Data Analytics for Beginners",
        mode="Self Paced",
        industry_sector="IT & ITES",
        keywords=["data analytics", "python"],
    )
    weak_match = _course(
        id="weak",
        title="Unrelated Humanities Course",
        mode="Regular",
        industry_sector="Healthcare",
        keywords=["philosophy"],
    )

    ranked = ranker.rank(filters, [weak_match, strong_match], intent, top_n=5)

    assert ranked[0].course.id == "strong"
    assert ranked[0].score > ranked[1].score
    assert any("data analytics" in reason for reason in ranked[0].reasons)


def test_returns_courses_even_with_zero_score_when_below_top_n():
    ranker = OutcomeRankerAgent()
    filters = FilterSelection()
    intent = Intent(raw_text="nothing in particular", goal_type=GoalType.CURIOSITY, topics=[])

    courses = [_course(id="a"), _course(id="b")]
    ranked = ranker.rank(filters, courses, intent, top_n=5)

    assert len(ranked) == 2
    assert all(rc.score == 0 for rc in ranked)


def test_duration_match_uses_le_semantics():
    ranker = OutcomeRankerAgent()
    filters = FilterSelection(course_duration="12 Weeks")
    intent = Intent(raw_text="x", goal_type=GoalType.CURIOSITY, topics=[])

    fits = _course(id="fits", duration_weeks=8)
    too_long = _course(id="too_long", duration_weeks=24)

    ranked = ranker.rank(filters, [too_long, fits], intent, top_n=5)

    assert ranked[0].course.id == "fits"
    assert ranked[0].score > ranked[1].score
