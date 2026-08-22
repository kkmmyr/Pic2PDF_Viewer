"""SQLite pagesから世代別LanceDB ICU BM25 indexを完全再構築する。

使用例:
    cd backend
    uv run python scripts/build_page_fts_index.py

成功時は本文を含まないbuild manifestをJSONでstdoutへ出力する。既存chunks / summaries、
旧active page tableは変更しない。
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.novel_db.connection import with_db
from services.novel_db.migrations import upgrade_head
from services.novel_db.page_fts import build_page_fts_index
from services.novel_db.page_fts import logger as page_fts_logger


def _route_build_logs_to_stderr() -> None:
    """stdoutを単一JSON manifestに保つため、serviceのconsole logだけstderrへ移す。"""
    for handler in page_fts_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            handler.setStream(sys.stderr)


def main() -> int:
    _route_build_logs_to_stderr()
    upgrade_head()
    try:
        with with_db() as conn:
            result = build_page_fts_index(conn)
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error_type": type(exc).__name__},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {"ok": True, **result.to_dict()},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
