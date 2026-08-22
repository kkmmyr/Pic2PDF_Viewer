"""Ornith 1.5の固定74〜75ページをMLX-LM / MLX-VLMで再評価する。

Linux本番DBはSSH越しにread-onlyで参照し、固定source / prompt hashが一致した場合だけ
3 seedのThinking試験を行う。公開DB、索引、checkpoint、環境変数は変更しない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from local_llm import BackendConfig, MlxBackend, MlxLmBackend
from local_llm._json_output import normalize_json_events, normalize_json_object

SOURCE_SHA256 = "7a44d23a1bdb263c7a67bcc3efa1405f1c3eeec33e076ff12efd3644e00e0f4e"
PROMPT_SHA256 = "4ce54b1fe01087b4b47eb584e8e630db88356541d90f76f64d899451b88bbeba"
DEFAULT_MODEL = Path(
    "/Users/medaro/.local/share/pic2pdf-mlx/models/ornith-1.5-35b-a3b-4bit",
)
REQUIRED_KEYS = {
    "final_action",
    "old_fact_status",
    "erroneous_summary_status",
    "reason",
}
STATUS_VALUES = {
    "supported",
    "contradicted",
    "partially_contradicted",
    "insufficient",
}
ACTION_VALUES = {
    "return_to_prison",
    "continue_fleeing_up_to_10_years",
    "other",
    "unclear",
}
SEEDS = (20260821, 20260822, 20260823)

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "final_action",
        "old_fact_status",
        "erroneous_summary_status",
        "reason",
    ],
    "properties": {
        "final_action": {"type": "string", "enum": sorted(ACTION_VALUES)},
        "old_fact_status": {"type": "string", "enum": sorted(STATUS_VALUES)},
        "erroneous_summary_status": {
            "type": "string",
            "enum": sorted(STATUS_VALUES),
        },
        "reason": {"type": "string", "minLength": 1},
    },
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, choices=("mlx_lm", "mlx_vlm"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default="http://127.0.0.1:11440")
    parser.add_argument("--ssh-host", default="medaroserver")
    parser.add_argument(
        "--remote-db",
        default="/opt/pic2pdf-viewer/data/novel_db/novel.db",
    )
    parser.add_argument("--book-id", type=int, default=46)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-tokens", type=int, default=8192)
    return parser.parse_args()


def _load_fixed_source(args: argparse.Namespace) -> str:
    sql = (
        "SELECT page_no,full_text FROM pages "
        f"WHERE book_id={args.book_id} AND page_no IN (74,75) ORDER BY page_no;"
    )
    remote_command = (
        f"sqlite3 -readonly -json {shlex.quote(args.remote_db)} {shlex.quote(sql)}"
    )
    source_raw = subprocess.check_output(
        ["ssh", "-o", "BatchMode=yes", args.ssh_host, remote_command],
        text=True,
    )
    pages = json.loads(source_raw)
    source = "\n\n".join(
        f"[page {row['page_no']}]\n{row['full_text']}" for row in pages
    )
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    if source_hash != SOURCE_SHA256:
        raise RuntimeError(f"source SHA-256 mismatch: {source_hash}")
    return source


def _build_prompt(source: str) -> str:
    prompt = f"""次の本文を読み、終盤の合意について判定してください。

判定対象:
- final_action: 仁耀が最後に受け入れた行動
- old_fact_status: 「仁耀は牢へ戻り裁きを受けることになった」という事実メモの整合性
- erroneous_summary_status: 「仁耀は最終的に牢へ戻った」という要約の整合性

status は supported / contradicted / partially_contradicted / insufficient のいずれかです。
final_action は return_to_prison / continue_fleeing_up_to_10_years / other / unclear のいずれかです。
reason には、途中の発言と最終合意を区別して根拠を簡潔に書いてください。

出力は次の4キーだけを持つ単一のJSON objectにしてください。
{{"final_action":"...","old_fact_status":"...","erroneous_summary_status":"...","reason":"..."}}

