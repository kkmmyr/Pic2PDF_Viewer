"""Gemma 4 ツール群（`D:\\61.tool\\Gemma 4`）のインポートヘルパー。

backend の `config` モジュールが `sys.modules['config']` にキャッシュされていると、
Gemma 側の `config.py` が読めず ImportError になる。インポート時だけ backend
config を退避し、完了後に復元する処理を `_gemma_import_context()` に共通化。

`author_resolver` / `series_resolver` から使う。
"""
import os
import sys
from contextlib import contextmanager
from typing import Any, Callable, Optional

from config import GEMMA_TOOL_DIR


@contextmanager
def _gemma_import_context():
    """Gemma ツールのインポートに必要な sys.path と sys.modules を整える。

    - `GEMMA_TOOL_DIR` と `GEMMA_TOOL_DIR/lib` を `sys.path` 先頭に追加（重複追加なし）
    - backend の `config` モジュールを退避し、yield 後に復元する
    """
    lib_dir = os.path.join(GEMMA_TOOL_DIR, "lib")
    for p in (GEMMA_TOOL_DIR, lib_dir):
        if p not in sys.path:
            sys.path.insert(0, p)

    saved_config = sys.modules.pop("config", None)
    try:
        yield
    finally:
        if saved_config is not None:
            sys.modules["config"] = saved_config


def import_ollama_client() -> Optional[Callable[..., Any]]:
    """`ollama_client.call_ollama` をインポートして返す。失敗時は None。"""
    with _gemma_import_context():
        try:
            from ollama_client import call_ollama  # type: ignore[import]
            return call_ollama
        except ImportError:
            return None


def import_web_extract_tools() -> tuple[
    Optional[Callable[..., Any]],
    Optional[Callable[..., Any]],
    Optional[Callable[..., Any]],
    Optional[Callable[..., Any]],
]:
    """web_extract / searxng_search / fetch_url_content / call_ollama を一括インポート。

    Returns:
        4 関数のタプル `(web_extract, searxng_search, fetch_url_content, call_ollama)`。
        Gemma ツールが利用不可の場合はすべて `None`。
    """
    with _gemma_import_context():
        try:
            from web_extract import web_extract, searxng_search, fetch_url_content  # type: ignore[import]
            from ollama_client import call_ollama  # type: ignore[import]
            return web_extract, searxng_search, fetch_url_content, call_ollama
        except ImportError:
            return None, None, None, None
