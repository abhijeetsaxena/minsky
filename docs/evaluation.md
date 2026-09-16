# Evaluation & Validation

Layered strategy (cheapest/most reliable checks first), per the framework survey in [plan.md](plan.md#research-findings):

## 1. Deterministic schema validation

Every `FilterSelection` the Constraint Resolver emits is checked against the real facet taxonomy in `data/swayam_facets.json` — a resolved value that isn't one of the real SWAYAM options is a hard bug, not a quality judgment call. This runs as a plain assertion inside `ConstraintResolverAgent` itself (fail fast) and again as a pytest check.

## 2. Golden intent → expected-filter test set

`eval/golden_cases.yaml` holds ~15-20 hand-written realistic learner intents (job seeker, in-service teacher upskilling via ARPIT, exam-prep student, credit-seeking degree student, hobbyist), each with the subset of filter keys we're confident about as `expected_filters`. `eval/run_eval.py`:

- Runs the full Coordinator pipeline on each case's raw intent text.
- Compares only the keys present in `expected_filters` (a case doesn't have to assert every facet — some are genuinely ambiguous and that's fine).
- Reports per-case pass/fail and an aggregate accuracy percentage.
- Exits non-zero if accuracy drops below a threshold (default 70%), so CI catches regressions.

This is free, deterministic, and fast enough to run on every PR — it's the primary regression gate for v1.

## 3. LLM-as-judge (deferred)

Ranking quality and explanation quality don't have one "correct" answer, which is where an LLM-as-judge rubric would eventually help (score 1-5: "does the explanation correctly justify each selected filter given the stated intent"). **Not implemented in v1** — deferred until the golden set stabilizes and there's a judge-model budget, per the research findings. When added, it should run as an optional CI job that's skippable without an API key, so the deterministic checks remain the required gate.

## 4. Human spot-check

Once the tool has real users, periodically sample resolved intents (especially ones flagged low-confidence by the Intent Parser) for manual review — both to catch cases the golden set doesn't cover and to calibrate any future LLM judge against human judgment.

## Running the eval locally

```bash
python -m eval.run_eval
```

Runs entirely offline against the rule-based parser and the synthetic dataset — no API key or network access required.
