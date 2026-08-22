"""Ornith Gate B4: 単ページ・原文引用先行で高リスク主張を隔離診断する。

Gate B2/B3の日本語小説RAG不採用は変更しない。保存済み固定fixtureの
高リスク6ページだけをread-onlyで使い、引用の完全一致と主体包含を
決定的に検査する。公開DB、索引、checkpoint、環境変数は変更しない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from services.novel_db.generation_quality import format_page_blocks

BOOK_ID = 46
BOOK_NAME = "茉莉花官吏伝 十　中原の鹿を逐わず (ビーズログ文庫)"
SOURCE_PAGES = tuple(range(8, 28))
TARGET_PAGES = (8, 10, 18, 25, 26, 27)
SOURCE_SHA256 = "47f62bc67042c39dbf09d0b9213041d8a6a048c98a41a5d0e3341292f6c15007"
DEFAULT_MODEL = Path(
    "/Users/medaro/.local/share/pic2pdf-mlx/models/ornith-1.5-35b-a3b-4bit",
)
DEFAULT_SEED = 20260813
MAX_RECORDS_PER_PAGE = 4

QUESTIONS = {
    8: "戦争をするかどうかに葛藤している人物と、その人物が本文で述べる理由は何か。",
    10: "『唯一で完璧な正答』について、子星と珀陽はそれぞれ何と言ったか。",
    18: "誰が茉莉花を国外へ出すと決めたか。子星と茉莉花の科挙試験の推薦人関係はどちら向きか。",
    25: "年若い文官との衝突で、このページだけから観測できる行動と結果は何か。後の説明を推測しないこと。",
    26: "新人文官は何を命じられていたか。華副三司使たちは暗茉莉花について何を疑っているか。",
    27: "暗茉莉花に関する同一人物疑惑は何か。また、来現は犀輿に何を許可したか。",
}

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
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default="http://127.0.0.1:11440")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--thinking-budget", type=int, default=2048)
    return parser.parse_args()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _load_fixture(path: Path) -> list[tuple[int, str]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("fixture root is not an object")
    if value.get("book_id") != BOOK_ID or value.get("book_name") != BOOK_NAME:
        raise RuntimeError("fixture book identity mismatch")
    rows = value.get("pages")
    if not isinstance(rows, list):
        raise RuntimeError("fixture pages are missing")
    pages = [
        (int(row["page_no"]), str(row["full_text"]))
        for row in rows
        if isinstance(row, dict)
    ]
    if tuple(page for page, _ in pages) != SOURCE_PAGES:
        raise RuntimeError("fixture did not contain exactly pages 8 through 27")
    if _sha256(format_page_blocks(pages)) != SOURCE_SHA256:
        raise RuntimeError("fixture source SHA-256 mismatch")
    return pages


def _build_schema(page: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["evidence_records"],
        "properties": {
            "evidence_records": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_RECORDS_PER_PAGE,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["page", "evidence", "subject_span", "claim"],
                    "properties": {
                        "page": {"type": "integer", "enum": [page]},
                        "evidence": {
                            "type": "string",
                            "minLength": 20,
                            "maxLength": 360,
                        },
                        "subject_span": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 40,
                        },
                        "claim": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 160,
                        },
                    },
                },
            },
        },
    }


def _build_prompt(page: int, source_text: str) -> str:
    return f"""次は小説『{BOOK_NAME}』の固定監査ページです。
質問に答える根拠を最大{MAX_RECORDS_PER_PAGE}件だけ抽出してください。

監査質問:
{QUESTIONS[page]}

規則:
- evidenceは下の本文に実在する連続した原文を、一字も直さず20〜360文字でコピーする。
- 改行、句読点、名前、送り仮名を正規化しない。別の箇所を連結しない。
- subject_spanは行為者、発言者、判断者を示す、evidence内に実在する文字列をそのままコピーする。
- 会話だけで主体が特定できないときは、主体を示す前後の地の文までevidenceへ含める。
- claimはevidenceだけから直接言える一つの事実を自然な日本語で書く。
- 関係の向き、命令者と実行者、本人の理由と別人物の考えを入れ替えない。
- 本文にない正規名、人物同定、心理、理由、結果を補わない。
- 質問の各論点を少なくとも1件のrecordで覆う。

