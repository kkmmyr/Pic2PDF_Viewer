"""ハイブリッド検索オーケストレーター（後方互換再エクスポート）。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §6。

内部実装は 3 サブモジュールに分離:
  - fts5_search   — FTS5 BM25 全文検索
  - vector_search — LanceDB KNN ベクトル検索
  - rrf_ranker    — Reciprocal Rank Fusion 統合
"""
from __future__ import annotations

# 共有データクラス・ユーティリティ（後方互換エクスポート）
from ._search_types import (
    Scope,
    ScopeType,
    SearchHit,
    _fetch_main_characters,
    _image_url,
    _resolve_book_names,
)

# FTS5 検索（後方互換エクスポート）
from .fts5_search import (
    build_fts5_or_query,
    fts_search,
    sanitize_snippet,
)

# ベクトル検索（後方互換エクスポート）
from .vector_search import (
    search_book_summaries,
    vec_search,
)

# RRF ランキング（後方互換エクスポート）
from .rrf_ranker import (
    hybrid_search,
    load_all_pages_of_book,
)

__all__ = [
    "Scope",
    "ScopeType",
    "SearchHit",
    "build_fts5_or_query",
    "fts_search",
    "hybrid_search",
    "load_all_pages_of_book",
    "sanitize_snippet",
    "search_book_summaries",
    "vec_search",
]
