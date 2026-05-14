"""
Novel DB（小説 RAG 機能）の設定値。

`config/__init__.py` から `from .novel_db import *` でインポートされる。
直接インポートも可能: `from config.novel_db import NOVEL_DB_LLM_MODEL`
"""
import os

# ---------------------------------------------------------------------------
# Novel DB の埋め込みモデル / LLM
# 埋め込み (bge-m3) と軽量 LLM (Gemma 4) は Ollama 経由。
# 重量 LLM (Qwen) は B-14 / ADR-0009 で llama-server に切り替え済み。
# Phase C（2026-05-11）で Ollama 上の qwen3.6-iq4xs は撤去（23GB 解放）、
# `NOVEL_DB_LLM_BACKEND` env は将来の新バックエンド（vLLM 等）追加時の拡張点
# として残存（現状は `llama_server` 1 択）。
# ---------------------------------------------------------------------------
NOVEL_DB_OLLAMA_BASE_URL  = os.environ.get("NOVEL_DB_OLLAMA_BASE_URL", "http://localhost:11434")
NOVEL_DB_EMBED_MODEL      = os.environ.get("NOVEL_DB_EMBED_MODEL", "bge-m3")
NOVEL_DB_EMBED_DIM        = 1024  # bge-m3 の出力次元
# 既定 0 = CPU 推論。llama-server（Qwen 35B）に VRAM を譲るため。
# GPU に戻すなら NOVEL_DB_EMBED_NUM_GPU=99 を設定して uvicorn を再起動。
NOVEL_DB_EMBED_NUM_GPU    = int(os.environ.get("NOVEL_DB_EMBED_NUM_GPU", "0"))
NOVEL_DB_LLM_MODEL       = os.environ.get("NOVEL_DB_LLM_MODEL", "qwen3.6-iq4xs")
# 既定 `llama_server`（実機ベンチで tg 5× 高速化、scope=all 応答 24s→14s）。
# Phase C で `ollama` 分岐撤去。未知の値は LLMError。
NOVEL_DB_LLM_BACKEND      = os.environ.get("NOVEL_DB_LLM_BACKEND", "llama_server")
NOVEL_DB_LLAMA_SERVER_URL = os.environ.get("NOVEL_DB_LLAMA_SERVER_URL", "http://127.0.0.1:11435")
# 主要登場人物抽出用の軽量モデル（短答型タスク。thinking で num_predict を
# 消費する 26b と異なり、e4b は応答が速く character 抽出に向く）
NOVEL_DB_CHAR_EXTRACT_MODEL = os.environ.get("NOVEL_DB_CHAR_EXTRACT_MODEL", "gemma4:e4b")

# B-9 Contextual Retrieval のチャンクコンテキスト生成モデル。
# Anthropic の Contextual Retrieval blog では「位置説明は単純なタスクなので
# 軽量モデルで十分」と推奨されており、gemma4:e4b で代用する。
# 品質不足が確認されたら NOVEL_DB_LLM_MODEL（qwen3.6:35b-a3b）にフォールバック。
#
# TODO(Step5高速化): Gemma4 MTP (Multi-Token Prediction) — llama.cpp 公式対応待ち
#   MTP は投機デコード（4 層の軽量ドラフターが先回り予測）。E4B 長文(256 tok)で 2.10× 実測。
#   現状: ~31 t/s × ~70 tok/chunk → MTP 適用後: ~65 t/s 期待（実測は 1.7×〜2.2×、3× はベスト値）。
#
#   【対応方針】llama.cpp の Gemma4 アシスタント GGUF 変換対応を待つ（緊急性なし）。
#   対応後は既存の llama-server をそのまま流用できるため移行コストが最小。
#   進捗: llama.cpp PR#22673 (MTP ベータ) + issue#22747 (Gemma4 GGUF 変換) — 2026-05-13 時点で進行中。
#
#   【各ランタイムの状況】（2026-05-13 技術検証済）
#   - llama.cpp: PR#22673 で MTP ベータ実装済みだが Gemma4 アシスタントの GGUF 変換が公式未対応 ← 待機中
#   - vLLM: Day-0 サポート済み（唯一の即時実用パス）。WSL2 + Linux 環境が必要で当環境では未セットアップ。
#           起動例: vllm serve google/gemma-4-E4B-it --tensor-parallel-size 1 --max-model-len 8192 \
#                     --speculative-config '{"method":"mtp","model":"google/gemma-4-E4B-it-assistant","num_speculative_tokens":1}'
#           ※ num_speculative_tokens=1 が推奨デフォルト（4 にすると最大速だが品質トレードオフあり）
#   - Ollama: PR#15980 (2026-05-05 マージ) は MLX (Apple Silicon) 専用。Windows/CUDA 非対応。
#   - `bjoernb/gemma4-e4b-fast` は同一 GGUF の別ラッパーで速度差なし（実機検証済み）。
#
#   参考: https://ai.google.dev/gemma/docs/mtp/overview?hl=ja
#         https://dev.classmethod.jp/articles/dgx-spark-gemma4-mtp-multi-token-prediction-bench/
NOVEL_DB_CONTEXT_MODEL = os.environ.get("NOVEL_DB_CONTEXT_MODEL", "gemma4:e4b")

