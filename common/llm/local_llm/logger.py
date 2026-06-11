"""mcp_server.py / ask.py 共通ロガー。

ログ出力先: `D:\\61.tool\\common\\llm\\logs\\YYYY-MM-DD.log`
ログ形式:
  2026-05-10 14:30:00 | mcp:ask_qwen     | 121345ms | [prompt 100文字...] -> [response 200文字...]
  2026-05-10 14:31:05 | mcp:analyze_code |  98230ms | [prompt 100文字...] -> [response 200文字...]
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

# 共通モジュールルート（local_llm/ の親）配下に logs/ を作る
_BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = _BASE_DIR / "logs"

PROMPT_PREVIEW = 100
RESPONSE_PREVIEW = 200


def _get_logger() -> logging.Logger:
    logger = logging.getLogger("local_llm")
    if logger.handlers:
        return logger

    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def log_interaction(
    source: str,
    prompt: str,
    response: str,
    elapsed_ms: int,
) -> None:
    """1 回の LLM とのやり取りをログに記録する。"""
    prompt_preview = prompt.replace("\n", " ")[:PROMPT_PREVIEW]
    if len(prompt) > PROMPT_PREVIEW:
        prompt_preview += "..."

    response_preview = response.replace("\n", " ")[:RESPONSE_PREVIEW]
    if len(response) > RESPONSE_PREVIEW:
        response_preview += "..."

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"{ts} | {source:<20} | {elapsed_ms:>6}ms | "
        f"[{prompt_preview}] -> [{response_preview}]"
    )
    _get_logger().info(line)
