"""Codex ブラウザで読み取った Kindle 価格を保存する単発 CLI。

この CLI は Amazon へ接続しない。Codex のブラウザが表示内容を読み取り、
JSON を ``ingest`` に渡す前提で、監視対象のエクスポートと結果の取り込みだけを行う。

例::

    cd backend
    uv run python -m tools.kindle_price_monitor export-targets
    printf '[{"watch_id": 1, "current_price": 499, "list_price": 1000}]' | \
        uv run python -m tools.kindle_price_monitor ingest
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# backend/ をパス追加してパッケージ参照を解決
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.kindle_catalog.migrations import upgrade_head
from services.kindle_catalog.price_watch import export_targets, record_observation


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex browser Kindle price monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("export-targets", help="有効な監視対象をJSONで出力")
    ingest = subparsers.add_parser("ingest", help="Codexブラウザの観測JSONを取り込む")
    ingest.add_argument("--file", type=Path, help="観測JSONファイル（省略時は標準入力）")
    return parser


def _read_json(path: Path | None) -> Any:
    raw = path.read_text(encoding="utf-8") if path else sys.stdin.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"観測JSONの解析に失敗しました: {exc}") from exc


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("items", payload.get("observations"))
    if not isinstance(payload, list):
        raise ValueError("観測JSONは配列、または items/observations 配列を持つオブジェクトにしてください")
    if not all(isinstance(item, dict) for item in payload):
        raise ValueError("観測JSONの各要素はオブジェクトにしてください")
    return payload


def _run_ingest(path: Path | None) -> int:
    records = _records(_read_json(path))
    results: list[dict[str, Any]] = []
    failed = False
    for index, record in enumerate(records):
        try:
            watch_id = record.get("watch_id")
            if isinstance(watch_id, bool) or not isinstance(watch_id, int):
                raise ValueError("watch_id は整数で指定してください")
            result = record_observation(
                watch_id=watch_id,
                current_price=record.get("current_price"),
                list_price=record.get("list_price"),
                status=record.get("status"),
                error_message=record.get("error_message"),
                source=record.get("source", "codex_browser"),
                title=record.get("title"),
            )
            results.append({"index": index, "watch_id": watch_id, "result": result})
        except (KeyError, ValueError, TypeError) as exc:
            failed = True
            results.append({"index": index, "watch_id": record.get("watch_id"), "error": str(exc)})
    json.dump({"items": results}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 1 if failed else 0


def _upgrade_quietly() -> None:
    """CLIのJSON出力を壊さないよう、起動時マイグレーションのログだけ抑制する。"""
    previous_disabled = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        upgrade_head()
    finally:
        logging.disable(previous_disabled)


def main() -> int:
    args = _parser().parse_args()
    try:
        _upgrade_quietly()
        if args.command == "export-targets":
            json.dump({"items": export_targets()}, sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
            return 0
        return _run_ingest(args.file)
    except (OSError, ValueError) as exc:
        print(f"[kindle_price_monitor] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
