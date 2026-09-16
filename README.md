# minsky

**Society of Minds.** Agents are distributed, task-specific, self-organizing entities leading to intelligence.

## What this is

AI-era interfaces still mostly ask users to pick attributes, not state outcomes. Minsky is a small hierarchy of specialist agents that turns a fuzzy stated goal ("I want to become job-ready in data analytics within 3 months") into a resolved, valid set of filter selections against a real system's actual facet taxonomy, a ranked shortlist, and a plain-language explanation of why.

The first concrete target is [SWAYAM](https://swayam.gov.in)'s course-catalog Filters panel — a real, live example of attribute-only filtering with no path from intent to result. See [docs/case-study-swayam.md](docs/case-study-swayam.md) for the UX gap analysis (grounded in the actual scraped filter taxonomy) and [docs/architecture.md](docs/architecture.md) for how the agent pipeline solves it.

## Docs

- [docs/case-study-swayam.md](docs/case-study-swayam.md) — the concrete UX problem, grounded in the real filter taxonomy
- [docs/architecture.md](docs/architecture.md) — the agent society: roles, data flow, alternatives considered
- [docs/plan.md](docs/plan.md) — scope, milestones, research findings
- [docs/evaluation.md](docs/evaluation.md) — how correctness is validated

## Status

Early scaffold. See [docs/plan.md](docs/plan.md) for what's implemented vs. deferred.

## Usage (once implemented)

```bash
pip install -e .
python -m minsky "I'm a working professional, want to get job-ready in data analytics within 3 months"
```

## Development

```bash
pip install -e ".[dev]"
pytest
python -m eval.run_eval
```
