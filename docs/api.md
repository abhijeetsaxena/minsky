# HTTP API

`src/minsky/api.py` wraps `Coordinator` (see `docs/architecture.md`) in a small
FastAPI app, so the intent -> filters -> ranked courses -> rationale pipeline
is callable over HTTP. The concrete next consumer is a browser extension's
content script calling a local instance of this API.

## Local/dev tool only -- read before running this anywhere but your own machine

This app ships with:

- **Wide-open CORS** (`allow_origins=["*"]`), so any origin -- including a
  browser extension's content script -- can call it.
- **No authentication.**
- **No rate limiting or request size limits.**

That is a deliberate, reasonable default for a local instance a browser
extension talks to on `localhost`. It is **not** safe to expose publicly
as-is. Before any public deployment, at minimum:

- Restrict `allow_origins` to the specific origin(s) that should be allowed
  (e.g. the extension's `chrome-extension://<id>` origin), not `"*"`.
- Add authentication (an API key header, at minimum).
- Add rate limiting and input size limits (e.g. cap `intent` length).

## Running it

Install the `api` extra, then run with `uvicorn`:

```bash
pip install -e ".[api]"
python -m uvicorn minsky.api:app --reload
```

(`python -m uvicorn ...` rather than a bare `uvicorn ...` — on some setups pip installs
the package but its console-script entry point isn't on `PATH`; running it as a module
always works since it only depends on `python` itself being on `PATH`.)

By default this serves on `http://127.0.0.1:8000`.

## Endpoints

### `GET /health`

Liveness check.

```bash
curl http://127.0.0.1:8000/health
```

```json
{"status": "ok"}
```

### `GET /facets`

Returns the real SWAYAM filter taxonomy (`data/swayam_facets.json`, loaded via
`load_facets()`), so a client can render real dropdown values instead of
hardcoding them.

```bash
curl http://127.0.0.1:8000/facets
```

```json
{
  "national_coordinator": ["AICTE", "CEC", "IGNOU", "..."],
  "course_mode": ["Self Paced", "Regular"],
  "course_duration_weeks": [4, 6, 8, 10, 12, 15, 16, 24],
  "educational_level": ["Up to Secondary School", "..."],
  "industry_sector": ["Accounting and Financial Services", "..."],
  "credits": ["Yes", "No"],
  "category": ["Annual Refresher Programme in Teaching (ARPIT)", "..."]
}
```

### `POST /resolve`

Runs the full pipeline for one free-text intent.

**Request body:**

| field           | type   | default       | notes                                             |
| --------------- | ------ | ------------- | -------------------------------------------------- |
| `intent`        | string | -- (required) | must be non-empty / non-whitespace-only            |
| `top_n`         | int    | `5`           | must be between 1 and 25 inclusive                 |
| `parser`        | string | `"rule_based"`| `"rule_based"` or `"llm"`                          |
| `course_source` | string | `"sample"`    | `"sample"` or `"live"`                             |

- `parser: "llm"` uses `LLMIntentParser`, which is safe to use even without
  `ANTHROPIC_API_KEY` configured -- it falls back to the deterministic
  `RuleBasedIntentParser` internally on any failure (missing key, network
  error, malformed model output), so the API never needs special-case error
  handling for this.
- `course_source: "live"` uses `LiveSwayamCourseSource`, always constructed
  with a `SampleCourseSource()` fallback, so a live-API hiccup degrades
  gracefully instead of failing the request.

```bash
curl -X POST http://127.0.0.1:8000/resolve \
  -H "Content-Type: application/json" \
  -d '{"intent": "I want to become job-ready in data analytics within 3 months", "top_n": 3}'
```

**Response body** (`ResolutionResult`, JSON-encoded via `dataclasses.asdict`):

```json
{
  "intent": {
    "raw_text": "I want to become job-ready in data analytics within 3 months",
    "goal_type": "job_readiness",
    "topics": ["data analytics"],
    "max_duration_weeks": 12,
    "preferred_mode": null,
    "preferred_language": null,
    "needs_credits": null,
    "educational_level": null,
    "industry_sector": "IT & ITES",
    "confidence": 0.85
  },
  "filters": {
    "national_coordinator": null,
    "course_mode": null,
    "course_duration": "12 Weeks",
    "course_language": null,
    "educational_level": null,
    "industry_sector": "IT & ITES",
    "credits": null,
    "category": "Engineering and Technology"
  },
  "ranked_courses": [
    {
      "course": {
        "id": "...",
        "title": "...",
        "provider": "...",
        "mode": "...",
        "duration_weeks": 12,
        "language": "...",
        "educational_level": "...",
        "industry_sector": "IT & ITES",
        "credits": false,
        "category": "Engineering and Technology",
        "keywords": ["..."]
      },
      "score": 0.9,
      "reasons": ["..."]
    }
  ],
  "rationale": "..."
}
```

Note `goal_type` comes back as its plain string value (e.g. `"job_readiness"`),
not an Enum repr -- `GoalType` is a `str` Enum and FastAPI's JSON encoding
handles it correctly.

**Error responses:**

- Blank/whitespace-only `intent`, an invalid `parser`/`course_source` value, or
  `top_n` outside `[1, 25]` -> `422 Unprocessable Entity` (Pydantic request
  validation).
- Any unexpected failure inside `Coordinator.solve()` (not expected in normal
  operation, since both `LLMIntentParser` and `LiveSwayamCourseSource` already
  degrade gracefully on their own) -> `500 Internal Server Error` with body
  `{"error": "<message>"}` instead of a raw stack trace.

## Not included

There is no `minsky serve` CLI subcommand -- running the API is just the
`uvicorn` command above.
