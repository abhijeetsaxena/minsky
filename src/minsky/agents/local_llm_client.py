"""LocalGGUFClient: an `LLMClient` (see llm_intent_parser.py) backed by a local,
open-weight GGUF model run on CPU via `llama-cpp-python`, downloaded from
Hugging Face via `huggingface_hub`.

Why this exists: `AnthropicLLMClient` is fast and hosted but costs money per
call and requires network access + an API key. `LocalGGUFClient` is a
free/private alternative -- no network needed after the one-time model
download, no per-call cost -- at the expense of being slower per request and
needing a large one-time download. See docs/local-llm.md for the full story:
model/license choice, the benchmark journey that led to these exact settings,
and measured latency/accuracy numbers.

Design goals mirrored from `AnthropicLLMClient`:
- `llama_cpp` and `huggingface_hub` are imported lazily (only when this client
  is actually used), so this module -- and any pipeline that only uses
  `RuleBasedIntentParser`/`AnthropicLLMClient` -- stays fully importable and
  usable even when neither package is installed.
- `.complete()` raises on failure rather than swallowing errors itself --
  `LLMIntentParser.parse()` already catches broadly and falls back to
  `RuleBasedIntentParser` (see llm_intent_parser.py), so this client stays
  simple.

Departure from `AnthropicLLMClient`: unlike the Anthropic client (a stateless
HTTP client, cheap to construct fresh per-request), constructing this client
must NOT reload the ~2.1GB model from disk into a fresh `llama_cpp.Llama`
instance every time -- that would add seconds of dead weight to every single
request and defeat the entire point of running locally. Loaded models are
therefore cached process-wide (module-level, keyed by the resolved config),
so multiple `LocalGGUFClient()` constructions in the same process -- e.g. a
fresh one built per HTTP request, exactly like `_build_coordinator()` does in
api.py -- reuse the same loaded model instead of reloading it. Loading is
still lazy: it only happens on the first actual `.complete()` call, not at
construction time. A lock around the load-if-absent check keeps two
concurrent first-requests (plausible under a real API server, e.g. uvicorn
with multiple worker threads) from both triggering a redundant/racy load.
"""

from __future__ import annotations

import os
import threading
from typing import Any

_DEFAULT_REPO_ID = "Qwen/Qwen2.5-3B-Instruct-GGUF"
_DEFAULT_FILENAME = "qwen2.5-3b-instruct-q4_k_m.gguf"
_DEFAULT_N_CTX = 4096
_DEFAULT_MAX_TOKENS = 300

_MISSING_DEPS_MESSAGE = (
    "LocalGGUFClient requires the 'llama-cpp-python' and 'huggingface_hub' packages -- "
    "install them: pip install -e '.[local-llm]', and llama-cpp-python may need "
    "pip install llama-cpp-python --extra-index-url "
    "https://abetlen.github.io/llama-cpp-python/whl/cpu if a prebuilt wheel isn't found "
    "for your platform."
)

# Process-wide cache of loaded `Llama` instances, keyed by the resolved
# (repo_id, filename, n_ctx, n_threads) config -- so multiple LocalGGUFClient
# instances constructed with the same config share one loaded model instead
# of each reloading it from disk. Guarded by `_CACHE_LOCK` so two concurrent
# first-requests don't both trigger a redundant/racy load.
_MODEL_CACHE: dict[tuple[str, str, int, int | None], Any] = {}
_CACHE_LOCK = threading.Lock()


class LocalGGUFClient:
    """`LLMClient` backed by a local GGUF model run on CPU via `llama-cpp-python`.

    Config resolution order for each parameter: constructor arg > matching
    env var > hardcoded default. See docs/local-llm.md for why these
    particular defaults (model choice, n_ctx, temperature=0.0) were picked.
    """

    def __init__(
        self,
        repo_id: str | None = None,
        filename: str | None = None,
        n_ctx: int | None = None,
        n_threads: int | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.repo_id = repo_id or os.environ.get("MINSKY_LOCAL_LLM_REPO") or _DEFAULT_REPO_ID
        self.filename = filename or os.environ.get("MINSKY_LOCAL_LLM_FILE") or _DEFAULT_FILENAME

        if n_ctx is not None:
            self.n_ctx = n_ctx
        else:
            env_n_ctx = os.environ.get("MINSKY_LOCAL_LLM_N_CTX")
            self.n_ctx = int(env_n_ctx) if env_n_ctx else _DEFAULT_N_CTX

        if n_threads is not None:
            self.n_threads = n_threads
        else:
            env_n_threads = os.environ.get("MINSKY_LOCAL_LLM_N_THREADS")
            self.n_threads = int(env_n_threads) if env_n_threads else None

        if max_tokens is not None:
            self.max_tokens = max_tokens
        else:
            env_max_tokens = os.environ.get("MINSKY_LOCAL_LLM_MAX_TOKENS")
            self.max_tokens = int(env_max_tokens) if env_max_tokens else _DEFAULT_MAX_TOKENS

    def complete(self, *, system: str, user: str) -> str:
        llm = self._get_model()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=self.max_tokens,
            temperature=0.0,
        )
        return response["choices"][0]["message"]["content"]

    # -- model loading / caching ---------------------------------------------

    def _get_model(self) -> Any:
        cache_key = (self.repo_id, self.filename, self.n_ctx, self.n_threads)
        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached

        with _CACHE_LOCK:
            # Re-check inside the lock: another thread may have loaded it
            # while we were waiting.
            cached = _MODEL_CACHE.get(cache_key)
            if cached is not None:
                return cached
            model = self._load_model()
            _MODEL_CACHE[cache_key] = model
            return model

    def _load_model(self) -> Any:
        try:
            import llama_cpp
        except ImportError as exc:
            raise RuntimeError(_MISSING_DEPS_MESSAGE) from exc
        try:
            import huggingface_hub
        except ImportError as exc:
            raise RuntimeError(_MISSING_DEPS_MESSAGE) from exc

        model_path = huggingface_hub.hf_hub_download(repo_id=self.repo_id, filename=self.filename)

        kwargs: dict[str, Any] = {"model_path": model_path, "n_ctx": self.n_ctx, "verbose": False}
        if self.n_threads is not None:
            kwargs["n_threads"] = self.n_threads
        return llama_cpp.Llama(**kwargs)
