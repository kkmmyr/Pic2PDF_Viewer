"""Ornith Gate B2: 4ページ窓とnative JSON Schemaで事実抽出を隔離評価する。

現行20ページGate Bの不合格は変更しない。Linux本番DBをSSH越しにread-onlyで
参照し、固定8〜27ページを5窓へ分割して、件数・page・文字数を生成時に拘束する。
公開DB、索引、checkpoint、環境変数は変更しない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import time
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from local_llm._json_output import normalize_json_object
from services.novel_db.generation_quality import format_page_blocks

BOOK_ID = 46
BOOK_NAME = "茉莉花官吏伝 十　中原の鹿を逐わず (ビーズログ文庫)"
SOURCE_PAGES = tuple(range(8, 28))
SOURCE_SHA256 = "47f62bc67042c39dbf09d0b9213041d8a6a048c98a41a5d0e3341292f6c15007"
LEDGER_SHA256 = "3c93cdb7f234e530f320ef00724136115785b4757000c58461eff1704576d86c"
BLOCK_RANGES = ((8, 11), (12, 15), (16, 19), (20, 23), (24, 27))
DEFAULT_MODEL = Path(
    "/Users/medaro/.local/share/pic2pdf-mlx/models/ornith-1.5-35b-a3b-4bit",
)
DEFAULT_SEED = 20260813
MAX_FACTS_PER_BLOCK = 12

# 日本語の新字体と同形の文字を除いた簡体字専用文字。読書会M4と同じ集合。
SIMPLIFIED_ONLY_CHARS = frozenset(
    "们这说话对时东车买卖门问间闻马鸟读谁谢过还进运鱼头实变让认识请调谈论"
    "语见觉观现发书长风飞爱乐电汉华关开张阳阴难题单满战术众优传场评级绝纯"
    "黑"
)
OBVIOUS_CHINESE_FRAGMENTS = (
    "最好",
    "心地而感到",
    "夕方法与夜",
    "的人都",
    "那也是",
    "家庭教师",
    "与生徒",
    "这是",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default="http://127.0.0.1:11440")
    parser.add_argument("--ssh-host", default="medaroserver")
    parser.add_argument(
        "--remote-db",
        default="/opt/pic2pdf-viewer/data/novel_db/novel.db",
    )
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=None,
        help=(
            "Optional MLX-VLM reasoning-token budget. Omit for the original "
            "Gate B2 protocol; use 4096 for the isolated Gate B3 diagnostic."
        ),
    )
    return parser.parse_args()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _read_remote_json(args: argparse.Namespace, sql: str) -> list[dict[str, Any]]:
    remote_command = (
        f"sqlite3 -readonly -json {shlex.quote(args.remote_db)} {shlex.quote(sql)}"
    )
    raw = subprocess.check_output(
        ["ssh", "-o", "BatchMode=yes", args.ssh_host, remote_command],
        text=True,
    )
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise RuntimeError("remote sqlite query did not return a JSON row array")
    return value


def _load_fixture(
    args: argparse.Namespace,
) -> tuple[list[tuple[int, str]], list[str], str]:
    book_rows = _read_remote_json(
        args,
        f"SELECT name FROM books WHERE id={BOOK_ID};",
    )
    if book_rows != [{"name": BOOK_NAME}]:
        raise RuntimeError(f"book fixture mismatch: {book_rows!r}")

    page_rows = _read_remote_json(
        args,
        "SELECT page_no,full_text FROM pages "
        f"WHERE book_id={BOOK_ID} AND page_no BETWEEN 8 AND 27 ORDER BY page_no;",
    )
    pages = [(int(row["page_no"]), str(row["full_text"])) for row in page_rows]
    if tuple(page_no for page_no, _ in pages) != SOURCE_PAGES:
        raise RuntimeError("source fixture did not contain exactly pages 8 through 27")
    if _sha256(format_page_blocks(pages)) != SOURCE_SHA256:
        raise RuntimeError("source SHA-256 mismatch")

    ledger_rows = _read_remote_json(
        args,
        "SELECT name FROM book_characters "
        f"WHERE book_id={BOOK_ID} ORDER BY first_page,name;",
    )
    canonical_names = [str(row["name"]) for row in ledger_rows]
    ledger = "\n".join(f"- {name}" for name in canonical_names)
    if _sha256(ledger) != LEDGER_SHA256:
        raise RuntimeError("character ledger SHA-256 mismatch")
    return pages, canonical_names, ledger


def _build_schema(
    allowed_pages: list[int],
    canonical_names: list[str],
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["facts"],
        "properties": {
            "facts": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_FACTS_PER_BLOCK,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "page",
                        "subject",
                        "action",
                        "reason_or_result",
                        "canonical_characters",
                    ],
                    "properties": {
                        "page": {"type": "integer", "enum": allowed_pages},
                        "subject": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 40,
                        },
                        "action": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 180,
                        },
                        "reason_or_result": {
                            "type": "string",
                            "maxLength": 180,
                        },
                        "canonical_characters": {
                            "type": "array",
                            "maxItems": 4,
                            "items": {"type": "string", "enum": canonical_names},
                        },
                    },
                },
            },
        },
    }


def _build_prompt(
    pages: list[tuple[int, str]],
    ledger: str,
    *,
    block_index: int,
) -> str:
    return f"""次は小説『{BOOK_NAME}』の本文の一部です（固定5窓中{block_index}番目）。