[page {page}]
{source_text}
"""


def _post_json(base_url: str, body: dict[str, Any], *, timeout: int) -> dict[str, Any]:
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


def _language_leaks(records: list[dict[str, Any]]) -> list[str]:
    leaks: list[str] = []
    for index, record in enumerate(records, start=1):
        value = f"{record.get('subject_span', '')} {record.get('claim', '')}"
        chars = sorted(set(value) & SIMPLIFIED_ONLY_CHARS)
        if chars:
            leaks.append(f"record {index}: simplified chars={''.join(chars)}")
        for fragment in OBVIOUS_CHINESE_FRAGMENTS:
            if fragment in value:
                leaks.append(f"record {index}: Chinese fragment={fragment}")
    return leaks


def _validate_records(
    parsed: dict[str, Any] | None,
    *,
    page: int,
    source_text: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(parsed, dict) or set(parsed) != {"evidence_records"}:
        return [], ["root is not the required evidence_records-only object"]
    records = parsed.get("evidence_records")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS_PER_PAGE:
        return [], ["evidence_records count is outside 1..4"]

    issues: list[str] = []
    validated: list[dict[str, Any]] = []
    signatures: set[tuple[str, str]] = set()
    required = {"page", "evidence", "subject_span", "claim"}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != required:
            issues.append(f"record {index}: keys mismatch")
            continue
        evidence = record["evidence"]
        subject = record["subject_span"]
        claim = record["claim"]
        if record["page"] != page:
            issues.append(f"record {index}: page mismatch")
        if not isinstance(evidence, str) or not 20 <= len(evidence) <= 360:
            issues.append(f"record {index}: invalid evidence length")
        elif evidence not in source_text:
            issues.append(f"record {index}: evidence is not an exact source span")
        if not isinstance(subject, str) or not 1 <= len(subject) <= 40:
            issues.append(f"record {index}: invalid subject_span")
        elif not isinstance(evidence, str) or subject not in evidence:
            issues.append(f"record {index}: subject_span is not inside evidence")
        if not isinstance(claim, str) or not 1 <= len(claim) <= 160:
            issues.append(f"record {index}: invalid claim")
        if isinstance(evidence, str) and isinstance(claim, str):
            signature = (evidence, claim)
            if signature in signatures:
                issues.append(f"record {index}: duplicate evidence and claim")
            signatures.add(signature)
        validated.append(record)
    issues.extend(_language_leaks(validated))
    return validated, issues


def _record_text(record: dict[str, Any]) -> str:
    return f"{record['subject_span']} {record['claim']}"


def _semantic_checks(records: list[dict[str, Any]]) -> dict[str, bool]:
    def matching(page: int, subject: str, *phrases: str) -> list[dict[str, Any]]:
        return [
            record
            for record in records
            if record["page"] == page
            and subject in str(record["subject_span"])
            and all(phrase in _record_text(record) for phrase in phrases)
        ]

    page_8_matsurika = bool(matching(8, "茉莉花", "戦争"))
    page_8_not_hakuyo = not any(
        record["page"] == 8
        and "珀陽" in str(record["subject_span"])
        and any(phrase in str(record["claim"]) for phrase in ("戦争", "白楼国を平和"))
        for record in records
    )
    page_10_kosei = bool(matching(10, "子星", "唯一で完璧な正答")) and any(
        any(phrase in str(record["claim"]) for phrase in ("ない", "ありません"))
        for record in matching(10, "子星", "唯一で完璧な正答")
    )
    page_10_hakuyo = bool(matching(10, "珀陽", "両方", "好き"))
    page_18_recommender = any(
        record["page"] == 18
        and "子星" in str(record["subject_span"])
        and "茉莉花" in str(record["claim"])
        and "推薦人" in str(record["claim"])
        for record in records
    )
    page_18_not_reversed = not any(
        record["page"] == 18
        and "推薦人" in str(record["claim"])
        and any(
            phrase in str(record["claim"])
            for phrase in ("茉莉花は子星", "茉莉花が子星")
        )
        for record in records
    )
    page_25_collision = any(
        record["page"] == 25
        and "文官" in str(record["subject_span"])
        and "ぶつ" in str(record["claim"])
        for record in records
    )
    page_25_no_foreign_reason = not any(
        record["page"] == 25
        and "文官" in str(record["subject_span"])
        and any(phrase in str(record["claim"]) for phrase in ("四日", "準備"))
        for record in records
    )
    page_26_order = any(
        record["page"] == 26
        and "新人文官" in str(record["subject_span"])
        and "ぶつ" in str(record["claim"])
        and any(phrase in str(record["claim"]) for phrase in ("命じ", "命令"))
        for record in records
    )
    no_shokei_mapping = not any("苑翔景" in _record_text(record) for record in records)
    page_26_identity_doubt = any(
        record["page"] == 26
        and "暗茉莉花" in str(record["claim"])
        and any(
            phrase in str(record["claim"])
            for phrase in ("同一人物", "違う人間", "別人")
        )
        for record in records
    )
    page_27_identity_doubt = any(
        record["page"] == 27
        and "暗茉莉花" in str(record["claim"])
        and any(phrase in str(record["claim"]) for phrase in ("同一人物", "別人"))
        for record in records
    )
    page_27_luggage_permission = any(
        record["page"] == 27
        and "来現" in str(record["subject_span"])
        and "荷物" in str(record["claim"])
        and any(phrase in str(record["claim"]) for phrase in ("許可", "探"))
        for record in records
    )
    return {
        "page_8_matsurika_owns_war_conflict": page_8_matsurika,
        "page_8_hakuyo_does_not_inherit_conflict": page_8_not_hakuyo,
        "page_10_kosei_denies_one_perfect_answer": page_10_kosei,
        "page_10_hakuyo_says_likes_both": page_10_hakuyo,
        "page_18_hakuyo_sends_matsurika_abroad": bool(
            matching(18, "珀陽", "茉莉花", "国外")
        ),
        "page_18_kosei_is_matsurika_recommender": page_18_recommender,
        "page_18_recommender_relation_not_reversed": page_18_not_reversed,
        "page_25_young_clerk_collision_present": page_25_collision,
        "page_25_clerk_does_not_inherit_four_day_reason": page_25_no_foreign_reason,
        "page_26_collision_order_present": page_26_order,
        "no_hua_role_to_shokei_mapping": no_shokei_mapping,
        "page_26_identity_doubt_present": page_26_identity_doubt,
        "page_27_identity_doubt_present": page_27_identity_doubt,
        "page_27_luggage_search_permission_present": page_27_luggage_permission,
    }


def _checks_for_page(checks: dict[str, bool], page: int) -> dict[str, bool]:
    prefix = f"page_{page}_"
    selected = {key: value for key, value in checks.items() if key.startswith(prefix)}
    if page == 26:
        selected["no_hua_role_to_shokei_mapping"] = checks[
            "no_hua_role_to_shokei_mapping"
        ]
    return selected


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _parse_response(raw: dict[str, Any]) -> tuple[str, str, Any]:
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise RuntimeError("server response did not contain exactly one choice")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RuntimeError("server choice is not an object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("server choice message is not an object")
    content = message.get("content") or ""
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    if not isinstance(content, str) or not isinstance(reasoning, str):
        raise RuntimeError("server content or reasoning is not text")
    return content, reasoning, choice.get("finish_reason")


def main() -> int:
    args = _parse_args()
    if not 0 < args.thinking_budget < args.max_tokens:
        raise RuntimeError("thinking budget must be between 1 and max-tokens - 1")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise RuntimeError(f"output directory is not empty: {args.output_dir}")
    if not args.model.is_dir():
        raise RuntimeError(f"model directory does not exist: {args.model}")
    pages = _load_fixture(args.fixture)
    page_map = dict(pages)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    for page in TARGET_PAGES:
        source_text = page_map[page]
        prompt = _build_prompt(page, source_text)
        schema = _build_schema(page)
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
            "thinking_budget": args.thinking_budget,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": f"ornith_evidence_page_{page}",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        print(json.dumps({"event": "start", "page": page}), flush=True)
        started = time.monotonic()
        raw = _post_json(args.base_url, body, timeout=args.timeout)
        elapsed = time.monotonic() - started
        content, reasoning, finish_reason = _parse_response(raw)
        parsed: dict[str, Any] | None = None
        parse_error: str | None = None
        try:
            value = json.loads(content)
            if not isinstance(value, dict):
                raise RuntimeError("structured content was not an object")
            parsed = value
        except (json.JSONDecodeError, RuntimeError) as exc:
            parse_error = str(exc)

        records, validation_issues = _validate_records(
            parsed,
            page=page,
            source_text=source_text,
        )
        all_records.extend(records)
        semantic_checks = _checks_for_page(_semantic_checks(records), page)
        semantic_pass = bool(semantic_checks) and all(semantic_checks.values())
        page_pass = bool(
            finish_reason == "stop"
            and reasoning
            and parse_error is None
            and not validation_issues
            and semantic_pass
        )
        result = {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "page": page,
            "question": QUESTIONS[page],
            "source_sha256": _sha256(source_text),
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
            "record_count": len(records),
            "semantic_checks": semantic_checks,
            "semantic_pass": semantic_pass,
            "page_pass": page_pass,
            "parsed": parsed,
            "raw_response": raw,
        }
        results.append(result)
        _write_json(args.output_dir / f"page-{page}.json", result)
        print(
            json.dumps(
                {
                    "event": "result",
                    "page": page,
                    "page_pass": page_pass,
                    "finish_reason": finish_reason,
                    "record_count": len(records),
                    "validation_issues": validation_issues,
                    "semantic_checks": semantic_checks,
                    "wall_seconds": result["wall_seconds"],
                    "completion_tokens": result["usage"].get("completion_tokens"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    semantic_checks = _semantic_checks(all_records)
    semantic_gate_pass = all(semantic_checks.values())
    gate_pass = all(result["page_pass"] for result in results) and semantic_gate_pass
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runtime": "mlx_vlm",
        "model": str(args.model),
        "book_id": BOOK_ID,
        "book_name": BOOK_NAME,
        "target_pages": list(TARGET_PAGES),
        "source_sha256": SOURCE_SHA256,
        "protocol": {
            "mode": "single-page-targeted-evidence-first",
            "max_records_per_page": MAX_RECORDS_PER_PAGE,
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
            "exact_source_span_required": True,
            "subject_inside_evidence_required": True,
            "canonical_ledger_supplied": False,
            "retry_count": 0,
        },
        "pages": [
            {
                key: result[key]
                for key in (
                    "page",
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
                    "record_count",
                    "semantic_checks",
                    "semantic_pass",
                    "page_pass",
                )
            }
            for result in results
        ],
        "record_count": len(all_records),
        "semantic_checks": semantic_checks,
        "semantic_gate_pass": semantic_gate_pass,
        "gate_pass": gate_pass,
        "manual_review_required": True,
        "production_adoption_unchanged": True,
    }
    _write_json(
        args.output_dir / "fixture.json",
        {
            "book_id": BOOK_ID,
            "book_name": BOOK_NAME,
            "pages": [
                {"page_no": page, "full_text": page_map[page]} for page in TARGET_PAGES
            ],
            "source_sha256": SOURCE_SHA256,
        },
    )
    _write_json(args.output_dir / "evidence-records.json", all_records)
    _write_json(args.output_dir / "summary.json", summary)
    print(
        json.dumps(
            {
                "event": "complete",
                "gate_pass": gate_pass,
                "record_count": len(all_records),
                "semantic_checks": semantic_checks,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
