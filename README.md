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
- [docs/live-integration.md](docs/live-integration.md) — the live SWAYAM data source (real course data, verified filter mappings)
- [docs/api.md](docs/api.md) — the HTTP API
- [extension/README.md](extension/README.md) — the browser extension

## Status

Core pipeline, live SWAYAM integration, an LLM-backed intent parser, an HTTP API, and a
browser extension are all implemented — see [docs/plan.md](docs/plan.md) for what's
still deliberately out of scope.

## Usage

CLI, offline, against the synthetic sample catalog:

```bash
pip install -e .
python -m minsky "I'm a working professional, want to get job-ready in data analytics within 3 months"
```

HTTP API, with real live SWAYAM course data:

```bash
pip install -e ".[api]"
uvicorn minsky.api:app --reload
curl -X POST localhost:8000/resolve -H 'Content-Type: application/json' \
  -d '{"intent": "I want to become job-ready in data analytics within 3 months", "course_source": "live"}'
```

Or load [extension/](extension/) as an unpacked browser extension to get the same
result as a panel directly on [swayam.gov.in](https://swayam.gov.in) — see
[extension/README.md](extension/README.md).

An LLM-backed intent parser is also available (`pip install -e ".[llm]"`, set
`ANTHROPIC_API_KEY`, pass `parser: "llm"` to `/resolve`) — see
[docs/architecture.md](docs/architecture.md)'s extension points.

## Development

```bash
pip install -e ".[dev,api]"
pytest
python -m eval.run_eval
```