# §4.5 本構築統合: キャラ抽出 / チャンク文脈生成のバックエンド切替
# "ollama" (既定): Ollama 経由で gemma4:e4b を使用
# "qwen"         : llama-server の Qwen に統一（thinking は _DEFAULT_THINK=False で自動抑制）
NOVEL_DB_GEMMA_BACKEND = os.environ.get("NOVEL_DB_GEMMA_BACKEND", "ollama")

# ---------------------------------------------------------------------------
# Novel DB 検索パラメータ
# - MIN_BODY_CHARS: 章扉・目次・人物紹介・あとがき等の薄いページを検索対象から除外する閾値
# - QA_TOP_K: RAG 質問応答で Gemma に渡すページ数（多いほど深い回答だが応答時間も伸びる）
# - QA_MAX_PER_BOOK: scope=all / series での書籍ごと取得上限（ざっくり質問が特定冊に偏らないよう均等化）
# - BODY_PAGE_MARGIN: 各書籍の先頭 / 末尾の除外ページ数（表紙・目次・あとがき・解説・奥付）
# ---------------------------------------------------------------------------
NOVEL_DB_MIN_BODY_CHARS    = 300
# B-13 段階 A→B（2026-05-11 採用）: top_k を 16 → 32 (A) → 64 (B) に段階拡大。
# B-14 で llama-server 切替により応答が 5× 高速化したため、context 拡大の余地が生まれた。
# 環境変数 NOVEL_DB_QA_TOP_K で上書き可（A=32 / B=64 / C=未定 の切替やベンチ用途）
NOVEL_DB_QA_TOP_K          = int(os.environ.get("NOVEL_DB_QA_TOP_K", "64"))
# B-13 段階 B（2026-05-11 採用）: max_per_book を 2 → 5 に拡大。
# scope=all/series でも同一書籍内のページを最大 5 件まで集め、同書籍に集中する
# 質問（「この書籍の主人公の心情変化」等）に深く答えられるようにする。
# 11 冊 × 5 件 = 最大 55 件取得可能（top_k=64 にバランスする値）
NOVEL_DB_QA_MAX_PER_BOOK   = 5
NOVEL_DB_BODY_PAGE_MARGIN  = 5
# B-8: scope=all / scope=series で QA プロンプトに含める書籍サマリの上限件数。
# 現状 11 冊なので 11 でほぼ全冊カバー。書籍数が増えたら適宜下げる
NOVEL_DB_QA_TOP_SUMMARIES  = 11
# B-13 段階 A→B: QA 時の num_ctx。8192 (PoC) → 16384 (A) → 32768 (B) と段階拡大。
# 段階 B では top_k=64 × 平均 600 字 = ~24k 字 + 全 11 冊サマリ ~11k 字 + テンプレ
# = 約 40k 字 ≒ ~25k tokens となり 16384 を超えるため、32768 に拡大。
# llama-server 側は -c 36864（32768 + 余裕）で起動する必要あり（start-qwen-server.bat）。
# 環境変数 NOVEL_DB_QA_NUM_CTX で上書き可（A=16384 へのロールバックや C=131072 への切替に使う）
NOVEL_DB_QA_NUM_CTX        = int(os.environ.get("NOVEL_DB_QA_NUM_CTX", "32768"))

# B-11 Query Expansion（2026-05-11 採用）: ユーザーの質問を gemma4:e4b で複数の検索
# クエリに展開して hybrid_search を多角的に実行する。抽象質問の recall 改善が狙い。
# 応答時間は +3〜5 秒（gemma4:e4b の短答呼び出し）。
NOVEL_DB_QA_EXPAND_ENABLED = os.environ.get("NOVEL_DB_QA_EXPAND_ENABLED", "true").lower() in ("1", "true", "yes")
NOVEL_DB_QA_EXPAND_N       = int(os.environ.get("NOVEL_DB_QA_EXPAND_N", "3"))
NOVEL_DB_QA_EXPAND_MODEL   = os.environ.get("NOVEL_DB_QA_EXPAND_MODEL", "gemma4:e4b")

# B-13 段階 C（2026-05-11 本採用）: scope=book で本文を丸ごと読み込むモード。
# hybrid_search を bypass し、指定書籍の全 page を page_no 順で LLM に投げる。
# 実機測定で 78k tokens 入力 / 170 秒 / 9.8 t/s、本文 9 箇所以上から具体的セリフ
# 引用付きの深い分析が得られたため、品質優先で既定有効化。
# llama-server は start-qwen-server.bat で -c 131072 / -ncmoe 28 起動済み前提。
# ロールバック: NOVEL_DB_QA_FULL_BOOK_MODE=false で段階 B 相当（hybrid_search）に戻る。
NOVEL_DB_QA_FULL_BOOK_MODE    = os.environ.get("NOVEL_DB_QA_FULL_BOOK_MODE", "true").lower() in ("1", "true", "yes")
NOVEL_DB_QA_FULL_BOOK_NUM_CTX = int(os.environ.get("NOVEL_DB_QA_FULL_BOOK_NUM_CTX", "131072"))