後段で安全な要約を作る材料として、重要な事実だけを最大{MAX_FACTS_PER_BLOCK}件抽出してください。

規則:
- 1件を一つの行動、判断、発言、状態変化に限定する。
- pageは、その事実が実際に起きる主たる1ページだけを選ぶ。次ページのmarkerを根拠として付け足さない。
- subjectは代名詞を避け、発言者・行為者・判断者を明示する。
- actionには誰が何をしたか、reason_or_resultには本文に明記された理由または結果だけを書く。
- 本文の細部を逐語的に再掲せず、因果、決定、任務、関係変化を優先する。
- 出力文字列は自然な日本語だけを使い、中国語・英語を混ぜない。
- canonical_charactersには、その事実に関係する公開人物名だけを下の正規表記で入れる。
- 台帳にない人物を推測で追加せず、台帳名だけから出来事を補完しない。
- 窓の冒頭・中央・末尾を覆い、本文にない設定・心理・結果を作らない。

公開版人物名台帳:
{ledger}

本文:
{format_page_blocks(pages)}
"""


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
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"MLX-VLM request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("server returned a non-object response")
    return value


def _language_leaks(facts: list[dict[str, Any]]) -> list[str]:
    leaks: list[str] = []
    for index, fact in enumerate(facts, start=1):
        value = " ".join(
            str(fact.get(key, "")) for key in ("subject", "action", "reason_or_result")
        )
        chars = sorted(set(value) & SIMPLIFIED_ONLY_CHARS)
        if chars:
            leaks.append(f"fact {index}: simplified chars={''.join(chars)}")
        for fragment in OBVIOUS_CHINESE_FRAGMENTS:
            if fragment in value:
                leaks.append(f"fact {index}: Chinese fragment={fragment}")
    return leaks


def _validate_facts(
    parsed: dict[str, Any] | None,
    *,
    allowed_pages: set[int],
    canonical_names: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    if not isinstance(parsed, dict) or set(parsed) != {"facts"}:
        return [], ["root is not the required facts-only object"]
    facts = parsed.get("facts")
    if not isinstance(facts, list) or not 1 <= len(facts) <= MAX_FACTS_PER_BLOCK:
        return [], ["facts count is outside 1..12"]

    required = {
        "page",
        "subject",
        "action",
        "reason_or_result",
        "canonical_characters",
    }
    signatures: set[tuple[Any, Any, Any]] = set()
    validated: list[dict[str, Any]] = []
    for index, fact in enumerate(facts, start=1):
        if not isinstance(fact, dict) or set(fact) != required:
            issues.append(f"fact {index}: keys mismatch")
            continue
        page = fact["page"]
        subject = fact["subject"]
        action = fact["action"]
        reason = fact["reason_or_result"]
        characters = fact["canonical_characters"]
        if page not in allowed_pages:
            issues.append(f"fact {index}: page outside block: {page}")
        if not isinstance(subject, str) or not 1 <= len(subject) <= 40:
            issues.append(f"fact {index}: invalid subject")
        if not isinstance(action, str) or not 1 <= len(action) <= 180:
            issues.append(f"fact {index}: invalid action")
        if not isinstance(reason, str) or len(reason) > 180:
            issues.append(f"fact {index}: invalid reason_or_result")
        if (
            not isinstance(characters, list)
            or len(characters) > 4
            or any(
                not isinstance(name, str) or name not in canonical_names
                for name in characters
            )
        ):
            issues.append(f"fact {index}: invalid canonical_characters")
        signature = (page, subject, action)
        if signature in signatures:
            issues.append(f"fact {index}: duplicate fact")
        signatures.add(signature)
        validated.append(fact)
    issues.extend(_language_leaks(validated))
    return validated, issues


def _fact_text(fact: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            str(fact["subject"]),
            str(fact["action"]),
            str(fact["reason_or_result"]),
        )
        if part
    )


def _semantic_checks(facts: list[dict[str, Any]]) -> dict[str, bool]:
    def matches(page: int, subject: str, *phrases: str) -> bool:
        return any(
            fact["page"] == page
            and subject in str(fact["subject"])
            and all(phrase in _fact_text(fact) for phrase in phrases)
            for fact in facts
        )

    page_10_unique_is_not_matsurika = not any(
        fact["page"] == 10
        and "皓茉莉花" in str(fact["subject"])
        and "唯一で完璧" in _fact_text(fact)
        for fact in facts
    )
    no_later_scene_on_18_19 = not any(
        fact["page"] in {18, 19}
        and any(phrase in _fact_text(fact) for phrase in ("歓迎の宴", "黒曜城で過ご"))
        for fact in facts
    )
    collision_not_moved_to_27 = not any(
        fact["page"] == 27
        and "新人文官" in _fact_text(fact)
        and "ぶつか" in _fact_text(fact)
        and "命じ" in _fact_text(fact)
        for fact in facts
    )
    page_8_matsurika_worry = any(
        fact["page"] == 8
        and "皓茉莉花" in str(fact["subject"])
        and "戦争" in _fact_text(fact)
        for fact in facts
    )
    page_8_hakuyo_does_not_inherit_matsurika_reason = not any(
        fact["page"] == 8
        and "珀陽" in str(fact["subject"])
        and any(
            phrase in _fact_text(fact)
            for phrase in ("白楼国を平和にしたくて", "答えを今出せて")
        )
        for fact in facts
    )
    page_18_recommender_relation_is_present = any(
        fact["page"] == 18
        and any(
            phrase in _fact_text(fact)
            for phrase in (
                "科挙試験の推薦人である芳子星",
                "芳子星は皓茉莉花の科挙試験の推薦人",
            )
        )
        for fact in facts
    )
    page_18_recommender_relation_not_reversed = not any(
        fact["page"] == 18 and "皓茉莉花は芳子星の科挙試験の推薦人" in _fact_text(fact)
        for fact in facts
    )
    page_25_new_clerk_reason_not_matsurika_plan = not any(
        fact["page"] in {25, 26}
        and "新人文官" in str(fact["subject"])
        and any(phrase in str(fact["reason_or_result"]) for phrase in ("四日", "準備"))
        for fact in facts
    )
    page_26_hua_role_not_mapped_to_shokei = not any(
        fact["page"] == 26
        and "華副三司使" in _fact_text(fact)
        and "苑翔景" in fact["canonical_characters"]
        for fact in facts
    )
    return {
        "page_8_matsurika_worries_about_war": page_8_matsurika_worry,
        "page_8_hakuyo_does_not_inherit_matsurika_reason": (
            page_8_hakuyo_does_not_inherit_matsurika_reason
        ),
        "page_10_kosei_speaks_about_unique_answer": matches(
            10,
            "芳子星",
            "唯一で完璧",
        ),
        "page_10_hakuyo_says_likes_both": matches(10, "珀陽", "両方", "好き"),
        "page_10_unique_answer_not_attributed_to_matsurika": page_10_unique_is_not_matsurika,
        "page_18_hakuyo_sends_matsurika_away": any(
            fact["page"] == 18
            and "珀陽" in str(fact["subject"])
            and any(phrase in _fact_text(fact) for phrase in ("国外", "月長城から遠ざ"))
            for fact in facts
        ),
        "page_18_kosei_is_matsurika_recommender": (
            page_18_recommender_relation_is_present
        ),
        "page_18_recommender_relation_not_reversed": (
            page_18_recommender_relation_not_reversed
        ),
        "page_18_19_not_later_welcome_scene": no_later_scene_on_18_19,
        "page_25_26_new_clerk_reason_not_matsurika_plan": (
            page_25_new_clerk_reason_not_matsurika_plan
        ),
        "page_26_collision_order_stays_on_26": any(
            fact["page"] == 26
            and "新人文官" in _fact_text(fact)
            and "ぶつか" in _fact_text(fact)
            and "命じ" in _fact_text(fact)
            for fact in facts
        ),
        "page_26_collision_order_not_moved_to_27": collision_not_moved_to_27,
        "page_26_hua_role_not_mapped_to_shokei": (
            page_26_hua_role_not_mapped_to_shokei
        ),
        "page_27_identity_doubt_is_present": any(
            fact["page"] == 27
            and any(
                phrase in _fact_text(fact) for phrase in ("同一人物", "別人", "荷物")
            )
            for fact in facts
        ),
    }


def _derive_character_facts(
    facts: list[dict[str, Any]],
    canonical_names: list[str],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in canonical_names}
    for fact in facts:
        for name in dict.fromkeys(fact["canonical_characters"]):
            grouped[name].append(
                {
                    "page": fact["page"],
                    "text": _fact_text(fact),
                },
            )
    return {name: items for name, items in grouped.items() if items}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    args = _parse_args()
    if args.thinking_budget is not None and not (
        0 < args.thinking_budget < args.max_tokens
    ):
        raise RuntimeError("thinking budget must be between 1 and max-tokens - 1")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise RuntimeError(f"output directory is not empty: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.model.is_dir():
        raise RuntimeError(f"model directory does not exist: {args.model}")

    pages, canonical_names, ledger = _load_fixture(args)
    page_map = dict(pages)
    results: list[dict[str, Any]] = []
    all_facts: list[dict[str, Any]] = []
    for block_index, (page_start, page_end) in enumerate(BLOCK_RANGES, start=1):
        block_pages = [
            (page, page_map[page]) for page in range(page_start, page_end + 1)
        ]
        prompt = _build_prompt(block_pages, ledger, block_index=block_index)
        schema = _build_schema(
            [page for page, _ in block_pages],
            canonical_names,
        )
        body = {
            "model": str(args.model),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "max_tokens": args.max_tokens,
            "temperature": 0.6,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "seed": args.seed,
            "enable_thinking": True,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": f"ornith_book_facts_{page_start}_{page_end}",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        if args.thinking_budget is not None:
            body["thinking_budget"] = args.thinking_budget
        print(
            json.dumps(
                {
                    "event": "start",
                    "block": block_index,
                    "pages": [page_start, page_end],
                    "thinking_budget": args.thinking_budget,
                },
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
        parsed: dict[str, Any] | None = None
        parse_error: str | None = None
        try:
            normalized = normalize_json_object(content)
            value = json.loads(normalized)
            if not isinstance(value, dict):
                raise RuntimeError("structured content was not an object")
            parsed = value
        except (json.JSONDecodeError, RuntimeError) as exc:
            parse_error = str(exc)

        facts, validation_issues = _validate_facts(
            parsed,
            allowed_pages=set(range(page_start, page_end + 1)),
            canonical_names=set(canonical_names),
        )
        covered_pages = sorted({int(fact["page"]) for fact in facts})
        coverage_pass = covered_pages == list(range(page_start, page_end + 1))
        block_pass = bool(
            finish_reason == "stop"
            and parse_error is None
            and not validation_issues
            and coverage_pass
            and isinstance(reasoning, str)
            and reasoning
        )
        result = {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "block": block_index,
            "pages": [page_start, page_end],
            "source_sha256": _sha256(format_page_blocks(block_pages)),
            "prompt_sha256": _sha256(prompt),
            "schema_sha256": _sha256(
                json.dumps(schema, ensure_ascii=False, sort_keys=True)
            ),
            "wall_seconds": round(elapsed, 3),
            "finish_reason": finish_reason,
            "usage": raw.get("usage") or {},
            "reasoning_chars": len(reasoning),
            "content_chars": len(content),
            "parse_error": parse_error,
            "validation_issues": validation_issues,
            "fact_count": len(facts),
            "covered_pages": covered_pages,
            "coverage_pass": coverage_pass,
            "block_pass": block_pass,
            "parsed": parsed,
            "raw_response": raw,
        }
        results.append(result)
        all_facts.extend(facts)
        _write_json(args.output_dir / f"block-{block_index}.json", result)
        print(
            json.dumps(
                {
                    "event": "result",
                    "block": block_index,
                    "pages": [page_start, page_end],
                    "block_pass": block_pass,
                    "finish_reason": finish_reason,
                    "fact_count": len(facts),
                    "covered_pages": covered_pages,
                    "validation_issues": validation_issues,
                    "wall_seconds": result["wall_seconds"],
                    "completion_tokens": result["usage"].get("completion_tokens"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    semantic_checks = _semantic_checks(all_facts)
    semantic_gate_pass = all(semantic_checks.values())
    all_pages = sorted({int(fact["page"]) for fact in all_facts})
    full_coverage_pass = all_pages == list(SOURCE_PAGES)
    gate_pass = bool(
        all(result["block_pass"] for result in results)
        and full_coverage_pass
        and semantic_gate_pass
    )
    derived_character_facts = _derive_character_facts(all_facts, canonical_names)
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runtime": "mlx_vlm",
        "model": str(args.model),
        "book_id": BOOK_ID,
        "book_name": BOOK_NAME,
        "source_pages": [SOURCE_PAGES[0], SOURCE_PAGES[-1]],
        "source_sha256": SOURCE_SHA256,
        "ledger_sha256": LEDGER_SHA256,
        "protocol": {
            "block_ranges": [list(value) for value in BLOCK_RANGES],
            "max_facts_per_block": MAX_FACTS_PER_BLOCK,
            "temperature": 0.6,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "seed": args.seed,
            "max_tokens": args.max_tokens,
            "enable_thinking": True,
            "thinking_budget": args.thinking_budget,
            "max_num_seqs": 1,
            "native_json_schema": True,
        },
        "blocks": [
            {
                key: result[key]
                for key in (
                    "block",
                    "pages",
                    "source_sha256",
                    "prompt_sha256",
                    "schema_sha256",
                    "wall_seconds",
                    "finish_reason",
                    "usage",
                    "reasoning_chars",
                    "content_chars",
                    "parse_error",
                    "validation_issues",
                    "fact_count",
                    "covered_pages",
                    "coverage_pass",
                    "block_pass",
                )
            }
            for result in results
        ],
        "fact_count": len(all_facts),
        "covered_pages": all_pages,
        "full_coverage_pass": full_coverage_pass,
        "semantic_checks": semantic_checks,
        "semantic_gate_pass": semantic_gate_pass,
        "gate_pass": gate_pass,
        "manual_review_required": True,
    }
    _write_json(
        args.output_dir / "fixture.json",
        {
            "book_id": BOOK_ID,
            "book_name": BOOK_NAME,
            "pages": [{"page_no": page, "full_text": text} for page, text in pages],
            "canonical_character_names": canonical_names,
            "source_sha256": SOURCE_SHA256,
            "ledger_sha256": LEDGER_SHA256,
        },
    )
    _write_json(args.output_dir / "facts.json", all_facts)
    _write_json(
        args.output_dir / "derived-character-facts.json",
        derived_character_facts,
    )
    _write_json(args.output_dir / "summary.json", summary)
    print(
        json.dumps(
            {
                "event": "complete",
                "gate_pass": gate_pass,
                "fact_count": len(all_facts),
                "full_coverage_pass": full_coverage_pass,
                "semantic_checks": semantic_checks,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
