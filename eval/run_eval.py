"""Golden-case evaluation harness. Run with: python -m eval.run_eval

Loads eval/golden_cases.yaml, runs the full Coordinator pipeline on each
case's intent text, and compares only the FilterSelection keys present in
that case's `expected_filters` against what was actually resolved. Prints a
per-case PASS/FAIL line and an aggregate accuracy percentage, then exits 1 if
accuracy drops below the threshold -- see docs/evaluation.md. Fully offline:
no network access or API key required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from minsky.coordinator import Coordinator

_ACCURACY_THRESHOLD = 0.70
_GOLDEN_CASES_PATH = Path(__file__).parent / "golden_cases.yaml"


def load_cases(path: Path = _GOLDEN_CASES_PATH) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def check_case(coordinator: Coordinator, case: dict) -> tuple[bool, list[str]]:
    """Returns (passed, mismatch_descriptions)."""
    result = coordinator.solve(case["intent"])
    resolved = vars(result.filters)
    expected = case.get("expected_filters") or {}

    mismatches = []
    for key, expected_value in expected.items():
        actual_value = resolved.get(key)
        if actual_value != expected_value:
            mismatches.append(f"{key}: expected {expected_value!r}, got {actual_value!r}")

    return (len(mismatches) == 0, mismatches)


def main() -> int:
    cases = load_cases()
    if not cases:
        print("No golden cases found.")
        return 1

    coordinator = Coordinator()
    passed_count = 0

    for i, case in enumerate(cases, start=1):
        passed, mismatches = check_case(coordinator, case)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] case {i}: {case['intent']!r}")
        if not passed:
            for mismatch in mismatches:
                print(f"         - {mismatch}")
        if passed:
            passed_count += 1

    total = len(cases)
    accuracy = passed_count / total
    print()
    print(f"Accuracy: {passed_count}/{total} ({accuracy:.0%})")

    if accuracy < _ACCURACY_THRESHOLD:
        print(f"FAILED: accuracy below threshold ({_ACCURACY_THRESHOLD:.0%})")
        return 1

    print("OK: accuracy meets threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
