"""小説テキスト検索・RAG 機能のサービス層。

DB スキーマ定義・接続・PDF テキスト抽出・チャンク分割・embedding 計算・
DB 構築フローを提供する。詳細は
docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md を参照。
"""

from .builder import rebuild_book
from .chunker import chunk_page
from .connection import open_db, with_db
from .embedder import embed_batch
from .extractor import extract_pages
from .schema import init_schema
from .search import Scope, SearchHit, hybrid_search

__all__ = [
    "Scope",
    "SearchHit",
    "chunk_page",
    "embed_batch",
    "extract_pages",
    "hybrid_search",
    "init_schema",
    "open_db",
    "rebuild_book",
    "with_db",
]
