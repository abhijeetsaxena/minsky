"""Tests for LocalGGUFClient (src/minsky/agents/local_llm_client.py).

Fully offline by default: `llama_cpp` and `huggingface_hub` are mocked out
(or their absence is simulated) everywhere except the one real integration
test at the bottom, which is skipped unless MINSKY_LOCAL_LLM_TESTS=1 is set --
mirrors the MINSKY_LIVE_TESTS gating pattern used in
tests/test_swayam_client.py, since that test downloads a real ~2GB model and
runs real inference and must never be a hard dependency of the default test
suite or CI.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

from minsky.agents import local_llm_client
from minsky.agents.local_llm_client import LocalGGUFClient

_RAW_TEXT = "I want to become job-ready in data analytics within 3 months"


@pytest.fixture(autouse=True)
def _clear_model_cache():
    """The model cache is process-wide/module-level by design (see the module
    docstring) -- tests must not leak a cached mock/model across each other."""
    local_llm_client._MODEL_CACHE.clear()
    yield
    local_llm_client._MODEL_CACHE.clear()


def _force_missing(monkeypatch, *names: str) -> None:
    """Simulate `names` not being installed, regardless of whether they
    actually are in this environment: assigning None in sys.modules makes a
    subsequent `import <name>` raise ImportError, per Python's import system.
    """
    for name in names:
        monkeypatch.setitem(sys.modules, name, None)


# -- module import stays safe without either package -------------------------


def test_module_imports_fine_without_llama_cpp_or_huggingface_hub(monkeypatch):
    _force_missing(monkeypatch, "llama_cpp", "huggingface_hub")
    # Re-importing (or just using) the already-imported module must not raise --
    # local_llm_client.py never imports either package at module scope.
    import importlib

    reloaded = importlib.reload(local_llm_client)
    assert reloaded.LocalGGUFClient is not None


def test_construction_never_raises_without_packages_installed(monkeypatch):
    _force_missing(monkeypatch, "llama_cpp", "huggingface_hub")
    client = LocalGGUFClient()
    assert client.repo_id == "Qwen/Qwen2.5-3B-Instruct-GGUF"


def test_complete_raises_clear_runtime_error_without_llama_cpp(monkeypatch):
    _force_missing(monkeypatch, "llama_cpp", "huggingface_hub")
    client = LocalGGUFClient()
    with pytest.raises(RuntimeError) as exc_info:
        client.complete(system="sys", user="user")
    message = str(exc_info.value)
    assert "llama-cpp-python" in message
    assert "huggingface_hub" in message
    assert "local-llm" in message
    assert "--extra-index-url" in message


# -- env-var / constructor-arg resolution -------------------------------------


def test_repo_id_resolution_order(monkeypatch):
    monkeypatch.delenv("MINSKY_LOCAL_LLM_REPO", raising=False)
    assert LocalGGUFClient().repo_id == "Qwen/Qwen2.5-3B-Instruct-GGUF"

    monkeypatch.setenv("MINSKY_LOCAL_LLM_REPO", "some-org/env-repo-GGUF")
    assert LocalGGUFClient().repo_id == "some-org/env-repo-GGUF"

    # constructor arg wins over env var
    assert LocalGGUFClient(repo_id="explicit/repo-GGUF").repo_id == "explicit/repo-GGUF"


def test_n_ctx_resolution_order(monkeypatch):
    monkeypatch.delenv("MINSKY_LOCAL_LLM_N_CTX", raising=False)
    assert LocalGGUFClient().n_ctx == 4096

    monkeypatch.setenv("MINSKY_LOCAL_LLM_N_CTX", "8192")
    assert LocalGGUFClient().n_ctx == 8192

    # constructor arg wins over env var
    assert LocalGGUFClient(n_ctx=2048).n_ctx == 2048


def test_n_threads_defaults_to_none_and_reads_env(monkeypatch):
    monkeypatch.delenv("MINSKY_LOCAL_LLM_N_THREADS", raising=False)
    assert LocalGGUFClient().n_threads is None

    monkeypatch.setenv("MINSKY_LOCAL_LLM_N_THREADS", "8")
    assert LocalGGUFClient().n_threads == 8

    assert LocalGGUFClient(n_threads=4).n_threads == 4


def test_max_tokens_resolution_order(monkeypatch):
    monkeypatch.delenv("MINSKY_LOCAL_LLM_MAX_TOKENS", raising=False)
    assert LocalGGUFClient().max_tokens == 300

    monkeypatch.setenv("MINSKY_LOCAL_LLM_MAX_TOKENS", "500")
    assert LocalGGUFClient().max_tokens == 500

    assert LocalGGUFClient(max_tokens=100).max_tokens == 100


def test_filename_resolution_order(monkeypatch):
    monkeypatch.delenv("MINSKY_LOCAL_LLM_FILE", raising=False)
    assert LocalGGUFClient().filename == "qwen2.5-3b-instruct-q4_k_m.gguf"

    monkeypatch.setenv("MINSKY_LOCAL_LLM_FILE", "other-file.gguf")
    assert LocalGGUFClient().filename == "other-file.gguf"

    assert LocalGGUFClient(filename="explicit.gguf").filename == "explicit.gguf"


# -- module-level process-wide cache ------------------------------------------


def _install_mocked_llama_cpp_and_hf():
    """Installs fake `llama_cpp`/`huggingface_hub` modules in sys.modules and
    returns the mock `Llama` class so callers can assert on call counts."""
    fake_llama_cls = MagicMock(name="Llama")
    fake_llm_instance = fake_llama_cls.return_value
    fake_llm_instance.create_chat_completion.return_value = {
        "choices": [{"message": {"content": '{"ok": true}'}}]
    }

    fake_llama_cpp_module = MagicMock()
    fake_llama_cpp_module.Llama = fake_llama_cls

    fake_hf_module = MagicMock()
    fake_hf_module.hf_hub_download.return_value = "/fake/path/model.gguf"

    return fake_llama_cpp_module, fake_hf_module, fake_llama_cls


def test_two_instances_with_same_config_share_one_cached_model(monkeypatch):
    fake_llama_cpp_module, fake_hf_module, fake_llama_cls = _install_mocked_llama_cpp_and_hf()
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf_module)

    client_one = LocalGGUFClient()
    client_two = LocalGGUFClient()

    client_one.complete(system="sys", user="user 1")
    client_two.complete(system="sys", user="user 2")

    # Two separate LocalGGUFClient constructions with identical config must
    # reuse the same loaded model -- Llama(...) (and the hf download) must
    # only be invoked once across both.
    assert fake_llama_cls.call_count == 1
    assert fake_hf_module.hf_hub_download.call_count == 1


def test_different_config_gets_its_own_cache_entry(monkeypatch):
    fake_llama_cpp_module, fake_hf_module, fake_llama_cls = _install_mocked_llama_cpp_and_hf()
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf_module)

    LocalGGUFClient(n_ctx=4096).complete(system="sys", user="user")
    LocalGGUFClient(n_ctx=2048).complete(system="sys", user="user")

    assert fake_llama_cls.call_count == 2


# -- complete() request/response shape ----------------------------------------


def test_complete_calls_create_chat_completion_with_messages_and_returns_content(monkeypatch):
    fake_llama_cpp_module, fake_hf_module, fake_llama_cls = _install_mocked_llama_cpp_and_hf()
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf_module)

    fake_llm_instance = fake_llama_cls.return_value
    fake_llm_instance.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "hello from the model"}}]
    }

    client = LocalGGUFClient(max_tokens=42)
    result = client.complete(system="the system prompt", user=_RAW_TEXT)

    assert result == "hello from the model"
    fake_llm_instance.create_chat_completion.assert_called_once_with(
        messages=[
            {"role": "system", "content": "the system prompt"},
            {"role": "user", "content": _RAW_TEXT},
        ],
        max_tokens=42,
        temperature=0.0,
    )


def test_load_model_passes_n_threads_only_when_set(monkeypatch):
    fake_llama_cpp_module, fake_hf_module, fake_llama_cls = _install_mocked_llama_cpp_and_hf()
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf_module)

    LocalGGUFClient(n_threads=None).complete(system="s", user="u")
    _, kwargs = fake_llama_cls.call_args
    assert "n_threads" not in kwargs


def test_load_model_passes_n_threads_when_explicitly_set(monkeypatch):
    fake_llama_cpp_module, fake_hf_module, fake_llama_cls = _install_mocked_llama_cpp_and_hf()
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf_module)

    LocalGGUFClient(n_threads=8).complete(system="s", user="u")
    _, kwargs = fake_llama_cls.call_args
    assert kwargs["n_threads"] == 8


# -- real integration test: downloads and runs the real model ----------------


@pytest.mark.skipif(
    os.environ.get("MINSKY_LOCAL_LLM_TESTS") != "1",
    reason="downloads and runs a real ~2GB local model",
)
def test_real_local_model_meets_conservative_golden_case_accuracy():
    """Runs a few golden cases through the real Qwen2.5-3B GGUF model.

    Measured accuracy on the full golden-case set is 93% (14/15, see
    docs/local-llm.md) -- this asserts a conservative floor (8/10, well below
    93%) against a subset to avoid flakiness while still catching a real
    regression (e.g. a broken prompt or a bad model swap).
    """
    import yaml

    from minsky.agents.llm_intent_parser import LLMIntentParser
    from minsky.coordinator import Coordinator

    cases_path = os.path.join(os.path.dirname(__file__), "..", "eval", "golden_cases.yaml")
    with open(cases_path, encoding="utf-8") as fh:
        all_cases = yaml.safe_load(fh)
    cases = all_cases[:10]

    coordinator = Coordinator(intent_parser=LLMIntentParser(client=LocalGGUFClient()))

    passed = 0
    for case in cases:
        result = coordinator.solve(case["intent"])
        resolved = vars(result.filters)
        expected = case.get("expected_filters") or {}
        if all(resolved.get(key) == value for key, value in expected.items()):
            passed += 1

    assert passed >= 8, f"only {passed}/{len(cases)} golden cases matched"
