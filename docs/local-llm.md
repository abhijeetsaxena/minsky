# Local LLM backend

`src/minsky/agents/local_llm_client.py` provides `LocalGGUFClient`, a third `LLMClient`
(see [architecture.md](architecture.md) and `llm_intent_parser.py`) alongside
`RuleBasedIntentParser` and `AnthropicLLMClient` — a free, private alternative that runs a
local, open-weight model on CPU instead of calling a hosted API.

## Why this exists

`AnthropicLLMClient` is fast and needs no local compute, but it costs money per call and
requires network access plus an `ANTHROPIC_API_KEY`. For a learner-facing tool, or for
development/CI where you don't want to burn API credits or depend on network access, a
local model is an appealing alternative: free per call, private (the learner's free text
never leaves the machine), and works offline once the model is downloaded. The tradeoff is
latency — a few seconds per request on CPU — and a one-time multi-GB download.

## Model choice, license, and download size

- **Model**: [`Qwen/Qwen2.5-3B-Instruct-GGUF`](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF),
  file `qwen2.5-3b-instruct-q4_k_m.gguf` (~2.1GB, a 4-bit quantization).
- **License**: Apache 2.0.
- **Ungated**: no Hugging Face account or token required to download it. If `HF_TOKEN` is
  set in the environment, `huggingface_hub`'s normal behavior picks it up automatically for
  higher rate limits, but it's never required.

## The benchmark journey

These numbers come from running `Coordinator(intent_parser=LLMIntentParser(client=...))`
against `eval/golden_cases.yaml` (the same 15-case golden set and harness described in
[evaluation.md](evaluation.md)), comparing `expected_filters` against what was actually
resolved:

| Model | Prompt | Accuracy |
|---|---|---|
| Qwen2.5-1.5B-Instruct-GGUF | freeform-taxonomy (model asked to name a sector/level in its own words) | **47%** |
| Qwen2.5-1.5B-Instruct-GGUF | closed-set-taxonomy (model asked to pick from the real facet values) | **73%** |
| Qwen2.5-3B-Instruct-GGUF | closed-set-taxonomy | **93% (14/15)** |

The freeform → closed-set change was the single biggest lever, not the model size bump.
`ConstraintResolverAgent`'s fuzzy-matcher (`constraint_resolver.py`) can't reliably bridge
a model's loose paraphrase (e.g. "IT") onto the real SWAYAM taxonomy value (e.g.
"IT & ITES"), but a model explicitly asked to choose from the closed list of real values
gets it right far more often. Because this is a strict improvement for any backend — not a
local-model-specific hack — `llm_intent_parser.py`'s shared `_SYSTEM_PROMPT` was updated to
the closed-set-taxonomy version, so `AnthropicLLMClient` benefits too.

93% on the 3B model with the closed-set prompt is comparable to what's expected from the
hosted Anthropic backend (not separately measured in this repo, since `AnthropicLLMClient`
requires a paid API key to run against the golden set) and is well above the repo's 70% CI
accuracy threshold (`eval/run_eval.py`'s `_ACCURACY_THRESHOLD`).

## Measured latency

On a no-GPU machine (Intel UHD 770 integrated graphics only, i7-12700, 16GB RAM) with
`n_ctx=4096`, `n_threads=8`, `temperature=0.0`, `max_tokens=300`:

- Model load: ~1.6s
- Inference: ~4-10s per request

This is why the module-level model cache (below) matters — paying the ~1.6s load cost on
every single request, on top of several seconds of inference, would make the backend
unusably slow under any real request volume.

## Install

```bash
pip install -e '.[local-llm]'
```

`llama-cpp-python` ships prebuilt wheels for CPU-only use, but a plain `pip install
llama-cpp-python` can fail to find one for your platform and fall back to building from
source — which fails without a local C/C++ compiler (common on a fresh Windows machine).
If that happens, install from the prebuilt CPU wheel index directly:

```bash
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

This exact command was confirmed to install cleanly on Windows with no local compiler
present.

## Module-level model caching

`AnthropicLLMClient` is a stateless HTTP client — cheap to construct fresh on every
request, which is exactly what `api.py`'s `_build_coordinator()` does for every incoming
`/resolve` call. `LocalGGUFClient` cannot follow the same pattern: constructing a fresh
`llama_cpp.Llama` on every request would re-read the ~2.1GB model file from disk and pay
the ~1.6s load cost per call, on top of the several-second inference cost above — the
model-loading overhead alone would dominate request latency.

Instead, loaded `Llama` instances are cached process-wide in a module-level dict, keyed by
the resolved `(repo_id, filename, n_ctx, n_threads)` config:

- Multiple `LocalGGUFClient()` constructions with the same config — e.g. one built per
  incoming HTTP request — share and reuse the same loaded model rather than each loading
  its own copy.
- Loading stays **lazy**: it only happens on the first actual `.complete()` call, not at
  construction time, matching the lazy-import pattern `AnthropicLLMClient` already uses for
  the `anthropic` package.
- A `threading.Lock` guards the load-if-absent check, so two concurrent first-requests
  (plausible under a real API server, e.g. uvicorn with multiple worker threads handling
  requests concurrently) can't both trigger a redundant/racy load of the same config.

The downloaded model file itself is cached separately and independently by
`huggingface_hub` in its own default cache directory (`hf_hub_download()`'s default
behavior) — `LocalGGUFClient` doesn't invent a separate cache location for that.

## When to use which backend

| Backend | Cost | Network | Accuracy (golden-case eval) | Latency | Notes |
|---|---|---|---|---|---|
| `rule_based` (`RuleBasedIntentParser`) | Free | None | 100% on cases it's tuned for, but least tolerant of varied/unusual phrasing | Instant | Deterministic keyword/regex rules; no LLM involved at all. Best default when phrasing is fairly predictable or when you need zero latency/cost/flakiness. |
| `llm` (`AnthropicLLMClient`) | Costs money per call | Requires network + `ANTHROPIC_API_KEY` | Not yet measured in this repo (no free credits to run the golden set) | Fast (hosted, GPU-backed) | Best when you want the highest phrasing flexibility and have an API budget/key. |
| `local_llm` (`LocalGGUFClient`) | Free per call | None after the one-time ~2.1GB download | 93% (14/15) measured on the golden-case set | Slow-ish: ~4-10s per request on a no-GPU machine | Best for cost-sensitive, privacy-sensitive, or offline scenarios where a few seconds of latency per request is acceptable. |

All three implement the same `IntentParser`/`LLMClient` interfaces and slot into
`Coordinator` interchangeably — see `src/minsky/api.py`'s `_build_coordinator()` for how
the HTTP API selects one via the `parser` request field (`"rule_based"`, `"llm"`, or
`"local_llm"`).
