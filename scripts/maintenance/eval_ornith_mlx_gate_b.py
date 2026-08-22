"""Ornith 1.5 MLXの固定第1ブロックを現行事実抽出契約で評価する。

Linux本番DBはSSH越しにread-onlyで参照し、固定source / prompt / 人物台帳の
hashが一致した場合だけ、8〜27ページの書籍事実と人物別事実を順番に生成する。
公開DB、索引、checkpoint、環境変数は変更しない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from local_llm import BackendConfig, MlxBackend
from services.novel_db._prompts import (
    CHARACTER_FACT_EXTRACTION_PROMPT,
    FACT_EXTRACTION_OPTIONS,
    FACT_EXTRACTION_PROMPT,
)
from services.novel_db.fact_checkpoints import validate_and_structure_fact_sheet
from services.novel_db.generation_quality import (
    BookFactSheet,
    format_page_blocks,
    parse_fact_sheet,
)

BOOK_ID = 46
BOOK_NAME = "茉莉花官吏伝 十　中原の鹿を逐わず (ビーズログ文庫)"
SOURCE_PAGES = tuple(range(8, 28))
SOURCE_SHA256 = "47f62bc67042c39dbf09d0b9213041d8a6a048c98a41a5d0e3341292f6c15007"
LEDGER_SHA256 = "3c93cdb7f234e530f320ef00724136115785b4757000c58461eff1704576d86c"
BOOK_PROMPT_SHA256 = "d38f4a04f5b8dcfb38069a42debe166bffd6a4c4860c824ff6042365deb23664"
DEFAULT_MODEL = Path(
    "/Users/medaro/.local/share/pic2pdf-mlx/models/ornith-1.5-35b-a3b-4bit",
)
DEFAULT_SEED = 20260813

# 公開人物名台帳に対応する短縮名・役職名を別見出しにしてはならない。
FORBIDDEN_ALIAS_HEADINGS = {
    "茉莉花",
    "子星",
    "天河",
    "翔景",
    "大虎",
    "冬虎",
    "春雪",
    "来現",
    "望礼部尚書",
    "礼部尚書",
}


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
) -> tuple[list[tuple[int, str]], list[str], str, str]:
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
    source = format_page_blocks(pages)
    source_hash = _sha256(source)
    if source_hash != SOURCE_SHA256:
        raise RuntimeError(f"source SHA-256 mismatch: {source_hash}")

    ledger_rows = _read_remote_json(
        args,
        "SELECT name FROM book_characters "
        f"WHERE book_id={BOOK_ID} ORDER BY first_page,name;",
    )
    names = [str(row["name"]) for row in ledger_rows]
    ledger = "\n".join(f"- {name}" for name in names)
    ledger_hash = _sha256(ledger)
    if ledger_hash != LEDGER_SHA256:
        raise RuntimeError(f"character ledger SHA-256 mismatch: {ledger_hash}")
    return pages, names, source, ledger


def _run_generation(
    backend: MlxBackend,
    prompt: str,
    *,
    options: dict[str, Any],
    timeout: int,
    stage: str,
) -> dict[str, Any]:
    print(
        json.dumps({"event": "start", "stage": stage}, ensure_ascii=False), flush=True
    )
    started = time.monotonic()
    response_parts: list[str] = []
    done_events: list[dict[str, Any]] = []
    event_count = 0
    for event in backend.stream_ask(
        prompt,
        options=options,
        think=False,
        timeout=timeout,
    ):
        event_count += 1
        response = event.get("response")
        if isinstance(response, str) and response:
            response_parts.append(response)
        if event.get("done"):
            done_events.append(event)
    elapsed = time.monotonic() - started
    content = "".join(response_parts).strip()
    done = done_events[-1] if done_events else {}
    result = {
        "stage": stage,
        "wall_seconds": round(elapsed, 3),
        "event_count": event_count,
        "done_count": len(done_events),
        "finish_reason": done.get("done_reason"),
        "prompt_tokens": done.get("prompt_eval_count"),
        "completion_tokens": done.get("eval_count"),
        "content_chars": len(content),
        "content": content,
    }
    print(
        json.dumps(
            {
                "event": "result",
                "stage": stage,
                "wall_seconds": result["wall_seconds"],
                "finish_reason": result["finish_reason"],
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "content_chars": result["content_chars"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return result


def _known_regression_hits(book_facts: str, character_response: str) -> list[str]:
    combined = f"{book_facts}\n{character_response}"
    hits: list[str] = []
    for raw_line in combined.splitlines():
        line = raw_line.strip()
        if "[page 10]" in line and "茉莉花" in line and "唯一で完璧な正答" in line:
            hits.append(
                "page 10 dialogue was attributed to 皓茉莉花 instead of 芳子星 / 珀陽"
            )
        if ("[page 18]" in line or "[page 19]" in line) and any(
            phrase in line for phrase in ("歓迎の宴", "歓迎宴", "黒曜城で過ご")
        ):
            hits.append("a later 黒曜城 scene was placed on page 18 or 19")
        if (
            "[page 27]" in line
            and "新人文官" in line
            and "ぶつか" in line
            and "命じ" in line
        ):
            hits.append("the page 26 collision order was moved to page 27")
    return sorted(set(hits))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    args = _parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise RuntimeError(f"output directory is not empty: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.model.is_dir():
        raise RuntimeError(f"model directory does not exist: {args.model}")

    pages, canonical_names, source, ledger = _load_fixture(args)
    book_prompt = FACT_EXTRACTION_PROMPT.format(
        book_name=BOOK_NAME,
        part_index=1,
        part_count=4,
        character_ledger=ledger,
        text=source,
    )
    book_prompt_hash = _sha256(book_prompt)
    if book_prompt_hash != BOOK_PROMPT_SHA256:
        raise RuntimeError(f"book prompt SHA-256 mismatch: {book_prompt_hash}")

    options = {**FACT_EXTRACTION_OPTIONS, "seed": args.seed}
    backend = MlxBackend(
        BackendConfig(
            base_url=args.base_url,
            model=str(args.model),
            timeout=args.timeout,
            default_options={},
        ),
    )
    book_result = _run_generation(
        backend,
        book_prompt,
        options=options,
        timeout=args.timeout,
        stage="book_fact_extraction",
    )
    book_response = str(book_result["content"])
    book_sheet = parse_fact_sheet(book_response)
    book_stop_pass = bool(
        book_result["done_count"] == 1 and book_result["finish_reason"] == "stop"
    )

    character_result: dict[str, Any] | None = None
    character_sheet = BookFactSheet(book_facts="", character_facts={})
    if book_sheet.book_facts and book_stop_pass:
        character_prompt = CHARACTER_FACT_EXTRACTION_PROMPT.format(
            book_name=BOOK_NAME,
            character_ledger=ledger,
            book_facts=book_sheet.book_facts,
        )
        character_result = _run_generation(
            backend,
            character_prompt,
            options=options,
            timeout=args.timeout,
            stage="character_fact_extraction",
        )
        character_sheet = parse_fact_sheet(str(character_result["content"]))

    sheet = BookFactSheet(
        book_facts=book_sheet.book_facts,
        character_facts=character_sheet.character_facts,
    )
    validation_error: str | None = None
    records = []
    try:
        records = validate_and_structure_fact_sheet(
            sheet,
            allowed_pages=set(SOURCE_PAGES),
        )
    except ValueError as exc:
        validation_error = str(exc)

    character_response = str(character_result["content"]) if character_result else ""
    character_headings = sorted(sheet.character_facts)
    forbidden_aliases = sorted(set(character_headings) & FORBIDDEN_ALIAS_HEADINGS)
    nonledger_headings = sorted(set(character_headings) - set(canonical_names))
    regression_hits = _known_regression_hits(sheet.book_facts, character_response)
    marker_pass = bool(
        book_response.startswith("[BOOK_FACTS]")
        and character_response.startswith("[CHARACTER_FACT:")
        and "```" not in book_response
        and "```" not in character_response
    )
    stop_pass = bool(
        book_result["done_count"] == 1
        and book_result["finish_reason"] == "stop"
        and character_result is not None
        and character_result["done_count"] == 1
        and character_result["finish_reason"] == "stop"
    )
    mechanical_gate_pass = bool(
        marker_pass
        and stop_pass
        and sheet.book_facts
        and sheet.character_facts
        and validation_error is None
        and not forbidden_aliases
        and not regression_hits
    )

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    summary = {
        "generated_at": generated_at,
        "runtime": "mlx_vlm",
        "model": str(args.model),
        "book_id": BOOK_ID,
        "book_name": BOOK_NAME,
        "source_pages": [SOURCE_PAGES[0], SOURCE_PAGES[-1]],
        "source_sha256": SOURCE_SHA256,
        "ledger_sha256": LEDGER_SHA256,
        "book_prompt_sha256": BOOK_PROMPT_SHA256,
        "options": options,
        "request_contract": {
            "enable_thinking": False,
            "stream": True,
            "max_num_seqs": 1,
            "native_structured_output": False,
        },
        "book_generation": {
            key: value for key, value in book_result.items() if key != "content"
        },
        "character_generation": (
            {key: value for key, value in character_result.items() if key != "content"}
            if character_result
            else None
        ),
        "marker_pass": marker_pass,
        "stop_pass": stop_pass,
        "validation_error": validation_error,
        "book_fact_chars": len(sheet.book_facts),
        "character_count": len(sheet.character_facts),
        "record_count": len(records),
        "referenced_pages": sorted(
            {page for record in records for page in record.pages}
        ),
        "character_headings": character_headings,
        "forbidden_alias_headings": forbidden_aliases,
        "nonledger_headings": nonledger_headings,
        "known_regression_hits": regression_hits,
        "mechanical_gate_pass": mechanical_gate_pass,
        "manual_review_required": True,
    }

    _write_json(
        args.output_dir / "fixture.json",
        {
            "book_id": BOOK_ID,
            "book_name": BOOK_NAME,
            "pages": [
                {"page_no": page_no, "full_text": text} for page_no, text in pages
            ],
            "canonical_character_names": canonical_names,
            "source_sha256": SOURCE_SHA256,
            "ledger_sha256": LEDGER_SHA256,
            "book_prompt_sha256": BOOK_PROMPT_SHA256,
        },
    )
    (args.output_dir / "book-response.txt").write_text(
        book_response + "\n", encoding="utf-8"
    )
    (args.output_dir / "character-response.txt").write_text(
        character_response + "\n",
        encoding="utf-8",
    )
    _write_json(
        args.output_dir / "fact-records.json",
        [asdict(record) for record in records],
    )
    _write_json(args.output_dir / "summary.json", summary)
    print(
        json.dumps(
            {
                "event": "complete",
                "mechanical_gate_pass": mechanical_gate_pass,
                "record_count": len(records),
                "character_count": len(sheet.character_facts),
                "known_regression_hits": regression_hits,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if mechanical_gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
