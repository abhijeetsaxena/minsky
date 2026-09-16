# Case Study: SWAYAM Course Catalog Filters

Ground truth captured from https://swayam.gov.in Course Catalog on 2026-09-16.

## The current filter taxonomy

The "FILTERS" sidebar exposes nine independent, flat facets:

| Facet | Options | Notes |
|---|---|---|
| National Coordinator | All, AICTE, CEC, IGNOU, IIMB, INI, NCERT, NIOS, NITTTR, NPTEL, UGC | Administrative body that produced the course — not a learner concept |
| Course Mode | All, Self Paced, Regular | |
| Course Duration | All, 4/6/8/10/12/15/16/24 Weeks | Discrete buckets, no range/"under N weeks" |
| Course Language | All | (values not enumerated at load time) |
| Educational Level | All, Up to Secondary School, Senior Secondary, UG-Year 1..4, PG-Year 1..2, Doctoral/Post-Doctoral | |
| Program Alignment | `-- Select --` | Only facet with a different placeholder than "All" — inconsistent, and its dependency on other fields is not surfaced |
| Industry/Sector | All + **54** sector names (Accounting… Textiles, Tourism…) | Flat alphabetical list, no grouping, no search-within-list |
| Course Exam Date | All + a list of **specific calendar dates** (e.g. "Wed Dec 09 2026") | Dates, not ranges — unusable for "before winter" style intent, forces exact-date scanning |
| Course Credits | All, Yes, No | |
| Category (separate block) | All + 13 domains (Design, Engineering and Technology, Health Sciences, Law, ARPIT, School, Teacher Education, …) | A second, parallel taxonomy the learner must also reconcile against Industry/Sector |

## Why this fails "intent-driven, outcome-based" design

1. **No outcome entry point.** A learner arrives with a goal — "become job-ready in data analytics in 3 months," "clear GATE next year," "get CE credits as a working teacher" — and must manually translate that goal into 5-9 independent dropdown picks themselves. The interface offers no path from intent → filters; the translation work is entirely offloaded to the human.
2. **Facets encode the provider's org chart, not the learner's mental model.** "National Coordinator" (AICTE vs. NPTEL vs. UGC) is meaningful to the ministry, not to a student deciding what to study.
3. **Unbounded flat lists instead of ranked/grouped choices.** 54 industry sectors and a dozen+ specific exam dates, both alphabetical/chronological with no grouping, no search, no "closest match" — cognitively this is a lookup task disguised as a filter.
4. **Facets are independent (AND-only), so intents that don't map cleanly to a single value are unsatisfiable.** "Something under 3 months" cannot be expressed against discrete week buckets without the learner doing the arithmetic themselves.
5. **Two overlapping taxonomies (Industry/Sector vs. Category) that the learner must reconcile,** with no indication of how they relate.
6. **No result-count feedback or explanation.** Filters give no preview of how many courses match, and the final list is a bare grid with no "why this course, given what you asked for."
7. **Inconsistent placeholder semantics** (`All` vs. `-- Select --`) signals the filters were bolted on incrementally rather than designed as one system.

## What "solved" looks like

An intent-driven layer sits **in front of** the existing facets (it doesn't need to replace them — SWAYAM's backend/API already supports exactly these query parameters). Given free text, it should:

- Parse the stated goal, topic, and implicit constraints (timeframe, mode, credit need, level).
- Resolve that into a concrete, valid selection across the *existing* nine facets (snapping "3 months" → `Course Duration ≤ 12 Weeks`, "data analytics job" → `Industry/Sector = IT & ITES`, `Category = Engineering and Technology`).
- Rank the resulting courses against the original intent, not just the resolved filters.
- Explain the mapping in plain language, so the learner can correct a wrong inference (e.g. "Industry/Sector: IT & ITES — because you mentioned 'data analytics'. Not right? →").

This is the concrete problem `minsky`'s prototype (see [architecture.md](architecture.md)) solves against a synthetic SWAYAM-shaped dataset built from this real taxonomy.
