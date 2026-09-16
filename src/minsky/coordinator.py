"""Coordinator: wires the agent pipeline together end-to-end.

The only class aware of the full pipeline (raw text -> Intent ->
FilterSelection -> ranked courses -> rationale) -- see docs/architecture.md.
Most callers (CLI, tests, a future API) should only need to import this.
"""

from __future__ import annotations

import json
from importlib import resources

from minsky.agents.constraint_resolver import ConstraintResolverAgent
from minsky.agents.explainer import ExplainerAgent
from minsky.agents.intent_parser import IntentParser, RuleBasedIntentParser
from minsky.agents.outcome_ranker import OutcomeRankerAgent
from minsky.schema import Course, ResolutionResult


def load_sample_courses() -> list[Course]:
    """Load the packaged synthetic course catalog (data/sample_courses.json)."""
    data_path = resources.files("minsky.data").joinpath("sample_courses.json")
    with data_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return [Course(**entry) for entry in raw]


class Coordinator:
    """Runs IntentParser -> ConstraintResolver -> OutcomeRanker -> Explainer in sequence."""

    def __init__(
        self,
        intent_parser: IntentParser | None = None,
        resolver: ConstraintResolverAgent | None = None,
        ranker: OutcomeRankerAgent | None = None,
        explainer: ExplainerAgent | None = None,
        courses: list[Course] | None = None,
    ) -> None:
        self.intent_parser = intent_parser if intent_parser is not None else RuleBasedIntentParser()
        self.resolver = resolver if resolver is not None else ConstraintResolverAgent()
        self.ranker = ranker if ranker is not None else OutcomeRankerAgent()
        self.explainer = explainer if explainer is not None else ExplainerAgent()
        self.courses = courses if courses is not None else load_sample_courses()

    def solve(self, raw_text: str, top_n: int = 5) -> ResolutionResult:
        intent = self.intent_parser.parse(raw_text)
        filters = self.resolver.resolve(intent)
        ranked_courses = self.ranker.rank(filters, self.courses, intent, top_n=top_n)
        rationale = self.explainer.explain(intent, filters, ranked_courses)
        return ResolutionResult(
            intent=intent,
            filters=filters,
            ranked_courses=ranked_courses,
            rationale=rationale,
        )
