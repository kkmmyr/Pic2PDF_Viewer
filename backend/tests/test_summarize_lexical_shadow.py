from __future__ import annotations

import io
import json
from datetime import datetime

from scripts.summarize_lexical_shadow import evaluate_gate, load_policy, main, summarize_lines

_SUCCESS_A = (
    "2026-08-22 10:00:00 [INFO] search: lexical shadow: "
    "query_hash=111111111111 fts_count=10 icu_count=8 overlap=6 fts_ms=1.000 icu_ms=8.000"
)
_SUCCESS_B = (
    "2026-08-22 10:05:00 [INFO] search: lexical shadow: "
    "query_hash=111111111111 fts_count=0 icu_count=0 overlap=0 fts_ms=3.000 icu_ms=10.000"
)
_UNAVAILABLE = (
    "2026-08-22 10:10:00 [WARNING] search: lexical shadow unavailable: "
    "query_hash=222222222222 fts_count=4 fts_ms=2.000 icu_ms=12.000 error_type=RuntimeError"
)
_LANCE_FALLBACK = (
    "2026-08-22 10:15:00 [WARNING] search: lexical ICU fallback: query_hash=333333333333 error_type=RuntimeError"
)


def test_summarize_lines_reports_rates_latency_overlap_without_hashes() -> None:
    result = summarize_lines([_SUCCESS_A, _SUCCESS_B, _UNAVAILABLE, _LANCE_FALLBACK])

    assert result["status"] == "observed"
    assert result["shadow"] == {
        "observations": 3,
        "successes": 2,
        "fallbacks": 1,
        "success_rate": 0.666667,
        "fallback_rate": 0.333333,
        "unique_query_count": 2,
    }
    assert result["latency_ms"]["fts5"] == {
        "samples": 3,
        "p50": 2.0,
        "p95": 3.0,
        "max": 3.0,
    }
    assert result["latency_ms"]["icu_success"]["p50"] == 9.0
    assert result["zero_hit"] == {"fts5": 1, "icu_success": 1}
    assert result["top_set_overlap"]["jaccard_mean"] == 0.75
    assert result["lance_icu_fallbacks"] == 1
    assert result["observation_window"] == {
        "first_at": "2026-08-22T10:00:00",
        "last_at": "2026-08-22T10:10:00",
        "distinct_local_dates": 1,
        "timestamped_observations": 3,
    }
    serialized = json.dumps(result)
    assert "111111111111" not in serialized
    assert "222222222222" not in serialized


def test_summarize_lines_applies_half_open_time_window() -> None:
    result = summarize_lines(
        [_SUCCESS_A, _SUCCESS_B, _UNAVAILABLE],
        since=datetime(2026, 8, 22, 10, 5),
        until=datetime(2026, 8, 22, 10, 10),
    )

    assert result["shadow"]["observations"] == 1
    assert result["input"]["filtered_lines"] == 2


def test_main_returns_two_when_no_shadow_observations(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("ordinary application log\n"))

    exit_code = main([])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["status"] == "insufficient_data"
    assert output["has_observations"] is False


def test_malformed_candidate_is_counted_but_not_observed() -> None:
    result = summarize_lines(["2026-08-22 10:00:00 lexical shadow: broken"])

    assert result["shadow"]["observations"] == 0
    assert result["input"]["malformed_lines"] == 1


def _policy(**overrides: int | float | str) -> dict[str, int | float | str]:
    policy: dict[str, int | float | str] = {
        "schema_version": "lexical-shadow-policy-v1",
        "min_observations": 3,
        "min_unique_queries": 2,
        "min_distinct_local_dates": 1,
        "max_fallback_rate": 0.0,
        "max_icu_success_p95_ms": 200.0,
        "max_malformed_lines": 0,
        "max_lance_icu_fallbacks": 0,
    }
    policy.update(overrides)
    return policy


def test_gate_distinguishes_pending_failure_and_pass() -> None:
    second_query = _SUCCESS_B.replace("111111111111", "222222222222")
    summary = summarize_lines([_SUCCESS_A, second_query])
    gate = evaluate_gate(summary, _policy(), "a" * 64)
    assert gate["status"] == "pending"
    assert gate["pending_reasons"] == ["min_observations"]

    failed = evaluate_gate(
        summarize_lines([_SUCCESS_A, second_query, _UNAVAILABLE]),
        _policy(),
        "a" * 64,
    )
    assert failed["status"] == "failed"
    assert failed["failure_reasons"] == ["max_fallback_rate"]

    passed = evaluate_gate(
        summarize_lines([_SUCCESS_A, _SUCCESS_B, _SUCCESS_A.replace("111111111111", "222222222222")]),
        _policy(),
        "a" * 64,
    )
    assert passed["status"] == "passed"


def test_main_applies_policy_and_returns_pending_exit_code(tmp_path, monkeypatch, capsys) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(_policy()), encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO(_SUCCESS_A + "\n"))

    exit_code = main(["--policy", str(policy_path), "--fail-on-gate"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["gate"]["status"] == "pending"
    assert len(output["gate"]["policy_sha256"]) == 64


def test_load_policy_rejects_invalid_schema(tmp_path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text('{"schema_version":"wrong"}', encoding="utf-8")

    try:
        load_policy(policy_path)
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("invalid policy must fail closed")
