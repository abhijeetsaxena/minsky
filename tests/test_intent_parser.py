from minsky.agents.intent_parser import RuleBasedIntentParser
from minsky.schema import GoalType


def test_job_readiness_data_analytics_intent():
    parser = RuleBasedIntentParser()
    intent = parser.parse("I want to become job-ready in data analytics within 3 months")

    assert intent.goal_type == GoalType.JOB_READINESS
    assert intent.max_duration_weeks == 12
    assert intent.industry_sector == "IT & ITES"
    assert "data analytics" in intent.topics


def test_exam_prep_intent():
    parser = RuleBasedIntentParser()
    intent = parser.parse("I need to prepare for GATE exam in electrical engineering")

    assert intent.goal_type == GoalType.EXAM_PREP


def test_skill_upgrade_teacher_intent():
    parser = RuleBasedIntentParser()
    intent = parser.parse("I want to upskill as a school teacher in teaching methods")

    assert intent.goal_type == GoalType.SKILL_UPGRADE
    assert intent.industry_sector == "Education and Training"


def test_certification_credits_intent():
    parser = RuleBasedIntentParser()
    intent = parser.parse("I want a certificate for financial accounting as a working professional")

    assert intent.goal_type == GoalType.CERTIFICATION_CREDITS
    assert intent.industry_sector == "Accounting and Financial Services"


def test_curiosity_fallback_intent():
    parser = RuleBasedIntentParser()
    intent = parser.parse("I'm just curious about philosophy and ethics")

    assert intent.goal_type == GoalType.CURIOSITY
    assert intent.max_duration_weeks is None
    assert intent.industry_sector is None


def test_week_duration_parsed_directly():
    parser = RuleBasedIntentParser()
    intent = parser.parse("I want a course under 8 weeks in web development")

    assert intent.max_duration_weeks == 8


def test_self_paced_mode_detected():
    parser = RuleBasedIntentParser()
    intent = parser.parse("I want a flexible self-paced course in digital marketing")

    assert intent.preferred_mode == "Self Paced"


def test_regular_mode_and_credits_detected():
    parser = RuleBasedIntentParser()
    intent = parser.parse("I want a long regular mode course with credits in banking and finance")

    assert intent.preferred_mode == "Regular"
    assert intent.needs_credits is True


def test_confidence_is_lower_for_vague_intent():
    parser = RuleBasedIntentParser()
    vague = parser.parse("I want to explore something new, no specific goal in mind")
    specific = parser.parse("I want to become job-ready in data analytics within 3 months")

    assert vague.confidence <= specific.confidence
    assert 0.3 <= vague.confidence <= 1.0