本文:
{source}
"""
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    if prompt_hash != PROMPT_SHA256:
        raise RuntimeError(f"prompt SHA-256 mismatch: {prompt_hash}")
    return prompt


def _build_request_body(
    args: argparse.Namespace,
    prompt: str,
    *,
    seed: int,
) -> dict[str, Any]:
    config = BackendConfig(
        base_url=args.base_url,
        model=str(args.model),
        timeout=args.timeout,
        default_options={
            "temperature": 0.6,
            "top_p": 0.95,
            "top_k": 20,
            "seed": seed,
            "num_predict": args.max_tokens,
        },
    )
    backend = MlxLmBackend(config) if args.runtime == "mlx_lm" else MlxBackend(config)
    body = backend._build_body(
        prompt,
        system=None,
        model=None,
        options=None,
        think=True,
        format="json",
    )
    body["stream"] = False
    if args.runtime == "mlx_vlm":
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "ornith_final_agreement",
                "strict": True,
                "schema": RESPONSE_SCHEMA,
            },
        }
    return body


def _post_json(
    base_url: str,
    body: dict[str, Any],
    *,
    timeout: int,
) -> dict[str, Any]:
    request = Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        value = json.loads(response.read().decode())
    if not isinstance(value, dict):
        raise RuntimeError("server returned a non-object response")
    return value


def _strict_raw_object(content: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = content.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None, "content is not a bare JSON object"
    try:
        normalized = normalize_json_object(content)
        parsed = json.loads(normalized)
    except (json.JSONDecodeError, RuntimeError) as exc:
        return None, str(exc)
    return parsed, None


def _adapt_mlx_lm_content(
    content: str,
    *,
    finish_reason: str | None,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    events = [
        {"response": content, "done": False},
        {"response": "", "done": True, "done_reason": finish_reason},
    ]
    try:
        normalized_events = list(normalize_json_events(events))
        normalized = "".join(event.get("response", "") for event in normalized_events)
        parsed = json.loads(normalized)
    except (json.JSONDecodeError, RuntimeError) as exc:
        return None, None, str(exc)
    return normalized, parsed, None


def _evaluate_parsed(parsed: dict[str, Any] | None) -> dict[str, bool]:
    keys_pass = isinstance(parsed, dict) and set(parsed) == REQUIRED_KEYS
    enum_pass = bool(
        keys_pass
        and parsed["final_action"] in ACTION_VALUES
        and parsed["old_fact_status"] in STATUS_VALUES
        and parsed["erroneous_summary_status"] in STATUS_VALUES
        and isinstance(parsed["reason"], str)
    )
    semantic_pass = bool(
        enum_pass
        and parsed["final_action"] == "continue_fleeing_up_to_10_years"
        and parsed["old_fact_status"] in {"contradicted", "partially_contradicted"}
        and parsed["erroneous_summary_status"] == "contradicted"
    )
    japanese_names_pass = bool(
        semantic_pass and "仁耀" in parsed["reason"] and "珀陽" in parsed["reason"]
    )
    return {
        "keys_pass": keys_pass,
        "enum_pass": enum_pass,
        "semantic_pass": semantic_pass,
        "japanese_names_pass": japanese_names_pass,
    }


def _request_contract(body: dict[str, Any], runtime: str) -> dict[str, Any]:
    return {
        "runtime": runtime,
        "stream": body["stream"],
        "temperature": body["temperature"],
        "top_p": body["top_p"],
        "top_k": body["top_k"],
        "seed": body["seed"],
        "max_tokens": body["max_tokens"],
        "enable_thinking": body.get("enable_thinking"),
        "chat_template_kwargs": body.get("chat_template_kwargs"),
        "response_format": body.get("response_format"),
    }


def _run_trial(
    args: argparse.Namespace,
    prompt: str,
    *,
    trial: int,
    seed: int,
) -> dict[str, Any]:
    body = _build_request_body(args, prompt, seed=seed)
    print(
        json.dumps(
            {"event": "start", "runtime": args.runtime, "trial": trial, "seed": seed},
            ensure_ascii=False,
        ),
        flush=True,
    )
    started = time.monotonic()
    raw = _post_json(args.base_url, body, timeout=args.timeout)
    elapsed = time.monotonic() - started

    choice = raw["choices"][0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    finish_reason = choice.get("finish_reason")
    raw_parsed, raw_parse_error = _strict_raw_object(content)

    adapted_content: str | None = None
    adapter_error: str | None = None
    if args.runtime == "mlx_lm":
        adapted_content, parsed, adapter_error = _adapt_mlx_lm_content(
            content,
            finish_reason=finish_reason,
        )
    else:
        parsed = raw_parsed

    checks = _evaluate_parsed(parsed)
    stop_pass = finish_reason == "stop"
    reasoning_contract_pass = isinstance(reasoning, str) and bool(reasoning)
    output_contract_pass = (
        adapter_error is None if args.runtime == "mlx_lm" else raw_parse_error is None
    )
    passed = bool(
        output_contract_pass
        and checks["keys_pass"]
        and checks["enum_pass"]
        and checks["semantic_pass"]
        and checks["japanese_names_pass"]
        and stop_pass
        and reasoning_contract_pass
    )

    result = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runtime": args.runtime,
        "trial": trial,
        "seed": seed,
        "model": str(args.model),
        "source_pages": [74, 75],
        "source_sha256": SOURCE_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "request_contract": _request_contract(body, args.runtime),
        "wall_seconds": round(elapsed, 3),
        "finish_reason": finish_reason,
        "usage": raw.get("usage") or {},
        "reasoning_chars": len(reasoning),
        "content_chars": len(content),
        "raw_json_pass": raw_parse_error is None,
        "raw_parse_error": raw_parse_error,
        "adapter_used": args.runtime == "mlx_lm",
        "adapter_error": adapter_error,
        "adapted_content": adapted_content,
        **checks,
        "stop_pass": stop_pass,
        "reasoning_contract_pass": reasoning_contract_pass,
        "output_contract_pass": output_contract_pass,
        "passed": passed,
        "parsed": parsed,
        "raw_response": raw,
    }
    print(
        json.dumps(
            {
                "event": "result",
                "runtime": args.runtime,
                "trial": trial,
                "passed": passed,
                "raw_json_pass": result["raw_json_pass"],
                "output_contract_pass": output_contract_pass,
                "semantic_pass": checks["semantic_pass"],
                "japanese_names_pass": checks["japanese_names_pass"],
                "finish_reason": finish_reason,
                "wall_seconds": result["wall_seconds"],
                "completion_tokens": result["usage"].get("completion_tokens"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return result


def main() -> int:
    args = _parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise RuntimeError(f"output directory is not empty: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.model.is_dir():
        raise RuntimeError(f"model directory does not exist: {args.model}")

    source = _load_fixed_source(args)
    prompt = _build_prompt(source)
    results = []
    for trial, seed in enumerate(SEEDS, start=1):
        result = _run_trial(args, prompt, trial=trial, seed=seed)
        results.append(result)
        (args.output_dir / f"thinking-{trial}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runtime": args.runtime,
        "model": str(args.model),
        "source_sha256": SOURCE_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "pass_count": sum(result["passed"] for result in results),
        "gate_pass": all(result["passed"] for result in results),
        "raw_json_pass_count": sum(result["raw_json_pass"] for result in results),
        "trials": [
            {
                key: result[key]
                for key in (
                    "trial",
                    "seed",
                    "wall_seconds",
                    "finish_reason",
                    "usage",
                    "reasoning_chars",
                    "content_chars",
                    "raw_json_pass",
                    "raw_parse_error",
                    "adapter_used",
                    "adapter_error",
                    "keys_pass",
                    "enum_pass",
                    "semantic_pass",
                    "japanese_names_pass",
                    "stop_pass",
                    "reasoning_contract_pass",
                    "output_contract_pass",
                    "passed",
                    "parsed",
                )
            }
            for result in results
        ],
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "event": "complete",
                "runtime": args.runtime,
                "gate_pass": summary["gate_pass"],
                "pass_count": summary["pass_count"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if summary["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
