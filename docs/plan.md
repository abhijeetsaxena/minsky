# Implementation Plan

## Scope (v1 — this milestone)

Prove the concept end-to-end on one concrete, real case: SWAYAM's course-catalog filters (see [case-study-swayam.md](case-study-swayam.md)).

In scope:
- `minsky.schema` — typed data model shared by all agents.
- Four agents + Coordinator (see [architecture.md](architecture.md)): Intent Parser (rule-based), Constraint Resolver, Outcome Ranker, Explainer.
- A synthetic-but-realistic course dataset (`data/sample_courses.json`) built from the real SWAYAM facet taxonomy (`data/swayam_facets.json`), so the demo is grounded without scraping/depending on live SWAYAM data.
- A CLI (`python -m minsky "<intent text>"`) that prints resolved filters, top-N ranked courses, and the rationale.
- Unit tests per agent + an integration test running the full pipeline.
- A golden-case evaluation harness (`eval/golden_cases.yaml` + `eval/run_eval.py`) — see [evaluation.md](evaluation.md).
- CI (GitHub Actions) running lint + tests + eval on every push/PR.

Out of scope for v1 (explicitly deferred, not forgotten):
- Any live integration with swayam.gov.in (scraping, API calls, auth) — v1 works against the synthetic dataset only.
- An HTTP API / browser extension / embeddable widget — natural Phase 2 once the core pipeline is validated, and only if there's a concrete consumer for it.
- `LLMIntentParser` (the pluggable LLM-backed alternative to the rule-based parser) — the interface is designed for it (see architecture.md's extension points) but no implementation ships in v1, to keep the default path dependency-free and CI runnable with no API key.
- Multi-portal generalization — v1 is scoped to SWAYAM's specific taxonomy; the resolver is designed to be retargetable, but retargeting itself is future work.

## Milestones

1. **Repo scaffold** — README, docs, `pyproject.toml`, `.gitignore`, LICENSE, CI workflow. *(this commit)*
2. **Schema + data** — `schema.py`, `data/swayam_facets.json` (real taxonomy), `data/sample_courses.json` (synthetic catalog).
3. **Agents** — implement Intent Parser, Constraint Resolver, Outcome Ranker, Explainer, Coordinator, each with unit tests.
4. **CLI** — thin entry point over the Coordinator.
5. **Evaluation harness** — golden cases + runnable eval script, wired into CI.
6. **Polish** — README usage examples, CONTRIBUTING notes if the repo gains outside contributors.

## Research findings (informing the above)

Framework and prior-art survey (full agent report, condensed):

- **Orchestration:** surveyed LangGraph, CrewAI, AG2/AutoGen, MetaGPT, CAMEL-AI, OpenAI Swarm — decision is to hand-roll a minimal orchestrator rather than adopt any of them; see [architecture.md](architecture.md#prior-art--alternatives-considered) for the reasoning and the CrewAI upgrade path if the project outgrows this.
- **Prior art:** CRSLab (conversational recommender task decomposition), Sparklis/EasyQuery/ln2sql (NL→structured-facet translation) are the closest existing work; none combine goal decomposition + constraint resolution + ranking + explanation the way minsky aims to.
- **Evaluation:** layered strategy — deterministic schema validation, then a golden intent→filter test set in CI (this is what v1 implements), with LLM-as-judge scoring for ranking/explanation quality deferred until the golden set stabilizes and an eval budget exists.

## Deploy approach

- Package as a normal installable Python package (`pip install -e .`), no hosting required for v1 — it's a library + CLI, not a service.
- GitHub Actions CI on every push/PR: lint (ruff) + `pytest` + `python -m eval.run_eval` (fails the build if golden-case accuracy drops below threshold).
- Versioned releases via git tags once the API (agent interfaces, `Coordinator.solve`) is stable enough to commit to; no release has been cut yet.
