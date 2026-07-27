"""小説テキスト検索・RAG 機能のサービス層。

DB スキーマ定義・接続・PDF テキスト抽出・チャンク分割・embedding 計算・
DB 構築フローを提供する。詳細は
docs/design/詳細設計/機能別/小説RAG_データ.md を参照。
"""

from .builder import ocr_book, rebuild_book, rebuild_from_pages
from .chunker import chunk_page
from .connection import open_db, with_db
from .embedder import embed_batch
from .extractor import extract_pages, run_ocr_subprocess
from .page_index_builder import rebuild_page_from_pages
from .search import Scope, SearchHit, hybrid_search

__all__ = [
    "Scope",
    "SearchHit",
    "chunk_page",
    "embed_batch",
    "extract_pages",
    "hybrid_search",
    "ocr_book",
    "open_db",
    "rebuild_book",
    "rebuild_from_pages",
    "rebuild_page_from_pages",
    "run_ocr_subprocess",
    "with_db",
]
