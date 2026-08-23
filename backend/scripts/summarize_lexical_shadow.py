"""Aggregate privacy-preserving LanceDB ICU shadow observations as JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

POLICY_SCHEMA_VERSION = "lexical-shadow-policy-v1"

_FLOAT = r"\d+(?:\.\d+)?"
_SUCCESS_RE = re.compile(
    rf"lexical shadow: query_hash=(?P<hash>[0-9a-f]{{12}}) "
    rf"fts_count=(?P<fts>\d+) icu_count=(?P<icu>\d+) "
    rf"overlap=(?P<overlap>\d+) fts_ms=(?P<fts_ms>{_FLOAT}) "
    rf"icu_ms=(?P<icu_ms>{_FLOAT})"
)
_UNAVAILABLE_RE = re.compile(
    rf"lexical shadow unavailable: query_hash=(?P<hash>[0-9a-f]{{12}}) "
    rf"fts_count=(?P<fts>\d+) fts_ms=(?P<fts_ms>{_FLOAT}) "
    rf"icu_ms=(?P<icu_ms>{_FLOAT}) error_type=(?P<error>\w+)"
)
_ICU_FALLBACK_RE = re.compile(
    r"lexical ICU fallback: query_hash=(?P<hash>[0-9a-f]{12}) "
    r"error_type=(?P<error>\w+)"
)
_TIMESTAMP_RE = re.compile(r"^(?P<value>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")


def _classify_shadow_line(
    line: str,
    *,
    since: datetime | None,
    until: datetime | None,
) -> tuple[str, dict[str, int | float | str] | None, datetime | None]:
    if "lexical shadow" not in line and "lexical ICU fallback" not in line:
        return "ignore", None, None
    timestamp = _line_timestamp(line)
    if (since is not None or until is not None) and (
        timestamp is None or (since is not None and timestamp < since) or (until is not None and timestamp >= until)
    ):
        return "filtered", None, timestamp

    match = _SUCCESS_RE.search(line)
    if match is not None:
        return (
            "success",
            {
                "hash": match.group("hash"),
                "fts": int(match.group("fts")),
                "icu": int(match.group("icu")),
                "overlap": int(match.group("overlap")),
                "fts_ms": float(match.group("fts_ms")),
                "icu_ms": float(match.group("icu_ms")),
            },
            timestamp,
        )

    match = _UNAVAILABLE_RE.search(line)
    if match is not None:
        return (
            "unavailable",
            {
                "hash": match.group("hash"),
                "fts": int(match.group("fts")),
                "fts_ms": float(match.group("fts_ms")),
                "icu_ms": float(match.group("icu_ms")),
            },
            timestamp,
        )
    if _ICU_FALLBACK_RE.search(line) is not None:
        return "fallback", None, None
    return "malformed", None, None


def _parse_boundary(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        raise ValueError("--since/--until must be a local timestamp without an offset")
    return parsed


def _line_timestamp(line: str) -> datetime | None:
    match = _TIMESTAMP_RE.match(line)
    if match is None:
        return None
    return datetime.fromisoformat(match.group("value"))


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _distribution(values: list[float]) -> dict[str, int | float | None]:
    return {
        "samples": len(values),
        "p50": _rounded(statistics.median(values)) if values else None,
        "p95": _rounded(_nearest_rank(values, 0.95)),
        "max": _rounded(max(values)) if values else None,
    }


def summarize_lines(
    lines: Iterable[str],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    successes: list[dict[str, int | float | str]] = []
    unavailable: list[dict[str, int | float | str]] = []
    lance_fallbacks = 0
    query_hashes: set[str] = set()
    observation_times: list[datetime] = []
    candidate_lines = 0
    malformed_lines = 0
    filtered_lines = 0

    for line in lines:
        kind, record, timestamp = _classify_shadow_line(
            line,
            since=since,
            until=until,
        )
        if kind == "ignore":
            continue
        candidate_lines += 1
        if kind == "filtered":
            filtered_lines += 1
            continue
        if kind in {"success", "unavailable"}:
            assert record is not None
            (successes if kind == "success" else unavailable).append(record)
            query_hashes.add(str(record["hash"]))
            if timestamp is not None:
                observation_times.append(timestamp)
            continue
        if kind == "fallback":
            lance_fallbacks += 1
            continue
        malformed_lines += 1

    observations = len(successes) + len(unavailable)
    fts_latencies = [float(row["fts_ms"]) for row in [*successes, *unavailable]]
    icu_attempt_latencies = [float(row["icu_ms"]) for row in [*successes, *unavailable]]
    icu_success_latencies = [float(row["icu_ms"]) for row in successes]
    jaccards: list[float] = []
    for row in successes:
        union = int(row["fts"]) + int(row["icu"]) - int(row["overlap"])
        jaccards.append(1.0 if union == 0 else int(row["overlap"]) / union)

    return {
        "schema_version": 1,
        "status": "observed" if observations else "insufficient_data",
        "has_observations": observations > 0,
        "shadow": {
            "observations": observations,
            "successes": len(successes),
            "fallbacks": len(unavailable),
            "success_rate": _rounded(len(successes) / observations) if observations else None,
            "fallback_rate": _rounded(len(unavailable) / observations) if observations else None,
            "unique_query_count": len(query_hashes),
        },
        "latency_ms": {
            "fts5": _distribution(fts_latencies),
            "icu_attempt": _distribution(icu_attempt_latencies),
            "icu_success": _distribution(icu_success_latencies),
        },
        "zero_hit": {
            "fts5": sum(int(row["fts"]) == 0 for row in [*successes, *unavailable]),
            "icu_success": sum(int(row["icu"]) == 0 for row in successes),
        },
        "top_set_overlap": {
            "samples": len(successes),
            "mean_count": _rounded(statistics.fmean(int(row["overlap"]) for row in successes)) if successes else None,
            "jaccard_mean": _rounded(statistics.fmean(jaccards)) if jaccards else None,
            "jaccard_p50": _rounded(statistics.median(jaccards)) if jaccards else None,
            "jaccard_min": _rounded(min(jaccards)) if jaccards else None,
        },
        "lance_icu_fallbacks": lance_fallbacks,
        "observation_window": {
            "first_at": min(observation_times).isoformat() if observation_times else None,
            "last_at": max(observation_times).isoformat() if observation_times else None,
            "distinct_local_dates": len({value.date() for value in observation_times}),
            "timestamped_observations": len(observation_times),
        },
        "input": {
            "candidate_lines": candidate_lines,
            "filtered_lines": filtered_lines,
            "malformed_lines": malformed_lines,
        },
    }


def load_policy(path: Path) -> tuple[dict[str, int | float | str], str]:
    raw = path.read_bytes()
    policy = json.loads(raw)
    if not isinstance(policy, dict) or policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError("unsupported lexical shadow policy schema")
    integer_fields = (
        "min_observations",
        "min_unique_queries",
        "min_distinct_local_dates",
        "max_malformed_lines",
        "max_lance_icu_fallbacks",
    )
    for field in integer_fields:
        value = policy.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"policy {field} must be a non-negative integer")
    float_fields = ("max_fallback_rate", "max_icu_success_p95_ms")
    for field in float_fields:
        value = policy.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"policy {field} must be a non-negative number")
    if float(policy["max_fallback_rate"]) > 1:
        raise ValueError("policy max_fallback_rate must be at most 1")
    return policy, hashlib.sha256(raw).hexdigest()


def evaluate_gate(
    summary: dict[str, Any],
    policy: dict[str, int | float | str],
    policy_sha256: str,
) -> dict[str, Any]:
    pending_reasons: list[str] = []
    failure_reasons: list[str] = []
    shadow = summary["shadow"]
    window = summary["observation_window"]
    if shadow["observations"] < policy["min_observations"]:
        pending_reasons.append("min_observations")
    if shadow["unique_query_count"] < policy["min_unique_queries"]:
        pending_reasons.append("min_unique_queries")
    if window["distinct_local_dates"] < policy["min_distinct_local_dates"]:
        pending_reasons.append("min_distinct_local_dates")
    if window["timestamped_observations"] != shadow["observations"]:
        failure_reasons.append("missing_observation_timestamp")
    fallback_rate = shadow["fallback_rate"]
    if fallback_rate is not None and fallback_rate > policy["max_fallback_rate"]:
        failure_reasons.append("max_fallback_rate")
    icu_p95 = summary["latency_ms"]["icu_success"]["p95"]
    if icu_p95 is not None and icu_p95 > policy["max_icu_success_p95_ms"]:
        failure_reasons.append("max_icu_success_p95_ms")
    if summary["input"]["malformed_lines"] > policy["max_malformed_lines"]:
        failure_reasons.append("max_malformed_lines")
    if summary["lance_icu_fallbacks"] > policy["max_lance_icu_fallbacks"]:
        failure_reasons.append("max_lance_icu_fallbacks")

    status = "failed" if failure_reasons else "pending" if pending_reasons else "passed"
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "status": status,
        "policy_sha256": policy_sha256,
        "pending_reasons": pending_reasons,
        "failure_reasons": failure_reasons,
        "thresholds": policy,
    }


def _read_lines(paths: Sequence[Path]) -> Iterable[str]:
    if not paths:
        yield from sys.stdin
        return
    for path in paths:
        with path.open(encoding="utf-8", errors="replace") as stream:
            yield from stream


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="log files; stdin when omitted")
    parser.add_argument("--since", help="inclusive local ISO timestamp")
    parser.add_argument("--until", help="exclusive local ISO timestamp")
    parser.add_argument("--policy", type=Path, help="operational promotion gate policy JSON")
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="return 0 for pass, 1 for failure, or 2 while observations are pending",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        since = _parse_boundary(args.since)
        until = _parse_boundary(args.until)
    except ValueError as exc:
        _build_parser().error(str(exc))
    if since is not None and until is not None and since >= until:
        _build_parser().error("--since must be earlier than --until")
    if args.fail_on_gate and args.policy is None:
        _build_parser().error("--fail-on-gate requires --policy")
    result = summarize_lines(_read_lines(args.paths), since=since, until=until)
    if args.policy is not None:
        try:
            policy, policy_sha256 = load_policy(args.policy)
            result["gate"] = evaluate_gate(result, policy, policy_sha256)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            _build_parser().error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.fail_on_gate:
        return {"passed": 0, "failed": 1, "pending": 2}[result["gate"]["status"]]
    return 0 if result["has_observations"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
