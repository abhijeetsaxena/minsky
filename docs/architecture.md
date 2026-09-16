# Architecture

## Philosophy

Minsky's premise (from Marvin Minsky's *Society of Mind*): a hard, fuzzy problem — "turn a learner's stated goal into a resolved set of filters and a justified shortlist" — is easier to solve as a small hierarchy of narrow, testable specialists than as one monolithic prompt or one giant filter form. Each agent takes a small, typed input and produces a small, typed output; no agent needs to understand the whole problem, and each can be built, tested, and swapped independently.

v1 uses **hierarchical pipeline coordination** (a Coordinator dispatches to specialists in sequence, merges typed outputs) rather than free-form decentralized message-passing. This is a deliberate scoping decision, not a simplification we're unaware of — see [Prior Art & Alternatives Considered](#prior-art--alternatives-considered).

## Agents

```
raw intent text
      │
      ▼
┌─────────────────┐
│   Coordinator    │  owns the pipeline, merges results, produces ResolutionResult
└─────────────────┘
      │ dispatches, in order
      ▼
┌─────────────────┐   Intent  (goal_type, topics, constraints, confidence)
│ IntentParserAgent│──────────────────────────────────────────────►
└─────────────────┘
      ▼
┌──────────────────────┐  FilterSelection (valid values snapped to the
│ ConstraintResolverAgent│  real SWAYAM facet taxonomy)
└──────────────────────┘──────────────────────────────────────────►
      ▼
┌─────────────────┐   list[RankedCourse] (filtered + scored + reasoned)
│ OutcomeRankerAgent│─────────────────────────────────────────────►
└─────────────────┘
      ▼
┌─────────────────┐   rationale: str (plain-language explanation)
│  ExplainerAgent  │─────────────────────────────────────────────►
└─────────────────┘
```

- **IntentParserAgent** — free text → `Intent`. Two interchangeable backends behind one interface: `RuleBasedIntentParser` (keyword/regex heuristics, zero external dependencies, deterministic — the default, and the only one CI needs) and an optional `LLMIntentParser` (pluggable client, for higher recall on phrasing the rules miss). Strategy pattern so the tool is fully usable and testable with no API key.
- **ConstraintResolverAgent** — `Intent` + the real facet taxonomy (`data/swayam_facets.json`, scraped from swayam.gov.in) → `FilterSelection`. This is the agent that directly answers the case study's gap: it does the intent→filter translation the learner currently has to do by hand, and it only ever emits values that exist in the real taxonomy (fuzzy-snapped via `difflib`, never invented).
- **OutcomeRankerAgent** — `FilterSelection` + a course catalog → ranked `list[RankedCourse]`, scored on facet match plus keyword overlap between `Intent.topics` and each course's title/keywords, so ranking reflects the *original goal*, not just the resolved filters.
- **ExplainerAgent** — assembles a plain-language rationale: what was inferred, why each filter was chosen, why the top course was ranked first. This is the transparency layer the current SWAYAM UI has none of.
- **Coordinator** — the only agent aware of the full pipeline; wires the above together and is the one class most callers (CLI, tests, future API) import.

## Data model

See [`src/minsky/schema.py`](../src/minsky/schema.py) for the authoritative types: `Intent`, `FilterSelection`, `Course`, `RankedCourse`, `ResolutionResult`.

## Prior Art & Alternatives Considered

Framework survey and prior-art research (full findings in [plan.md](plan.md#research-findings)):

- **Orchestration framework:** evaluated LangGraph, CrewAI, AG2 (AutoGen's community continuation), MetaGPT, CAMEL-AI, OpenAI Swarm. None fit a small fixed pipeline without pulling in dependency weight or an opinionated conversation/graph model the project doesn't need yet. **Decision: hand-rolled orchestrator.** If the roadmap grows into branching/conditional workflows, **CrewAI**'s hierarchical `Process` is the natural upgrade path — its manager-delegates-to-roles model already matches this architecture.
- **Intent→filter prior art:** closest reference points are **CRSLab** (RUCAIBox) for task decomposition in conversational recommenders, and **Sparklis** / **EasyQuery** / **ln2sql** for "fuzzy phrase → structured facet" translation. No existing OSS package combines goal decomposition + constraint resolution + ranking + explanation for this kind of filter UI — that combination is the gap minsky fills.

## Extension points

- Swap `RuleBasedIntentParser` for `LLMIntentParser` without touching any other agent (same `Intent` output contract).
- Point `ConstraintResolverAgent` at a different facet taxonomy JSON to retarget minsky at a different portal's filter set (e.g. another MOOC platform) without changing agent logic.
- Add agents to the pipeline (e.g. a `DiversityAgent` to avoid recommending near-duplicate courses) by inserting a stage between Ranker and Explainer — each agent's typed contract keeps this additive.
