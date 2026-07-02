# 小説テキスト検索・RAG 機能 バックエンド設計書

> status: absorption-pending | last-verified: 2026-05-11
<!-- 吸収予定（設計書ガバナンス再編 G4）。それまで本書が当該機能の正本。 -->

novel タブの OCR テキストを SQLite + FTS5 + ベクトルで検索し、ローカル LLM（Qwen3.6:35b-a3b）で質問応答する機能の **バックエンド側** 設計書。本ファイルに集約し、要件は 要件定義: 小説テキスト検索・RAG機能.md を参照。

---

## 1. 概要

### 1.1. 目的

- 既存 Searchable PDF（`backend/data/kindle_novel/pdfs/*.pdf`）から OCR テキストを抽出して SQLite に取り込む
- ハイブリッド検索（FTS5 OR + ベクトル `bge-m3`）+ ローカル LLM `qwen3.6-iq4xs`（Qwen3.6:35b-a3b の IQ4_XS 量子化、2026-05-11 切替）でページ番号付き引用回答を返す
- 主要登場人物のページ単位抽出（`gemma4:e4b`）でキャラ帰属の誤りを抑制したプロンプトを構築
- ライブラリ表示・DB 再構築・履歴保存・画像配信を提供する

### 1.2. 設計原則

- **疎結合**: 既存 backend にミニマル追加。`routers/novel_db.py` と `services/novel_db/` 配下に閉じる
- **既存パターン踏襲**: routers / services 分離・`_deps.py` の validated_source・`utils/path_utils.py` の validate_safe_path を流用（[CLAUDE.md backend conventions](../../../../.claude/CLAUDE.md)）
- **SQLite 単一ファイル**: 書籍データ・チャンク・ベクトル・履歴・ジョブをすべて 1 ファイルにまとめ、DB 配置・バックアップを単純化
- **既存 series / meta は流用**: 書籍 ↔ シリーズの紐付けは既存 `series.router` / `services/meta_store.py` 経由で `data/meta.db` を参照（Phase 64 で JSON → SQLite 移行済み）
- **LLM クライアントは共通モジュール**: thinking モデルの呼び出しロジックは `D:\61.tool\common\llm`（A-0 リネーム前は `Qwen/`）に切り出し、他プロジェクトと共有（詳細は [ADR-0007](../../基本設計/ADR/0007_llm-extraction-qwen-adoption.md)）
- **リアルタイム配信は SSE**: Qwen3.6 の応答（80〜130 秒）を Server-Sent Events で逐次配信

### 1.3. 関連ドキュメント

- 要件: docs/01_要件定義/小説テキスト検索・RAG機能.md
- 既存 OCR: [docs/03_詳細設計/OCR設計書.md](OCR設計書.md)（yomitoku ベース）
- 既存 backend 全体: [詳細設計書_バックエンド編.md](../詳細設計書_バックエンド編.md)
- フロントエンド設計: 別途 [小説テキスト検索・RAG機能_フロントエンド設計.md](小説テキスト検索・RAG機能_フロントエンド設計.md)（後続作成）
- API 仕様: [API仕様書.md](../API.md) §X（後続追加）
- 運用知見（実機ベンチマーク・モデル選定・トラブルシューティング）: [docs/05_記録/小説RAG_技術知見.md](../../../log/技術知見/小説RAG_技術知見.md)

---

## 2. アーキテクチャ

### 2.1. 全体構成

```
[Frontend novel タブ]
    ├─ 検索  ──┐
    ├─ 質問  ──┤  HTTP / SSE
    └─ 再構築─┘
              │
              ▼
[FastAPI] routers/novel_db.py
              │
              ├─→ services/novel_db/retrieval.py (検索・コンテキスト構築統合: hybrid_search デデュープ + full_book_mode + 書籍サマリ付与, Phase 55-3)
              ├─→ services/novel_db/search.py    (検索: FTS5 + ベクトル + RRF + 主要キャラ JOIN)
              ├─→ services/novel_db/llm.py       (Qwen SSE 呼び出し: 共通モジュール経由)
              ├─→ services/novel_db/library.py   (書籍一覧 + DB 状態)
              └─→ services/novel_db/job_queue.py (再構築ジョブの全体ロック + キュー)
                          │
                          └─→ services/novel_db/builder.py
                                  ├─ extractor.py            (PyMuPDF blocks 抽出)
                                  ├─ chunker.py              (句点境界チャンク)
                                  ├─ embedder.py             (Ollama bge-m3)
                                  └─ character_extractor.py  (Ollama gemma4:e4b: 主要登場人物)

                          [別 CLI 経由で後追い実行する補助処理]
                          ├─→ services/novel_db/summarizer.py     (Qwen 1-shot: 書籍俯瞰サマリ B-5)
                          └─→ services/novel_db/contextualizer.py (gemma4:e4b: チャンク位置説明 B-9)
                                          │
                                          ▼
                            [SQLite] backend/data/novel_db/novel.db
                            (FTS5 + メタデータ) + [LanceDB] novel.lancedb（ベクトル）
                                          │
                                          ▼
                            [Ollama localhost:11434]
                            ├─ bge-m3              (embedding)
                            └─ gemma4:e4b          (主要登場人物 + チャンク位置説明: 短答型)
                            (※ Phase C / 2026-05-11 で rollback 用 qwen3.6-iq4xs を撤去)

                            [llama-server 127.0.0.1:11435]   ← B-14 / ADR-0009 で採用
                            └─ qwen3.6-iq4xs       (RAG 質問応答 + 書籍俯瞰サマリ: thinking モデル, IQ4_XS GGUF)
                                  ▲
                                  │ 共通モジュール経由（QWEN_BACKEND で 2 系統切替）
                              [D:\61.tool\common\llm\local_llm]

[StaticFiles] /kindle_novel/images/{書籍名}/{連番}.png  (既存マウント流用)
```

### 2.2. 設計判断（Why）

- **既存 FastAPI に組み込む理由**: hitomi 監視は単発タスクなので別プロセスにしたが、本機能は対話型 API（検索・質問）が主であり、リクエスト都度の応答が必須。組み込み方が自然
- **SQLite + FTS5 + LanceDB を選んだ理由**:
    - PoC で SQLite + FTS5 + sqlite-vec を検証済み、十分な性能（11 冊で約 10MB、検索 < 1 秒）
    - Phase 62（2026-05-14）でベクトル部分を sqlite-vec → LanceDB に移行。FTS5・メタデータは SQLite に残し、ベクトル（chunks/summaries）を LanceDB へ分離
    - LanceDB 移行理由: sqlite-vec の vec0 は線形スキャン O(n) で ANN インデックス追加不可。LanceDB は 50,000 チャンク超で IVF_PQ 自動ビルドにより ANN 検索が有効化される
- **bge-m3 を採用した理由**: PoC で `nomic-embed-text` と比較し、日本語意味検索精度が明確に高い（OCR ミスを意味距離で吸収可能）
- **質問応答 LLM に Qwen3.6:35b-a3b を採用した理由**: 当初 PoC で gemma4:26b を採用したが、シリーズ全体の概括的な質問（「テーマ」「主人公の成長」など）に対する回答が浅く、踏み込みが足りなかった。Qwen3.6:35b-a3b（35B 総 / 活性 3B MoE）に切り替えたところ、同条件の質問で `done_reason='stop'` で完走し、章ごとの対比や具体例の引用を含む構造的回答が得られた。応答時間は 30〜100 秒 → 80〜130 秒に伸びたが、品質向上の方が大きい（詳細・経緯は [ADR-0007](../../基本設計/ADR/0007_llm-extraction-qwen-adoption.md)）
- **主要登場人物抽出に gemma4:e4b を採用した理由**: 短答型タスク（人物名のリスト出力）であり、Qwen のような重量モデルは過剰。1300 ページの一括抽出を現実的な時間で回すために軽量モデルが必須。`stream=True` / `think=False` / `num_predict=4096` で安定動作する
- **LLM クライアントを共通モジュールに切り出した理由**: Qwen3.x は thinking モデルで `stream=True` / `think=False` の併用が必須。`num_predict` を thinking ブロックに食い潰される事故が起きやすく、地雷を踏み抜く呼び出しを各プロジェクトで再実装したくない（詳細は [ADR-0007](../../基本設計/ADR/0007_llm-extraction-qwen-adoption.md)）
- **全体ロック + ジョブキュー方式を選んだ理由**:
    - SQLite WAL モードでも、ベクトル更新時の書き込みは GPU/CPU を高負荷で消費するため、並列実行は逆効果
    - ロック粒度を「書籍単位」にする実装複雑化の利得が薄い
    - クライアント側で「再構築中」を示せばユーザー体験は十分

---

## 3. ディレクトリ構成

```
backend/
├── data/
│   ├── novel_db/                    # 新規（DB ファイル格納）
│   │   ├── novel.db                 # SQLite + FTS5 + メタデータ（chunks/pages/books 等）
│   │   └── novel.lancedb/           # LanceDB ベクトルストア（Phase 62、NTFS 必須）
│   └── kindle_novel/                # 既存（PDF / 画像 / サムネイル）
│       ├── images/                  # 元画像（永続保持）
│       └── thumbnails/              # 既存（流用または削除、後述）
├── routers/
│   ├── novel_db.py                  # 新規（検索 / 質問 / ライブラリ / 再構築）
│   └── ...
└── services/
    └── novel_db/                    # 新規パッケージ
        ├── __init__.py
        ├── migrations.py            # Alembic upgrade_head() ヘルパー（起動時呼び出し）
        ├── connection.py            # sqlite3 接続 + sqlite_vec.load()
        ├── extractor.py             # PyMuPDF blocks 抽出 + OCR subprocess インターフェース
        ├── ocr_worker.py            # yomitoku OCR ワーカー（common/ocr/venv で実行）
        ├── chunker.py               # 句点境界チャンク（800 字 / overlap 50）
        ├── embedder.py              # Ollama bge-m3 ラッパー
        ├── character_extractor.py   # Ollama gemma4:e4b で主要登場人物を抽出
        ├── contextualizer.py        # gemma4:e4b でチャンクごとの位置説明を生成（B-9）。should_skip_context() を公開（Phase 55-2）
        ├── query_expander.py        # gemma4:e4b で QA 質問を 3 個の検索クエリに展開（B-11）
        ├── retrieval.py             # post_qa / post_chat_session_start 共通の検索・コンテキスト構築（Phase 55-3: RetrievalResult + retrieve()）
        ├── _search_types.py         # 共有型（Scope / SearchHit）・_resolve_book_names(lru_cache) / _fetch_main_characters — Phase 70 抽出
        ├── fts5_search.py           # FTS5 BM25 クエリ整形・sanitize_snippet・fts_search — Phase 70 抽出
        ├── vector_search.py         # LanceDB KNN チャンク検索・search_book_summaries — Phase 70 抽出
        ├── rrf_ranker.py            # RRF 融合 hybrid_search / load_all_pages_of_book — Phase 70 抽出
        ├── search.py                # 後方互換再エクスポート（47 行）— Phase 70 で縮小
        ├── llm.py                   # 共通 Qwen モジュール経由のストリーミング（薄いラッパ）
        ├── builder.py               # 1 冊の DB 構築フロー（再構築含む）
        ├── _prompts.py              # プロンプトテンプレート・LLM オプション・parse_combined_output — Phase 60 抽出
        ├── summarizer.py            # 1 冊の俯瞰サマリ生成（Qwen 1-shot + map-reduce fallback）
        ├── job_queue.py             # 再構築ジョブの全体ロック + キュー API（NovelDbJobQueue）
        ├── job_worker.py            # ジョブ実行 worker スレッド（NovelDbJobWorker）— Phase 59 抽出
        └── library.py               # 書籍一覧取得・DB 状態問い合わせ

backend/scripts/                     # CLI 用ツール
├── build_novel_db.py                # 全件 / 個別書籍を CLI から再構築
├── extract_characters.py            # 主要登場人物の一括抽出
├── build_novel_summaries.py         # 書籍ごとの俯瞰サマリの一括生成（B-5）
└── build_chunk_contexts.py          # チャンク位置説明の一括生成 + 再 embedding（B-9）
```

---

## 4. データモデル（SQLite スキーマ）

スキーマは Alembic が唯一の真実の源。`backend/alembic/versions/` に revision が集約される。新規 DB は `0003_schema_base.py` が完全スキーマを生成し、既存 DB へのカラム追加は各 revision が冪等に実行する。起動時 `upgrade_head()` で自動適用（失敗で起動中断）。`schema.py` による起動時 DDL（`init_schema`）は廃止済み。

```sql
-- 書籍メタ（DB 構築時に upsert）
CREATE TABLE books (
    id                    INTEGER PRIMARY KEY,
    name                  TEXT NOT NULL UNIQUE,    -- フォルダ名 = PDF stem
    pdf_path              TEXT NOT NULL,
    images_dir            TEXT NOT NULL,
    page_count            INTEGER NOT NULL,
    indexed_at            TIMESTAMP NOT NULL,      -- DB 構築完了時刻
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    summary               TEXT,                    -- 俯瞰サマリ（summarizer 生成、NULL=未生成）
    summary_generated_at  TIMESTAMP                -- summary 生成日時
);
CREATE INDEX idx_books_name ON books(name);

-- ※ book_summaries_vec（vec0 仮想テーブル）は Phase 62 で廃止。
--    書籍サマリ embedding は LanceDB summaries テーブルに格納される。
--    スキーマ: (book_id: int, book_name: str, embedding: vector[1024])
--    詳細: backend/services/novel_db/lance_store.py get_summaries_table()

-- ページ単位（FTS5 検索の対象）
CREATE TABLE pages (
    id         INTEGER PRIMARY KEY,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_no    INTEGER NOT NULL,
    image_path TEXT,                     -- 絶対パス（無ければ NULL）
    full_text  TEXT,                     -- ブロック抽出 + 改行除去後の連結
    char_count INTEGER NOT NULL,
    UNIQUE(book_id, page_no)
);
CREATE INDEX idx_pages_book ON pages(book_id);

-- FTS5 インデックス（pages.full_text）
-- tokenize='trigram' により日本語の部分文字列マッチが可能
CREATE VIRTUAL TABLE pages_fts USING fts5(
    full_text,
    content='pages',
    content_rowid='id',
    tokenize='trigram'
);

-- チャンク単位（ベクトル検索の対象）
CREATE TABLE chunks (
    id                       INTEGER PRIMARY KEY,
    page_id                  INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    chunk_idx                INTEGER NOT NULL,
    text                     TEXT NOT NULL,
    char_count               INTEGER NOT NULL,
    contextual_text          TEXT,        -- B-9: チャンクの位置説明（80 字程度、contextualizer 生成）
    contextual_generated_at  TIMESTAMP
);
CREATE INDEX idx_chunks_page ON chunks(page_id);

-- ※ chunks_vec（vec0 仮想テーブル）は Phase 62 で廃止。
--    チャンク embedding は LanceDB chunks テーブルに格納される。
--    スキーマ: (chunk_id, book_name, page_no, text, char_count, page_count, embedding[1024])
--    B-9 適用後の embedding は (contextual_text + "\n\n" + text) で計算。
--    contextual_text が NULL のチャンクは text のみ（後方互換）。
--    詳細: backend/services/novel_db/lance_store.py get_chunks_table()

-- 質問履歴
CREATE TABLE qa_history (
    id            INTEGER PRIMARY KEY,
    asked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at   TIMESTAMP,
    scope_type    TEXT NOT NULL,         -- 'all' | 'series' | 'book'
    scope_id      TEXT,                  -- series_id (TEXT) | book name | NULL
    question      TEXT NOT NULL,
    answer        TEXT,
    prompt        TEXT NOT NULL,
    context_json  TEXT NOT NULL,         -- [{book, page_no, chunk_idx, score, text}, ...] の JSON
    model         TEXT NOT NULL,
    options_json  TEXT NOT NULL,
    eval_count    INTEGER,
    done_reason   TEXT,
    error_message TEXT
);
CREATE INDEX idx_qa_history_asked_at ON qa_history(asked_at DESC);

-- 再構築ジョブ（全体ロック + キュー）
CREATE TABLE rebuild_jobs (
    id              INTEGER PRIMARY KEY,
    job_type        TEXT NOT NULL,       -- 'book' | 'series' | 'all'
    target_id       TEXT,                -- book name | series_id | NULL
    state           TEXT NOT NULL DEFAULT 'queued',  -- 'queued' | 'running' | 'completed' | 'failed' | 'canceled'
    enqueued_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at      TIMESTAMP,
    finished_at     TIMESTAMP,
    progress_total  INTEGER,             -- 対象書籍数
    progress_done   INTEGER,             -- 処理完了書籍数
    current_step    TEXT,                -- 実行中ステップ名（full_build 時: 'step 1/3: rebuild_from_pages' 等）
    error_message   TEXT
);
CREATE INDEX idx_rebuild_jobs_state ON rebuild_jobs(state, enqueued_at);
```

### 4.1. シリーズ ID の扱い

- `qa_history.scope_id` には文字列で series_id を保存
- series_id の実体は `meta.db` の `meta` テーブルの `series_id` カラム（`services/series_detector.py` が生成）に従う（Phase 64 で JSON → SQLite 移行済み）
- novel.db 内には series テーブルを作らず、参照のたびに `services/meta_store.py` 経由で `meta.db` から取得（書籍数 11 冊規模では速度問題なし）

---

## 5. DB 構築パイプライン

`services/novel_db/builder.py` がエントリーポイント。1 冊の構築フローは以下：

```
Path(pdf) ──┐
            ├─→ extractor.extract_pages() → list[{page_no, full_text, char_count}]
            │
            ├─→ books / pages テーブルに INSERT
            │
            ├─→ chunker.chunk_page(full_text) で各ページを分割
            │   → list[{page_id, chunk_idx, text}]
            │
            ├─→ embedder.embed_batch(texts) で 16 件単位に bge-m3 埋め込み
            │
            └─→ chunks テーブルに INSERT + LanceDB chunks テーブルに add()
```

### 5.1. テキスト抽出（`extractor.py`）

```python
import re
import fitz  # PyMuPDF

_NEWLINE_RE = re.compile(r"\n+")

def extract_pages(pdf_path: Path) -> list[dict]:
    """PDF のページ単位テキストを取得する。

    PyMuPDF の get_text("blocks") で縦書き 1 列 = 1 ブロックとして取得し、
    各ブロック内の改行（1 文字 TextObject 配置の副作用）を除去してから連結する。
    """
    pages = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            blocks = page.get_text("blocks")
            parts: list[str] = []
            for b in blocks:
                cleaned = _NEWLINE_RE.sub("", b[4]).strip()
                if cleaned:
                    parts.append(cleaned)
            full_text = "\n".join(parts)
            pages.append({
                "page_no": i + 1,
                "full_text": full_text,
                "char_count": len(full_text),
            })
    return pages
```

PoC スクリプトで動作確認後、本実装に昇格（PoC ディレクトリ `tmp_poc/` は実装完了後に削除）。

#### 5.1.1. 画像 OCR モード（`mode=ocr`）（2026-05-13 追加）

`rebuild_jobs.mode` が `ocr` のとき、PDF テキスト層の代わりに `images/*.png` を yomitoku で OCR してページテキストを生成する。旧称 `reocr` は Phase 59 で廃止（起動時 DB migration で `ocr` に正規化）。

**実行方式: subprocess 分離**

yomitoku は `D:\61.tool\common\ocr\venv` 専用の GPU パッケージ群に依存するため、backend `.venv` には含めない。代わりに **`ocr_worker.py`** をスタンドアロンスクリプトとして `common/ocr/venv/Scripts/python.exe` で実行し、結果を JSON 行ストリームで受け取る。

```
job_queue._execute_job
  └─ extractor.run_ocr_subprocess(images_dirs: list[Path])
        └─ subprocess: common/ocr/venv/Scripts/python.exe ocr_worker.py <dir1> <dir2> ...
              ├─ yomitoku を 1 度初期化（複数書籍で再利用）
              └─ 各書籍: {"book_name": "...", "pages": [...]}  # stdout に 1 行ずつ flush
  └─ builder._store_ocr_pages(book_name, pages)  # DB への書き込みは main process
```

**ポイント**:
- yomitoku のモデルロード（~30 秒）は全書籍で 1 回だけ行う
- stderr は backend の stdout/ログにそのまま流れる（GPU/モデル読み込みログが見える）
- worker が 1 書籍でエラーした場合は `{"book_name": "...", "error": "..."}` を返し、job 全体を失敗にする

### 5.2. チャンク分割（`chunker.py`）

#### 現行方式: ページ単位 `chunk_page()`

- ページの全文長 ≤ 800 字 → 1 チャンク
- 800 字超 → 句点境界（`。」!?`）優先で分割、50 字オーバーラップ

#### §4.4 実験用: クロスページ `chunk_book()`

OCR 後の全ページを 1 本に連結してから句点境界でチャンク分割する実験的実装。

| パラメータ | 値 |
|---|---|
| `max_chars` | 1200 字 |
| `overlap` | 120 字 |
| `min_page_chars` | 30 字（章扉・ヘッダのみのページをスキップ） |
| 句点境界 | `。」!?`（末尾 max_chars/10 以内を探索） |

- 各チャンクの `page_id` = **チャンクが開始するページ**（リーダーへのジャンプに使う）
- `bisect` による二分探索でオフセット → page_id を O(log N) で解決

#### §4.4 実験用: Qwen 意味セグメンテーション `chunk_qwen`

1 冊全文を Qwen に送り、意味的なまとまり（章・場面・時間軸の区切り）の境界ページを JSON 配列で返させ、境界ごとにページ群を分割してから `chunk_book()` でサブ分割する方式。

比較スクリプト: `backend/scripts/eval_chunk_strategy.py --qwen`

#### §4.4 実験結果（2026-05-12）

書籍「おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)」(118 ページ / 115,256 字) で 3 方式を比較（クエリ: 「父王が次期女王を発表する場面」）。

| 方式 | チャンク数 | avg文字数 | top1 スコア |
|---|---|---|---|
| 現状 `chunk_page` | 202 | 594字 | **0.5824** (p11) |
| 実験B `chunk_book` | 109 | 1176字 | 0.5558 (p11) |
| 実験A `chunk_qwen` | 109 | 1172字 | 0.5558 (p11) |

Qwen が識別した境界: `[13, 41, 74, 107]`（p74 = 「第三章 騎士と暗殺者」の実際の章頭）

**考察:**
- この書籍はページあたり平均 ~980字と密度が高く、ページ単位でも十分なコンテキストが得られる。そのため `chunk_page` が最高スコアを維持
- `chunk_qwen` は境界識別の精度は高い（章頭と一致）が、チャンク数・avg字数が `chunk_book` とほぼ同一になった。セグメント数が少ない（4点）ため、各セグメントが十分大きく `chunk_book` と同様に収束したため
- ページ密度が低い書籍（挿絵多め・会話主体、平均 300〜500 字/ページ）では `chunk_book` / `chunk_qwen` の優位性が出る可能性あり

**決定:** 現状の `chunk_page` を本番方式として維持。`chunk_book` および `chunk_qwen` は実験コードとして `chunker.py` に残し、今後必要に応じて再検証できるようにする。

### 5.3. embedding（`embedder.py`）

- Ollama API (`POST /api/embed`) を httpx で叩く（Phase 63 にて urllib → httpx 移行）
- モデル: `bge-m3`（1024 次元）
- バッチサイズ: 16
- タイムアウト: 180 秒
- エラー: `httpx.HTTPError`（接続失敗・タイムアウト・4xx/5xx）を `EmbeddingError` に変換

**GPU 配置ポリシー**: リクエストボディに `options.num_gpu = NOVEL_DB_EMBED_NUM_GPU`（既定 `0` = CPU 専用）を渡す。Full Build 実行中は llama-server（Qwen 35B, `-ngl 28`）が VRAM を約 10〜10.5 GB 占有するため、bge-m3 を CPU で動かすことで余裕を確保する。GPU で動かしたい場合は `NOVEL_DB_EMBED_NUM_GPU=99` を設定して uvicorn を再起動する。

PoC スクリプトベースで、エラーハンドリング・ログ出力を追加して本実装。

### 5.4. ジョブごとの構築フロー（`builder.py`）

```python
def rebuild_book(conn, book_name: str) -> None:
    """1 冊を再構築する（既存レコードは削除して上書き）。"""
    pdf_path = NOVEL_PDF_DIR / f"{book_name}.pdf"
    images_dir = NOVEL_IMAGES_DIR / book_name
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    # 既存レコード削除（CASCADE で pages / chunks も連動）
    # ⚠️ pages.main_characters / chunks.contextual_text / books.summary / books.summary_generated_at /
    #    LanceDB summaries の該当行も道連れに消える。再構築後に extract_characters /
    #    build_novel_summaries / build_chunk_contexts を CLI で再実行する必要がある
    conn.execute("DELETE FROM books WHERE name = ?", (book_name,))

    pages = extract_pages(pdf_path)
    cur = conn.execute(
        "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
        "VALUES (?, ?, ?, ?, datetime('now'))",
        (book_name, str(pdf_path), str(images_dir), len(pages)),
    )
    book_id = cur.lastrowid

    # pages
    for p in pages:
        img = images_dir / f"{p['page_no']:03d}.png"
        cur = conn.execute(
            "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) "
            "VALUES (?, ?, ?, ?, ?)",
            (book_id, p["page_no"], str(img) if img.exists() else None,
             p["full_text"], p["char_count"]),
        )
        p["id"] = cur.lastrowid
    conn.execute(
        "INSERT INTO pages_fts (rowid, full_text) "
        "SELECT id, full_text FROM pages WHERE book_id = ?", (book_id,))

    # chunks + embedding
    all_chunks = []
    for p in pages:
        if p["char_count"] < 30:
            continue
        for idx, c in enumerate(chunk_page(p["full_text"])):
            all_chunks.append({"page_id": p["id"], "chunk_idx": idx, "text": c})

    for batch in chunked(all_chunks, 16):
        embeds = embed_batch([c["text"] for c in batch])
        for c, emb in zip(batch, embeds):
            cur = conn.execute(
                "INSERT INTO chunks (page_id, chunk_idx, text, char_count) "
                "VALUES (?, ?, ?, ?)",
                (c["page_id"], c["chunk_idx"], c["text"], len(c["text"])),
            )
            # Phase 62: LanceDB chunks テーブルに add()（serialize_f32 不要）
            # get_chunks_table().add([{"chunk_id": chunk_id, "book_name": ..., "embedding": emb, ...}])
    conn.commit()
```

### 5.5. 失敗時ロールバック

PDF 破損 / Ollama 接続失敗 / embedding タイムアウト等で構築途中にエラーが起きた場合：

- ジョブ全体を 1 つの SQLite トランザクションで囲み、例外時に `conn.rollback()`
- 該当書籍の既存レコードはトランザクション開始前に削除済み（再構築なら）。トランザクションロールバック後は **「未構築」状態** に戻る（半端な部分データは残らない）
- `rebuild_jobs.state='failed'` + `error_message` にエラー内容を記録
- フロントは状態 polling で失敗を検知 → トースト等でユーザーに通知

```python
def rebuild_book(conn, book_name: str) -> None:
    try:
        with conn:  # コンテキストマネージャでトランザクション開始（自動 commit/rollback）
            conn.execute("DELETE FROM books WHERE name = ?", (book_name,))
            ...  # extract → INSERT pages → embedding → INSERT chunks
        # 成功時はここに到達
    except Exception:
        # conn の `with` ブロックで自動 rollback 済み。再構築前の状態に戻る
        raise
```

### 5.6. 主要登場人物抽出（`character_extractor.py`）（2026-05-10 追加）

LLM 質問応答時の **キャラ帰属誤りを抑制** するための事前処理。`builder.rebuild_book` の最終フェーズで、各 `pages.full_text` に対して `gemma4:e4b` を呼び、登場人物名のリストを `pages.main_characters`（JSON 配列）に保存する。

**なぜ必要か:** 質問応答プロンプトでは、複数ページ・複数書籍の抜粋をまとめて Qwen に渡す。各ページにキャラのヒントが無いと、Qwen が「page 110 で（主人公が）演技で自分を守る」のように、別キャラの心情を主人公の話として誤統合することがある（PoC で観察）。各ページの主要登場人物をプロンプト先頭に明示することで、帰属を正しく誘導する。

**設定**:

```python
NOVEL_DB_CHAR_EXTRACT_MODEL = "gemma4:e4b"   # 短答型タスクは軽量モデルで十分
# Qwen と同じく stream=True / think=False / num_predict 余裕持たせ
```

**スキーマ**: `pages.main_characters TEXT` 列に `["デューク", "レティ", ...]` 形式の JSON 文字列。未抽出ページは `NULL`。

**抽出のタイミング**:
- 別 CLI（`extract_characters.py`）でユーザーが任意のタイミングで実行する。`builder.rebuild_book` には組み込まない（再構築のたびに数十分かかるのを避けるため）
- 1 ページごとに 1〜3 秒、1359 ページで 30〜60 分（`gemma4:26b` の thinking 暴走を避けるため `e4b` を採用した結果として現実的時間に収まった）

**フォールバック**: 抽出失敗（接続エラー / 空応答 / JSON パース失敗）時は `NULL` のまま続行し、次ページに進む。検索 / 質問応答は `main_characters IS NULL` を許容する（プロンプトに「主要登場人物: ...」のヒント行が出ないだけ）。

### 5.7. 書籍俯瞰サマリ生成（`summarizer.py`）（2026-05-10 追加: B-5）

`scope=all` / `scope=series` の **概括的な質問**（「シリーズ全体のテーマは？」等）に対する回答品質を引き上げるための事前処理。各冊を 1500 字程度に要約して `books.summary` に保存し、QA 時にプロンプト先頭へ追加する（[§7.2](#72-プロンプト構築) 参照）。

**なぜ必要か:** ハイブリッド検索が拾える `top_k=16` 件のページ抜粋では、全 11 冊・1359 ページを俯瞰しきれない構造。Qwen 切替で踏み込みは改善したが、検索コンテキスト依存である限り、シリーズ全体を網羅した回答は本質的に難しい。事前に各冊の要約を作っておけば、scope=all/series 時に「全冊のあらすじ + ヒットページの抜粋」をコンテキストとして Qwen に渡せる。

**生成方式（B-6 検証で 1-shot 化、2026-05-10）:**

| フェーズ | 内容 | LLM オプション |
|---|---|---|
| 入力フィルタ | `min_chars` / `body_page_margin` で前付け・後付けを除外 | — |
| **1-shot（既定）** | 全文をそのまま Qwen に渡し、1500 字サマリへ | `num_predict=2560`, `num_ctx=131072` |
| フォールバック（>200,000 字） | map: 各 ~20000 字チャンクを 400 字に / reduce: 統合して 1500 字に | map: `num_ctx=16384`, reduce: `num_ctx=16384` |

実機検証で `num_ctx=131072` が **VRAM 12GB（RTX 5070）+ システム RAM 32GB の環境**で OOM なく動作することを確認（[小説RAG_技術知見.md §0 ハードウェア前提](../../../log/技術知見/小説RAG_技術知見.md)）。モデル本体（Q4_K_M、27GB）は VRAM に乗り切らず Ollama が約 61% を CPU 側にオフロードしているため、num_ctx 拡大による KV cache 増加も主にシステム RAM 側で吸収される。1 冊あたり 1.6 chars/token 換算で 113k 字 = ~71k tokens のため、131k ctx に余裕で収まる。

**プロンプト管理（Phase 60）**: プロンプトテンプレート・LLM オプション・`parse_combined_output` は `_prompts.py` に一元化。`summarizer.py` はビジネスロジックのみ保持する。

**スキーマ**: `books.summary TEXT`（NULL = 未生成）/ `books.summary_generated_at TIMESTAMP`。`update_book_summary()` 内で LanceDB `summaries` テーブル（B-8）への upsert も同時に行う（Phase 62 で `book_summaries_vec` から移行）。

**生成タイミング**: 別 CLI（[§5.9](#59-cli) の `build_novel_summaries.py`）でユーザーが任意のタイミングで実行する。`builder.rebuild_book` には組み込まない（再構築のたびに数十分かかるのを避けるため）。

**所要時間**: 1 冊あたり **4〜6 分**（1-shot 経路、Qwen3.6:35b-a3b）。11 冊で **約 40〜60 分**。map-reduce フォールバック経路では 1 冊 ~10 分。

**フォールバック**: `summary IS NULL` の書籍は QA プロンプトに含めない（後方互換）。検索 / QA は summary が無くても従前通り動作する。

### 5.8. チャンク位置説明生成（`contextualizer.py`）（2026-05-11 追加: B-9）

Anthropic 2024-09 ブログの **Contextual Retrieval** 手法を踏襲。各チャンクに対して書籍俯瞰サマリ（B-5）をコンテキストとして与え、LLM に「このチャンクが書籍内のどの場面か」を 1 文（~80 字）で生成させる。`(contextual_text + chunk_text)` を bge-m3 で再 embedding すると、retrieval の recall が大きく改善する（Anthropic 計測で 35〜49% 改善）。

**なぜ必要か:** 現状 `chunks.text` は「ページから 800 字を切り出しただけ」で、書籍内での位置づけ（巻 / シーン / 登場キャラ群）が embedding に含まれない。「父王が次期女王を発表する場面」のような抽象的な質問が、該当ページに直接の語彙的一致がなくても、位置説明（「page 11 で父親が奇策を講じる宣言の場面」）込みの embedding なら top に来る。

**生成方式:**

| 項目 | 値 |
|---|---|
| モデル | `gemma4:e4b`（軽量、`NOVEL_DB_CONTEXT_MODEL` で切替可）|
| プロンプト | 書名 + 書籍俯瞰サマリ + チャンク先頭 1200 字 → 80〜120 字の位置説明（**本文の固有名詞と特徴的フレーズを必ず含める** よう明示指示、2026-05-12 改良）|
| 出力長 | `num_predict=256`, `num_ctx=8192` |
| 1 チャンク所要 | ~5 秒（実機計測、2026-05-12 のプロンプト拡張後） |
| 全件（2,230 チャンク） | 約 110〜130 分 |

**スキーマ**: `chunks.contextual_text TEXT`（NULL = 未生成または skip 対象）/ `chunks.contextual_generated_at TIMESTAMP`。

**skip 条件**（2026-05-12 追加 / `should_skip_context`、Phase 55-2 でサービス層に移動・パブリック化）: 以下のチャンクは ctx 生成を省き `contextual_text = NULL` のまま保つ。検索 noise を防ぎ、`make_embedding_input` が text のみで embedding する経路に乗せる。
- `chunks.char_count < NOVEL_DB_MIN_BODY_CHARS`（既定 300）— 章扉・目次・人物紹介などの薄いチャンク
- `pages.page_no <= NOVEL_DB_BODY_PAGE_MARGIN` または `page_no > page_count - NOVEL_DB_BODY_PAGE_MARGIN`（既定 5）— 表紙・タイトルページ・あとがき・奥付などの余白ページ

**embedding 再構築**: 生成完了後、`(contextual_text + "\n\n" + chunk_text)` を bge-m3 でバッチ 16 で embedding し、LanceDB `chunks` テーブルを `delete(chunk_id=...)` → `add([...])` で更新する（`make_embedding_input` ヘルパ、Phase 62 で `chunks_vec` から移行）。skip 対象は ctx が NULL のため text のみで再 embedding。

**生成タイミング**: 別 CLI（[§5.9](#59-cli) の `build_chunk_contexts.py`）でユーザーが任意のタイミングで実行する。B-5 のサマリが前提（プロンプトのコンテキストに使う）。

**フォールバック**:
- `book.summary IS NULL` の書籍はスキップ（コンテキスト無しでは位置説明が薄くなるため）
- LLM 接続エラーや空応答時は `contextual_text` を NULL のまま続行 → そのチャンクの embedding は text のみで計算（後方互換）
- 重量モデルにフォールバックしたい場合は `NOVEL_DB_CONTEXT_MODEL=qwen3.6:35b-a3b` 等で切替

**実機検証**:
- **初版（2026-05-11）**: 書籍 1 巻（202 チャンク）のパイロットで avg 63 字 / min 29 字 / max 88 字 の位置説明、サンプル 5 件本文整合、「父王が次期女王を発表する場面」→ p11 top 1 retrieval を確認
- **改良版（2026-05-12）**: id=23（おこぼれ姫 1 巻、202 chunks）の `--redo` で **ok=174 / skip=28 / ng=0**、長さ avg 106 字（指示の 80〜120 字に整合）。ctx 内に「レティーツィア」「ディーク・バンドゥエット」等の固有名詞 + 「騎士の誓いの言葉」「我が右手は剣、我が左手は楯」等の特徴的フレーズが含まれることを確認

### 5.10. キャラクター辞典生成（`character_summarizer.py`）（2026-05-12 追加: B-15）

`pages.main_characters` カラムを集計してキャラ名を列挙し、各キャラについて「そのキャラが登場するページの本文のみ」を Qwen に投入してキャラ視点の 1 段落（~400 字）の人物像を生成し、`book_characters` テーブルにキャッシュする。フロントの「登場人物」セクション（[フロントエンド設計 §x.x]）から `GET /novel_db/books/{book}/characters/{name}` で取得して表示する。

**なぜ必要か:** 続巻を読み始める前 / 間が空いた後に「このキャラは何者だったか」を即座に思い出したい。既に B-9 の chunk ctx で「キャラ名 → 主要シーン」は検索できるが、キャラ単位の俯瞰ページがあれば人物関係の思い出しコストが大幅に下がる。

**生成方式:**

| 項目 | 値 |
|---|---|
| モデル | `qwen3.6-iq4xs`（`NOVEL_DB_LLM_MODEL`、llama-server バックエンド） |
| 入力範囲 | 該当キャラが `main_characters` に含まれる page の `full_text` を page_no 順に連結（先頭 80,000 字までで truncate） |
| プロンプト | 書名 + キャラ名 + 本文 → 1 段落 400 字程度。役職 / 行動 / 心情の動き / 関係性の変化 / 印象的な台詞を指示 |
| 出力長 | `num_predict=1024`, `num_ctx=65536` |
| 1 キャラ所要 | 主要キャラ（80k 字 body）で ~470 秒、副キャラ（数 page）で ~30 秒 |

**スキーマ**: `book_characters(id, book_id, name, summary, first_page, page_count, generated_at)`。UNIQUE(book_id, name)。

**API 連動**: API 一覧はキャラ一覧 + has_summary フラグだけ返し、詳細 API でサマリ全文 + 主要シーン top 5（`char_count` 多い順）を返す。

**生成タイミング**: 別 CLI（[§5.11](#511-cli) の `build_character_summaries.py`）でユーザーが任意のタイミングで実行する。`pages.main_characters` の前提（character_extractor で抽出済み）が必要。

**フォールバック**:
- `main_characters IS NULL` の page しかない書籍はキャラ抽出 = 0 で処理スキップ
- LLM 失敗時は `book_characters.summary = NULL` のまま統計値（first_page / page_count）だけ保存
- 既に summary 済みのキャラは `--redo` 未指定なら skip

**`--min-pages` による足切り** (2026-05-12 追加): `page_count` がこの値未満のキャラは集計から除外する（既定 1 = 足切りなし）。副キャラ（1〜4 page のみ登場）はサマリ生成の材料が薄く品質が低い傾向があり、また 11 冊フルバッチで 100〜200 キャラの副キャラが含まれるため、`--min-pages 5` で主要キャラに絞ると全冊バッチの所要時間を 6〜7 時間 → 2〜3 時間に短縮できる。副キャラのサマリは需要が出てから個別生成（`--character NAME`）または閾値を下げて再実行で対応する。

**実機検証 (2026-05-12)**: id=23 おこぼれ姫 1 巻 の top 3 キャラで動作確認:
- レティ（95p, body 80k chars）: 419 chars サマリ / 471 秒
- デューク（69p, body 80k chars）: 365 chars サマリ / 83 秒
- アストリッド（35p, body 38k chars）: 365 chars サマリ / 41 秒
- 合計 596 秒、`ng=0`、`book_characters` に 3 行 UPSERT 完了。生成内容は役職 / 行動 / 心情の変化 / 関係性 / 印象的フレーズを含む 1 段落 (400 字程度) に整合
- 2 キャラ目以降が高速化したのは llama-server の KV cache 効果と見られる

**全 11 冊バッチ実行 (2026-05-12)**: `--all --min-pages 5` で実行:
- 完了: **96 キャラ生成 / skip=3 / ng=0 / 48 分**
- 各冊 フィルタ後 9〜11 キャラ（フィルタ前 31〜46）→ KV cache が効きやすい程よい粒度
- 1 冊あたり初手 ~75s + 続行 ~10〜15s/キャラ、書籍切替時に system prefix 変化で cache miss

### 5.12. マルチターン会話 QA（`qa_sessions.py` + `llm.stream_chat`）（2026-05-12 追加: B-16）

単発 QA（`/qa`）と並走する形で、会話履歴を保ったマルチターン QA を追加した。1 セッションは **scope 固定**（開始時に book / series / all を選び、途中変更不可）。LLM は `LlamaServerBackend.astream_chat` 経由で OpenAI 互換 `messages` をそのまま流す。

**スキーマ**:
- `qa_sessions(id, scope_type, scope_id, title, started_at, last_message_at)`
- `qa_messages(id, session_id, role, content, eval_count, done_reason, created_at)` — CASCADE on session 削除

**初手 (`POST /qa/sessions`)**:
1. 既存 `/qa` と同じ手順で hits + book_summaries を構築（`scope=book` で `NOVEL_DB_QA_FULL_BOOK_MODE` なら全 page 読み）
2. `build_chat_system_message(scope, context_block)` で `messages[0] = {role: 'system', content: ...}` を作成
3. session 作成 → system + user メッセージを DB に append
4. `stream_chat([system, user])` を SSE 配信
5. 終端で assistant メッセージを DB に append（`eval_count` / `done_reason` 込み）

**続行 (`POST /qa/sessions/{id}/messages`)**:
1. `load_chat_messages(session_id)` で過去 messages（system + user/assistant 履歴）を全件取得
2. 新 user メッセージを DB に append
3. `stream_chat(prior + [new_user])` を SSE 配信
4. 終端で assistant を append

**LLM オプション**:
- `LLM_OPTIONS` を流用（`num_ctx=32768` 既定）。`scope=book` で `NOVEL_DB_QA_FULL_BOOK_MODE` なら `num_ctx=131072` に上書き
- 履歴は無圧縮で先頭から積む。長期セッションで肥大化したら要約圧縮を後付け（MVP では非対応）

**llama-server の KV cache 効果**:
- 初手の system + user は長い（page 抜粋 30 万字+質問）が、続行ターンでは同じ prefix が再送されるため KV cache がヒットし、2 ターン目以降は実質「新 user + assistant」分の推論に短縮される
- B-15 の検証で 2 キャラ目以降が 5× 高速化したのと同じ効果

**バックエンド前提**:
- `NOVEL_DB_LLM_BACKEND=llama_server` 必須。Ollama 経路は `LlamaServerBackend` の `stream_chat` を持たないため、`local_llm.OllamaBackend.stream_chat` は `NotImplementedError` を投げ、SSE で `{"error": ...}` を 1 度返してストリーム終了する
- thinking 抑制は `chat_template_kwargs.enable_thinking=False`（`local_llm` 側で既定）

**実機検証 (2026-05-12)**: おこぼれ姫 1 巻 × scope=book で 3 ターン会話を実施:
- Q1「レティの心情は物語の始めと終わりでどう変化した？」（初手、131k 全 page 読み）: 数分
- Q2「その変化のきっかけは？」（KV cache ヒット）: 約 1 分
- Q3「他キャラとの関係に影響は？」: 同程度
- 観察:
  - **KV cache 効果**: Q1 → Q2 で 3〜5× 高速化。system + Q1 + A1 の prefix を再利用できているため
  - **文脈保持**: Q2 が「Q1 のレティの心情変化」を主語にしたきっかけ説明、Q3 が「レティの変化を起点とした他 4 キャラとの関係変化」を整理 → 履歴を踏まえた深掘りが機能
  - **根拠 page 明記**: p19 / p30 / p40 / p66-67 / p68 / p75-76 / p99-100 / p105 / p107-108 など全域から page 番号付き引用 → 131k 全 page 読みが効いている
  - **キャラ帰属**: デューク / フリートヘルム / グイード / レオンハルト / アストリッド の固有名詞 + 行動 + 内面が正しく対応、誤統合なし

### 5.13. CLI

| スクリプト | 用途 |
|---|---|
| `backend/scripts/build_novel_db.py` | 全件 / 個別書籍の DB 再構築（PDF テキスト抽出 + チャンク + embedding）|
| `backend/scripts/extract_characters.py` | 主要登場人物の一括抽出（`pages.main_characters` を埋める）|
| `backend/scripts/build_novel_summaries.py` | 書籍俯瞰サマリの一括生成（`books.summary` を埋める）|
| `backend/scripts/build_chunk_contexts.py` | チャンク位置説明の一括生成 + 再 embedding（`chunks.contextual_text` を埋め、`chunks_vec` を更新）|
| `backend/scripts/build_character_summaries.py` | キャラクター辞典の一括生成（`book_characters.summary` を埋める）（B-15）|

```bash
uv run python scripts/build_novel_db.py --all                      # 全件
uv run python scripts/build_novel_db.py --book "おこぼれ姫と..."   # 個別
uv run python scripts/build_novel_db.py --series "おこぼれ姫"      # シリーズ

uv run python scripts/extract_characters.py --all                  # 全 page から主要登場人物を抽出
uv run python scripts/extract_characters.py --book "..." --redo    # 既存値を上書き

uv run python scripts/build_novel_summaries.py --all               # 全冊の俯瞰サマリ生成
uv run python scripts/build_novel_summaries.py --book "..." --redo # 既存値を上書き

uv run python scripts/build_chunk_contexts.py --all                # 全チャンクに位置説明 + 再 embedding
uv run python scripts/build_chunk_contexts.py --book "..." --redo  # 既存値を上書き

uv run python scripts/build_character_summaries.py --book "..."           # キャラ辞典生成（B-15）
uv run python scripts/build_character_summaries.py --book "..." --redo    # 既存サマリを上書き
uv run python scripts/build_character_summaries.py --book "..." --character "レティ"  # 1 キャラのみ
uv run python scripts/build_character_summaries.py --all --min-pages 5    # page_count >= 5 の主要キャラのみ
```

`build_novel_db.py` は内部的に `services/novel_db/job_queue.py` を経由（同時実行禁止）。
`extract_characters.py` / `build_novel_summaries.py` / `build_chunk_contexts.py` / `build_character_summaries.py` はジョブキューを使わず逐次実行（再構築と並行しない前提）。

**処理順序の推奨**: `build_novel_db` → `extract_characters` → `build_novel_summaries` → `build_chunk_contexts`。`build_chunk_contexts` は `book.summary` を要求するため、サマリ生成より後に実行する必要がある。

**UI からの統合実行（§4.5、2026-05-13 追加）**: 上記 5 スクリプトを順番に手動実行する代わりに、UI の「Full Build」ボタンから `mode=full_build` ジョブをキューに投入することで 1 操作で完結できる。内部処理は [§5.14](#514-full_builderpy本構築統合-パターン-a) で定義する `build_book_full()` が担う。

### 5.14. `full_builder.py`（本構築統合、パターン A）（2026-05-13 追加: §4.5）

5 つの CLI バッチ（`build_novel_db`, `extract_characters`, `build_novel_summaries`, `build_character_summaries`, `build_chunk_contexts`）を 1 関数 `build_book_full(book_name, *, redo=False)` に統合し、UI ジョブキュー（`mode=full_build`）から呼び出せるようにする。

**処理ステップ（1 冊あたり）**:

| ステップ | 関数 | スキップ条件 |
|---|---|---|
| 1. チャンク・embedding 再構築 | `builder.rebuild_from_pages()` | なし（常実行）|
| 2. 書籍俯瞰サマリ生成 | `summarizer.summarize_book()` + `update_book_summary()` | `books.summary IS NOT NULL` かつ `redo=False` |
| 3. 主要登場人物抽出 | `character_extractor.extract_main_characters()` per page | `pages.main_characters IS NOT NULL` かつ `redo=False` |
| 4. キャラクター辞典生成 | `character_summarizer.summarize_character()` + `upsert_character()` per character | `book_characters.summary IS NOT NULL` かつ `redo=False` |
| 5. チャンク位置説明生成 + 再 embedding | `contextualizer.generate_chunk_context()` + re-embed per chunk | `chunks.contextual_text IS NOT NULL` かつ `redo=False` |

**Gemma 系バックエンド切替（§4.5）**: ステップ 3・5 は既定 `gemma4:e4b`（Ollama）を使うが、`NOVEL_DB_GEMMA_BACKEND=qwen` とすると `LlamaServerBackend`（Qwen、think=False 自動）に一本化できる。切替は `_llm_backend.build_short_answer_backend()` ファクトリで行う。

```python
# NOVEL_DB_GEMMA_BACKEND: "ollama" (既定) | "qwen"
# "qwen" 時: gemma4:e4b の代わりに llama-server の Qwen を使用（think=False 自動）
```

**ジョブキュー統合**: `job_queue.py` の `JobMode` に `"full_build"` を追加。`_execute_job()` 内で `build_book_full(book_name)` を呼ぶ。`progress_total = 冊数`, `progress_done = 完了冊数`（ステップ単位の細粒度は追わない）。

**UI**: `BookCard` に「Full Build」ボタンを追加（書籍が OCR 済みの場合に表示）。`mode=full_build` でジョブをキューに投入する。`RebuildJobBanner` でラベル表示。

---

## 6. 検索（`search.py` → Phase 70 以降は 4 モジュールに分離）

> **Phase 70 変更**: `search.py` は以下の 4 サブモジュールに分割済み。`search.py` は後方互換のため全シンボルを再エクスポートする薄いラッパーのみ。
> | モジュール | 責務 |
> |---|---|
> | `_search_types.py` | `Scope` / `SearchHit` / `_resolve_book_names` / `_fetch_main_characters` |
> | `fts5_search.py` | `build_fts5_or_query` / `sanitize_snippet` / `fts_search` |
> | `vector_search.py` | `vec_search` / `search_book_summaries` |
> | `rrf_ranker.py` | `hybrid_search` / `load_all_pages_of_book` |

### 6.1. ハイブリッド検索（FTS5 OR + ベクトル + RRF）

PoC スクリプト（旧 `tmp_poc/search.py`）の `hybrid_search()` を本実装に昇格。

**ベクトル embedding の構成（B-9 適用後）**: LanceDB `chunks` テーブルの `embedding` は `(contextual_text + "\n\n" + chunk_text)` を bge-m3 で計算した値（Phase 62 で `chunks_vec.embedding` から移行）。`contextual_text` が NULL の chunk は `chunk_text` のみで計算する（後方互換）。これにより「該当ページに直接の語彙的一致がない抽象的なクエリ」でも、位置説明込みの semantic 距離で top に来るようになる。

```python
def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    scope: ScopeFilter,
    top: int = 20,
    fts_n: int = 30,
    vec_n: int = 30,
    k_rrf: int = 60,
) -> list[SearchHit]:
    """FTS5 + ベクトル検索を Reciprocal Rank Fusion でページ単位に融合する。

    scope: 'all' | ('series', series_id) | ('book', book_name) のいずれか
    """
    # FTS5: クエリを OR フレーズに整形（PoC build_fts5_or_query 関数）
    or_query = build_fts5_or_query(query)
    fts_rows = _fts_search(conn, or_query, scope, fts_n) if or_query else []

    # ベクトル: 質問文を bge-m3 で埋め込み、k 件取得
    emb = embed_batch([query])[0]
    vec_rows = _vec_search(conn, emb, scope, vec_n)

    # RRF
    pages: dict[int, dict] = {}
    for rank, row in enumerate(fts_rows):
        ...
    for rank, row in enumerate(vec_rows):
        ...

    return ranked[:top]
```

### 6.2. ScopeFilter

```python
@dataclass
class ScopeFilter:
    type: Literal["all", "series", "book"]
    id: str | None = None  # series_id or book_name

    def book_name_predicate(self) -> str:
        """SQL の WHERE 句に追加するフィルタを返す。"""
        if self.type == "all":
            return ""
        if self.type == "book":
            return "AND b.name = :scope_id"
        if self.type == "series":
            # series_id は meta.db 参照で book_name のリストに展開
            ...
```

シリーズスコープでは `meta.db` の meta テーブルから該当 series_id の書籍リストを取得し、`b.name IN (...)` で SQL に展開する。

### 6.3. ハイライト

FTS5 の `snippet()` 関数を SQL 内で利用し、`<mark>` タグで囲む：

```sql
SELECT
    p.page_no,
    p.full_text,
    snippet(pages_fts, 0, '<mark>', '</mark>', '…', 32) AS snippet,
    bm25(pages_fts) AS score
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.id
WHERE pages_fts MATCH ?
```

#### 6.3.1. snippet のサニタイゼーション

フロントは `dangerouslySetInnerHTML` で snippet を描画するため、**バックエンド側で HTML をサニタイズして `<mark>` タグのみ許可** する：

1. SQL の `snippet()` 出力を取得（テキスト本文 + `<mark>` 区切り）
2. Python 側で以下の処理を行ってからレスポンスに含める：
   - 本文中の HTML 特殊文字（`<`, `>`, `&`, `"`, `'`）を一旦 `&lt;` 等にエスケープ
   - その後、`&lt;mark&gt;` / `&lt;/mark&gt;` のみを `<mark>` / `</mark>` に戻す
   - 結果として、本文中の `<` や `>` は表示用にエスケープされ、`<mark>` 以外のタグは作れない

```python
import html
import re

_MARK_ESCAPED = re.compile(r"&lt;(/?mark)&gt;")

def sanitize_snippet(snippet: str) -> str:
    escaped = html.escape(snippet)
    return _MARK_ESCAPED.sub(r"<\1>", escaped)
```

これにより、フロントは追加のサニタイザ（DOMPurify 等）を導入せず、`dangerouslySetInnerHTML` を安全に使える。

#### 6.3.2. ベクトル検索のみのチャンク

ベクトル検索でのみヒットしたチャンクは `chunks.text` の先頭 200 字を使う（ハイライトなし）。HTML 特殊文字のエスケープのみ実施。

### 6.4. 検索結果の型

```python
@dataclass
class SearchHit:
    book_name: str
    page_no: int
    snippet: str          # FTS5 ハイライト or チャンク先頭
    has_highlight: bool
    image_url: str | None
    rrf_score: float
    main_characters: list[str] | None  # ページの主要登場人物（character_extractor 由来、未抽出は []）
```

### 6.5. 書籍サマリのベクトル検索（B-8、2026-05-10 追加）

`scope=all` / `scope=series` での **概括的な質問** に対して、ページレベルの hybrid search に加えて **書籍サマリ自体** を retrieval 候補にする。

**処理フロー**:
1. `hybrid_search()` でページ単位の top-K hit を取得（従来通り）
2. `search_book_summaries(conn, query, scope, top=NOVEL_DB_QA_TOP_SUMMARIES)` でサマリベクトル検索を実行
3. ヒット書籍の和集合 `(ページ hit 書籍) ∪ (サマリ hit 書籍)` を取って `load_summaries_for_books()` に渡す
4. `build_prompt()` で **【書籍俯瞰サマリ】** ブロックに展開

**FTS5 を使わない理由**: サマリは抽象表現が中心で、ユーザーの質問語との keyword 一致は起きにくい。bge-m3 の意味類似度のほうが効く。

```python
def search_book_summaries(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    *,
    top: int = 11,
) -> list[tuple[str, float]]:
    """LanceDB `summaries` テーブルに対するベクトル検索（Phase 62 で `book_summaries_vec` から移行）。
    Returns: [(book_name, distance), ...]（distance 昇順）
    """
```

**動作確認**: 「メルディの軍師としての活躍」→ 「10 二人の軍師」が distance 0.97 で 1 位（タイトル通り軍師がテーマの巻が圧勝）、「1 巻」が 1.18 で 2 位、と意味的に妥当な順位を返すことを実機確認。

**フォールバック**: LanceDB `summaries` テーブルが空の場合（embedding 未生成）は空リストを返し、page 単位の hit-book-summaries だけが prompt に乗る（後方互換）。

### 6.6. 検索フィルタ（2026-05-10 追加）

`hybrid_search()` には章扉・目次・人物紹介・あとがき等の **薄いページや書誌付録** をノイズとして除外するためのフィルタを 3 つ持たせる。デフォルト値は `backend/config.py` で集中管理する。

| パラメータ | デフォルト | 役割 |
|---|---|---|
| `min_chars` | `NOVEL_DB_MIN_BODY_CHARS = 300` | `pages.char_count` がこの値未満のページを除外。章扉・目次・人物紹介の薄い 1 ページを弾く |
| `body_page_margin` | `NOVEL_DB_BODY_PAGE_MARGIN = 5` | 各書籍の **先頭・末尾 N ページ** を除外。表紙・口絵・あとがき・解説・奥付を弾く |
| `max_per_book` | `NOVEL_DB_QA_MAX_PER_BOOK = 5` | 1 書籍あたりの取得上限。`scope=all` / `scope=series` で特定書籍に偏らないよう均等化（B-13 段階 B で 2 → 5 に拡大、同書籍に集中する質問で深さ向上）|

`top_k` のデフォルトも段階的に引き上げた（`NOVEL_DB_QA_TOP_K = 64`、B-13 段階 A で 16 → 32、段階 B で 32 → 64 に拡大）。フィルタで弾かれた分を見越して多めに取り、`max_per_book = 5` で書籍を分散させる方針。11 冊 × 5 = 最大 55 件取得可能（`top_k = 64` の枠内）。

**フィルタの効き方の注意**:
- `min_chars` を厳しくしすぎると挿絵が多い章でヒットを取り逃す。300 字は経験値（PoC で「短すぎる」と感じた境界）
- `body_page_margin=5` は標準的な軽小説の付録厚みに合わせた値。前付け / 後付けが薄い書籍では誤って本編序盤・終盤を削る可能性がある。実害が出たら値を見直す
- `max_per_book` は `scope=book` のときは効かない（同一書籍内で `top_k` 件取得する設計）

---

## 7. 質問応答（`llm.py`）

### 7.1. Qwen SSE ストリーミング（共通モジュール経由、2 バックエンド切替）

- LLM クライアントは `D:\61.tool\common\llm` の `local_llm` パッケージ
  （`Backend(ABC)` + `LlamaServerBackend` / `OllamaBackend` の 2 具象）
  を sys.path 経由で取り込む
- Pic2PDF 側の `services/novel_db/_llm_backend.py` で **sys.path 注入 +
  Backend 構築** をまとめており、各 service ファイル (`llm.py` / `summarizer.py`)
  は `from ._llm_backend import build_qwen_backend` だけ書けばよい
- **B-14 / ADR-0009 で `NOVEL_DB_LLM_BACKEND` 切替を追加**（既定 `llama_server`、
  Phase C / 2026-05-11 で `ollama` 分岐を撤去 → 現状 `llama_server` 1 択 +
  未知バックエンドは `LLMError`）。バックエンド分岐・OpenAI 互換 SSE → Ollama 形式
  イベントの正規化・thinking 抑制（`chat_template_kwargs.enable_thinking=false`）
  はすべて共通モジュール側に集約
- 共通モジュール側で **Qwen3.x の thinking モデル必須要件**（thinking 抑制・
  `stream=True`・`num_predict` を thinking で食い潰されない値にする）を担保している
- レスポンスは正規化された dict。`{response, done, done_reason, prompt_eval_count,
  eval_count}` の Ollama 互換形式で yield されるため、利用側は backend 種別を
  意識せず従来通り `event.get("response")` / `event.get("done")` のまま使える
- 完了後（`done: true` 受信時）に履歴を保存

```python
# services/novel_db/_llm_backend.py（抜粋）
import sys

_LLM_PKG_DIR = r"D:\61.tool\common\llm"
if _LLM_PKG_DIR not in sys.path:
    sys.path.insert(0, _LLM_PKG_DIR)

import config
from local_llm import (
    Backend, BackendConfig, LlamaServerBackend, LLMError, OllamaBackend,
)

def build_qwen_backend() -> Backend:
    if config.NOVEL_DB_LLM_BACKEND == "llama_server":
        return LlamaServerBackend(BackendConfig(
            base_url=config.NOVEL_DB_LLAMA_SERVER_URL,
            model=config.NOVEL_DB_LLM_MODEL,
        ))
    if config.NOVEL_DB_LLM_BACKEND == "ollama":
        return OllamaBackend(BackendConfig(
            base_url=config.NOVEL_DB_OLLAMA_BASE_URL,
            model=config.NOVEL_DB_LLM_MODEL,
        ))
    raise LLMError(f"unknown NOVEL_DB_LLM_BACKEND: {config.NOVEL_DB_LLM_BACKEND}")


# services/novel_db/llm.py（抜粋）
from ._llm_backend import build_qwen_backend

_BACKEND = build_qwen_backend()  # プロセス起動時に 1 度だけ

async def _astream_ask(prompt, *, model=None, options=None, timeout=None):
    """共通 Backend に委譲する thin wrapper（テストで monkeypatch 用）。"""
    async for event in _BACKEND.astream_ask(
        prompt, model=model, options=options, timeout=timeout,
    ):
        yield event

async def stream_qa(prompt, *, model=NOVEL_DB_LLM_MODEL, options=None, timeout=600.0):
    async for event in _astream_ask(prompt, model=model, options=options or LLM_OPTIONS, timeout=timeout):
        yield event
```

**設計上の決定（A-3、2026-05-11）**:
- env var bridge (`os.environ.setdefault("QWEN_*", ...)`) を廃止し、
  `BackendConfig` を引数渡しする方式に統一
- `config` の値は call-time で参照（`from config import X` ではなく `config.X`）。
  monkeypatch で reload 不要、後続テストへの状態漏れもない
- `_astream_ask` は `_BACKEND.astream_ask` への薄い委譲。テストでは
  `llm._astream_ask` を monkeypatch することで Backend 実体（HTTP）を介さず
  動作確認できる

**バックエンド構成（採用後）**:

| コンポーネント | バックエンド | ポート | 用途 |
|---|---|---|---|
| Qwen3.6-IQ4_XS | **llama.cpp llama-server** | 11435 | RAG 質問応答 + 書籍俯瞰サマリ生成 |
| gemma4:e4b | Ollama | 11434 | 主要登場人物抽出 / Contextual Retrieval ctx 生成 / Query Expansion |
| bge-m3 | Ollama | 11434 | 埋め込み |

**`NOVEL_DB_GEMMA_BACKEND`（§4.5 追加）**: `"ollama"`（既定）か `"qwen"` で切替可。`"qwen"` 設定時は gemma4:e4b の代わりに llama-server の Qwen を使用（`_DEFAULT_THINK=False` により thinking トークンなし）。`build_short_answer_backend()` ファクトリが自動選択する。

llama-server は Windows タスクスケジューラの `llama-server-qwen` タスク（ONLOGON トリガ、Limited 権限）で自動起動される。起動コマンドは `D:\61.tool\common\llama.cpp\b9101\start-qwen-server.bat`。

なぜ共通モジュールに切り出したかは [ADR-0007](../../基本設計/ADR/0007_llm-extraction-qwen-adoption.md)、なぜ llama-server に切り替えたかは [ADR-0009](../../基本設計/ADR/0009_llm-backend-llama-server.md) を参照。実機ベンチで応答 5× 短縮を確認している。なぜ Backend 抽象に再設計したかは [LLM 層リファクタリング計画](../../../archive/LLM層リファクタリング_完了記録.md)（A-0〜A-7、2026-05-11、Phase C で Ollama rollback 経路撤去）を参照。

### 7.2. プロンプト構築

```
以下は小説『{book_title}』からの抜粋です。
これを参考にして質問に答えてください。

【回答ルール】
- 根拠としたページ番号を必ず明記してください（例: 「page 50 に記述あり」）。
- 引用する際は、誰の発言・行動・心情かを必ず明記してください。
  良い例: 「page 32 でウィラードが『～』と忠誠を誓う」
  悪い例: 「page 110 で（主人公が）演技で自分を守る」
          （← 実際は別キャラの心情なのに主人公の話として誤統合）
- 各 page には「主要登場人物: ...」のヒントが付いているので、その人物の
  発言・行動として帰属させてください。書かれていない人物の行動として推論を
  結びつけることは避けてください。
- 別々の page にあるキャラの行動を、同一人物の行動として安易に統合しないでください。
- 質問が抽象的・概括的な場合（テーマ / 主人公の成長 / シリーズ全体の特徴など）は、
  汎用的な単語の羅列で済ませず、以下を含めて構造的に深く分析してください:
    1. 具体的なシーン・出来事を 3 つ以上挙げる
    2. それらが示すテーマ・キャラクターの変化・物語上の意味を分析する
    3. 異なる時期・巻の対比があれば言及する
- 質問が具体的（特定のキャラ・場面・セリフ）な場合は、関連する記述を統合して詳しく答えてください。
- 抜粋に直接の記述がなくても、関連する複数の記述から推論して構いません。
- 全く関連する記述がない場合のみ「該当箇所が見つかりません」と答えてください。

{context}

質問: {question}

回答:
```

context の各 page ヘッダ:
- `scope=book` のとき: `[page N, 主要登場人物: A, B, C]`
- `scope=all` / `scope=series` のとき: `[書名 page N, 主要登場人物: A, B, C]`
- `main_characters` が空なら「主要登場人物: ...」部分は省略

PoC 当初は最小プロンプトだったが、Qwen への切り替えで「シリーズ全体」スコープの概括質問で **キャラ帰属の誤統合** が観察された（複数ページのキャラを混同）。`character_extractor` で抽出したヒントをページごとに付与し、明示的な帰属ルールをプロンプトに追加することで誤統合率を下げた（PoC 計測で 18% 程度まで低下、許容範囲）。

**書籍俯瞰サマリの埋め込み**（B-5、2026-05-10 追加）:

`scope=all` / `scope=series` のとき、ヒットした書籍の `books.summary` を `load_summaries_for_books()` で一括取得し、プロンプト先頭に **【書籍俯瞰サマリ】** ブロックとして埋め込む。

```
以下は小説『...』からの抜粋です。
これを参考にして質問に答えてください。

【書籍俯瞰サマリ】（各書籍の事前生成あらすじ。背景知識として活用）

■ 書籍 A
（あらすじ 1500 字程度）

■ 書籍 B
（あらすじ 1500 字程度）

【回答ルール】
...
```

サマリが未生成（`summary IS NULL`）の書籍は単にブロックに含めない（後方互換）。`scope=book` のときはこのブロック自体を付与しない（page 抜粋で十分なため）。

### 7.3. LLM パラメータ

```python
LLM_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.2,
    "num_predict": 4096,
    "num_ctx": NOVEL_DB_QA_NUM_CTX,  # config 化、既定 32768（B-13 段階 B、2026-05-11）
}
```

`num_predict=4096` は Qwen 系で `done_reason='stop'` で完走するのに十分な値（共通モジュールのデフォルト 8192 を `LLM_OPTIONS` で上書き）。

**`num_ctx` は `NOVEL_DB_QA_NUM_CTX`（既定 32768）で config 化**。段階的に拡大した経緯:

| 段階 | num_ctx | top_k | max_per_book | 採用日 | 主な狙い |
|---|---:|---:|---:|---|---|
| PoC | 8,192 | 16 | 2 | 2026-05 | 初期 |
| **A** | **16,384** | **32** | 2 | 2026-05-11 | 切り詰めバグ解消（`prompt_eval_count` が 8,192 にぴったり張り付いていた問題） |
| **B** | **32,768** | **64** | **5** | 2026-05-11 | 概括質問の深さ向上（B-14 で応答 5× 速くなった分の余裕を使う） |
| **C**（既定）| **131,072** | 全 page | — | 2026-05-11 | scope=book で本文丸読み。応答時間 4.5× 増を許容して本文 9 箇所以上から具体的引用付きの深い分析を得る |

**注**: 既定は段階 C（`NOVEL_DB_QA_FULL_BOOK_MODE=true`）。scope=book 時は全 page
読み、scope=all/series 時は引き続き段階 B 相当（top_k=64 / max_per_book=5）。
段階 B に戻す場合は `NOVEL_DB_QA_FULL_BOOK_MODE=false` の env で即時切替可。

段階 B では `top_k=64` のページ抜粋（~24k 字）+ 全 11 冊サマリ（~11k 字）+ システム
プロンプト + 質問 ≒ **~40k 字 / ~25k tokens** に達するため、`num_ctx=32768` が必要。
段階 B 用には `-c 36864` で運用していたが、段階 C 採用後の現在は **`-c 131072`**
（scope=book 全 page 読み対応のため、scope=all/series でもヘッドルームが余るだけで実害なし）。

`max_per_book=5` は段階 B で導入。scope=all/series でも同一書籍内のページを最大 5 件
まで集め、同書籍に集中する質問（「この書籍の主人公の心情変化」等）に深く答えられる
ようにする。11 冊 × 5 件 = 最大 55 件取得可能（`top_k=64` の枠内）。

ロールバック: `NOVEL_DB_QA_NUM_CTX=16384 NOVEL_DB_QA_TOP_K=32` の環境変数で段階 A
相当に戻る（`max_per_book` だけはコード定数のためコード戻しが必要）。

#### 段階 C: scope=book 全 page 読み込みモード（既定、本採用）

`NOVEL_DB_QA_FULL_BOOK_MODE=true`（既定）で有効。scope=book のとき hybrid_search
を bypass して書籍の全 page（`min_chars` / `body_page_margin` フィルタ後）を
page_no 順で LLM に投げる。実装は [`search.py:load_all_pages_of_book`](../../backend/services/novel_db/search.py)。

llama-server は `start-qwen-server.bat` で `-c 131072 -ncmoe 28` 起動（B-13 段階 C
本採用後の canonical 設定。Windows タスクスケジューラ `llama-server-qwen` に登録済み）。

実測（2026-05-11、11 巻 = 87k tokens の最大本に対する深い質問）:

| モード | hits | in_tok | out_tok | elapsed | 生成速度（短文 warm）|
|---|---:|---:|---:|---:|---:|
| 段階 B（hybrid_search） | 16 page | 2,779 | 1,688 | 37.4 s | 45 t/s |
| 段階 C（全 page 読み）| 100 page | **77,856** | 1,668 | **169.7 s** | 9.8 t/s（end-to-end）|

段階 C は **1 冊丸読み（78k tokens）を 170 秒で処理**し、本文 9 箇所以上から具体的な
セリフ・場面を引用する深い分析が得られる。代わりに応答時間は段階 B の 4.5×。

**-ncmoe 28 採用根拠**（2026-05-11、ncmoe スイープ）:

| -ncmoe | VRAM | A_short tg* | B_mid tg* | C_long tg* |
|---:|---:|---:|---:|---:|
| 32 | 56% (6.9 GB) | 21.4 | 55.0 | 59.4 |
| 30 | 63% (7.7 GB) | 42.9 | 53.3 | 54.2 |
| **28** | **70% (8.5 GB)** | **46.3** | **55.6** | **56.2** |

A_short（純粋な生成速度に近い）で -ncmoe 28 が最速。B_mid/C_long も僅差で 28 がベスト。
VRAM 30% 余裕あり。-ncmoe 26 以下は将来の最適化余地として残す。

ロールバック: `NOVEL_DB_QA_FULL_BOOK_MODE=false` の env で段階 B 相当の hybrid_search
経路に戻る（プロセス再起動不要）。llama-server 側は num_ctx=131072 で動いているが
scope=book で過剰な ctx を使わないだけなので問題なし。

### 7.4. Query Expansion（`query_expander.py`、B-11、2026-05-11 採用）

QA エンドポイントでハイブリッド検索を実行する前に、軽量 LLM（gemma4:e4b、`NOVEL_DB_QA_EXPAND_MODEL` で切替可）でユーザーの質問から **追加の検索クエリを 3 個生成** し、元の質問と合わせて **合計 4 つのクエリで `hybrid_search` を並列実行**。結果を `(book_name, page_no)` でデデュープ、RRF スコア最大値で並べ替えて top_k に絞る。

**なぜ必要か**: 「主人公の成長」「キャラ A と B の関係性」のような **抽象質問・関係質問** では、ユーザーの 1 クエリだけだと semantic 距離が遠い page を取り逃すことがある。複数の角度（場面 / キャラ / 行動 / 関係性 / 時期）から検索することで retrieval recall を改善する。

**B-9（Contextual Retrieval）との直交関係**:
- B-9: chunk 側 embedding を強化（位置説明を含める）
- B-11: query 側を強化（複数の検索角度を生成）
- 両方適用で「クエリ ↔ チャンク」の両端から retrieval 堅牢性が累積

**プロンプト**（gemma4:e4b に渡す）:
```
次の質問に対し、小説の本文を全文検索 / 意味検索するための短い検索クエリを N 個生成。
- 各クエリは異なる切り口（場面 / キャラ / 行動 / 関係性 / 時期 など）
- 各クエリは 10〜20 字程度のキーワード列
- 元のキーワードを含めても可
- 前置きや番号付けは不要、1 行 1 クエリ

質問: {question}
検索クエリ（N 行）:
```

**設定（環境変数で切替可）**:
- `NOVEL_DB_QA_EXPAND_ENABLED`（デフォルト `true`、品質優先方針）
- `NOVEL_DB_QA_EXPAND_N`（デフォルト 3）
- `NOVEL_DB_QA_EXPAND_MODEL`（デフォルト `gemma4:e4b`、Qwen を使いたい場合は変更）

**応答時間ペナルティ**: gemma4:e4b の短答呼び出しで **実測 +3〜5 秒**。`expand_query` が失敗（接続エラー / 空応答）した場合は元の質問のみで通常検索（後方互換）。

### 7.5. SSE エンドポイント

```python
@router.post("/qa")
async def qa_endpoint(req: QaRequest) -> StreamingResponse:
    """[Query Expansion →] ハイブリッド検索 → Qwen ストリーミング → 履歴保存"""
    # B-11: 質問を gemma4:e4b で複数クエリに展開（無効時は [question] だけ）
    queries = expand_query(req.question) if NOVEL_DB_QA_EXPAND_ENABLED else [req.question]

    rows_by_key: dict[tuple[str, int], SearchHit] = {}
    for q in queries:
        sub_rows = hybrid_search(
            conn, q, scope=req.scope,
            top=NOVEL_DB_QA_TOP_K,
            min_chars=NOVEL_DB_MIN_BODY_CHARS,
            body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
            max_per_book=NOVEL_DB_QA_MAX_PER_BOOK,
        )
        for h in sub_rows:
            key = (h.book_name, h.page_no)
            if key not in rows_by_key or h.rrf_score > rows_by_key[key].rrf_score:
                rows_by_key[key] = h
    rows = sorted(rows_by_key.values(), key=lambda h: -h.rrf_score)[:NOVEL_DB_QA_TOP_K]
    # B-8: scope=all/series ではサマリベクトル検索の hit も合流させる
    if req.scope.type in ("all", "series"):
        hit_books = {r.book_name for r in rows}
        summary_hits = search_book_summaries(
            conn, req.question, req.scope, top=NOVEL_DB_QA_TOP_SUMMARIES,
        )
        relevant_books = sorted(hit_books | {n for n, _ in summary_hits})
        book_summaries = load_summaries_for_books(conn, relevant_books)
    else:
        book_summaries = None
    prompt = build_prompt(req.question, rows, scope=req.scope, book_summaries=book_summaries)
    history_id = save_history_start(conn, req, prompt, rows)

    async def event_stream():
        full_response = []
        async for event in stream_qa(prompt):
            if event.get("response"):
                full_response.append(event["response"])
                yield f"data: {json.dumps({'token': event['response']})}\n\n"
            if event.get("done"):
                save_history_finish(conn, history_id, "".join(full_response), event)
                yield f"data: {json.dumps({'done': True})}\n\n"
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

ジョブキューが running 状態のときは 503 + Retry-After を返す（後述 §8）。

### 7.6. 連投警告

連投警告（直前と完全一致）はフロントエンド側のチェックで行い、バックエンド側ではチェックしない。フロントから常に送ってもよい設計（API はステートレス）。

### 7.7. 質問の停止（クライアント切断）

- フロントの「停止」ボタンで `AbortController.abort()` → fetch コネクションが切断される
- FastAPI 側は `request.is_disconnected()` を SSE ループ内で監視し、切断検知時に Ollama リクエストを `aclose()` してリソース解放
- 履歴は `done_reason='canceled'` で保存（途中まで生成された応答テキストはそのまま `qa_history.answer` に格納）

```python
async def event_stream(request: Request):
    full_response: list[str] = []
    try:
        async for event in stream_qa(prompt):
            if await request.is_disconnected():
                _save_history_finish(history_id, "".join(full_response),
                                      {"done_reason": "canceled", "eval_count": 0})
                return
            if event.get("response"):
                full_response.append(event["response"])
                yield f"data: {json.dumps({'token': event['response']})}\n\n"
            if event.get("done"):
                _save_history_finish(history_id, "".join(full_response), event)
                yield f"data: {json.dumps({'done': True})}\n\n"
                return
    except Exception as e:
        _save_history_error(history_id, str(e))
        raise
```

---

## 8. 再構築ジョブ（`job_queue.py` + `job_worker.py`）

### 8.1. 全体ロック + ジョブキュー

Phase 59 でキュー管理と worker 実行を 2 クラスに分離した。

| クラス | ファイル | 責務 |
|---|---|---|
| `NovelDbJobQueue` | `job_queue.py` | `enqueue` / `cancel` / `get_status` + ライフサイクル管理 |
| `NovelDbJobWorker` | `job_worker.py` | worker スレッド実行・DB 更新・ジョブ実行ロジック |

- バックエンド起動時に `main.py` の lifespan で `NovelDbJobQueue.start()` / `stop()` を呼ぶ
- `start()` 内で旧 JobMode 名を DB 上でマイグレーション（`pdf_text` → `rebuild`、`reocr` → `ocr`）
- 単一の worker スレッドで `rebuild_jobs` テーブルを polling し、`state='queued'` のジョブを古い順に実行
- `is_running` は `NovelDbJobQueue` が `NovelDbJobWorker` に委譲

```python
class NovelDbJobQueue:
    def __init__(self) -> None:
        self._wakeup = threading.Event()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._worker = NovelDbJobWorker(self._stop_event, self._wakeup)

    @property
    def is_running(self) -> bool:
        return self._worker.is_running

    def start(self) -> None:
        # スキーマ初期化は起動時に upgrade_head() で完了済み（main.py の lifespan）
        with with_db() as conn:
            conn.execute("UPDATE rebuild_jobs SET state='failed', error_message='aborted by server restart' WHERE state='running'")
            conn.execute("UPDATE rebuild_jobs SET mode='rebuild' WHERE mode='pdf_text'")
            conn.execute("UPDATE rebuild_jobs SET mode='ocr' WHERE mode='reocr'")
            conn.commit()
        self._worker_thread = threading.Thread(target=self._worker.run, name="NovelDbJobQueue", daemon=True)
        self._worker_thread.start()

    def enqueue(self, job_type: JobType, target_id: str | None = None, mode: JobMode = "rebuild") -> tuple[int, int]:
        ...  # INSERT + wakeup.set()

class NovelDbJobWorker:
    def run(self) -> None: ...          # スレッドエントリー
    def _drain_queue(self) -> None: ...
    def _claim_next_job(self) -> dict | None: ...
    def _mark_finished(...) -> None: ...
    def _update_progress/step/detail(...) -> None: ...
    def _execute_job(self, job: dict) -> None: ...  # mode 別分岐
    def _resolve_targets(self, job_type, target_id, mode) -> list[str]: ...
```

**ヘルパー関数（モジュールレベル）**:

| 関数 | 返す書籍 |
|---|---|
| `_list_all_book_names()` | `KINDLE_NOVEL_IMAGES_DIR` 配下の全サブディレクトリ名 |
| `_list_books_needing_ocr()` | images_dir に存在 かつ `books.ocr_done_at IS NULL`（OCR 未完了） |
| `_list_books_with_ocr_done()` | `books.ocr_done_at IS NOT NULL`（OCR 完了済み） |
| `_list_books_needing_full_build()` | `ocr_done_at IS NOT NULL AND indexed_at IS NULL`（Full Build 未完了） |
| `_list_books_needing_contexts()` | `contextual_text IS NULL` のチャンクを持つ書籍（コンテキスト生成未完了） |
| `_list_books_in_series(series_id)` | 指定シリーズに属する novel 書籍 |

**`_resolve_targets` の選択ロジック**（`job_type="all"` 時）:
- `mode="ocr"` → `_list_books_needing_ocr()`: OCR 未完了書籍のみ（重複処理防止）
- `mode="full_build"` → `_list_books_needing_full_build()`: Full Build 未完了書籍のみ（`indexed_at IS NULL`）
- `mode="generate_contexts"` → `_list_books_needing_contexts()`: コンテキスト未生成チャンクを持つ書籍のみ
- それ以外（`rebuild`）→ `_list_books_with_ocr_done()`: OCR 完了済み全冊

**有効な JobMode**（Phase 59 で旧名を廃止）:

| mode | 処理 |
|---|---|
| `rebuild` | pages.full_text → chunks / embeddings 再構築（旧 `pdf_text` と同義、DB 上は migrate 済み） |
| `ocr` | images/*.png → yomitoku OCR → pages.full_text（旧 `reocr` と同義、DB 上は migrate 済み） |
| `full_build` | rebuild → summarize → extract_chars → char_summary の統合フロー |
| `generate_contexts` | チャンクごとの文脈付与 + 再 embedding（Step 3 単独） |

### 8.2. 検索 / 質問 API のロック確認

```python
def _check_locked(queue: NovelDbJobQueue) -> None:
    if queue.is_running:
        raise HTTPException(
            status_code=503,
            detail="Database rebuild is in progress. Try again shortly.",
            headers={"Retry-After": "10"},
        )
```

`routers/novel_db/_deps.py` の `require_not_locked()` として実装（Phase 57 移行済み）。検索 / 質問エンドポイントに `Depends(require_not_locked)` を付与する。

### 8.3. ジョブ進捗表示

`rebuild_jobs.progress_total` / `progress_done` を builder 側から逐次更新。フロントは `GET /api/novel_db/rebuild/status` でポーリング（5 秒間隔）。

`mode=full_build` ジョブは追加で `current_step` にステップ名（`"step 1/3: rebuild_from_pages"` / `"step 2/3: summarize_book + characters"` / `"step 3/3: generate_contexts"`）を書き込む。SSE 経由でフロントに届き、実行中カードに `Step 1/3: ...` として表示される。

### 8.4. ジョブのキャンセル仕様

- **`state='queued'`（待機中）のジョブのみキャンセル可能**: `DELETE /api/novel_db/rebuild/{job_id}` で `state='canceled'` に更新
- **`state='running'`（実行中）のジョブはキャンセル不可**: 実行途中で中断すると embedding バッチの整合性が崩れるリスクと実装複雑化が利得を上回る。実行中の DELETE は **409 Conflict** を返す
- 待機中ジョブの一括キャンセル（例: 「キューを全部空に」）は当面非対応。必要になったら別エンドポイントで追加

---

## 9. ライブラリ表示（`library.py`）

### 9.1. 書籍一覧

```python
def list_books(conn: sqlite3.Connection) -> list[BookSummary]:
    """data/kindle_novel/images/ のサブディレクトリを起点に書籍リストを構築し、
    novel.db の DB 状態（is_indexed / page_count / indexed_at）と meta.db を結合して返す。

    ※ PDFs ではなく images/ ディレクトリを起点とする（PDFs は廃止済み）。
    """
    images_dir = Path(KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []

    meta = load_meta("novel")  # meta_store 経由
    indexed = _fetch_indexed_status(conn)  # {name: {page_count, indexed_at}}

    summaries = []
    for book_dir in sorted(d for d in images_dir.iterdir() if d.is_dir()):
        name = book_dir.name
        meta_entry = meta.get(f"{name}.pdf", {})
        info = indexed.get(name)
        summaries.append(BookSummary(
            name=name,
            authors=list(meta_entry.get("authors", [])),
            series_id=meta_entry.get("series_id"),
            series_title=meta_entry.get("series_title"),
            is_indexed=info is not None,
            page_count=info["page_count"] if info else None,
            indexed_at=info["indexed_at"] if info else None,
            thumbnail_url=_thumbnail_url(name),
            volume=meta_entry.get("volume"),
            publisher=meta_entry.get("publisher"),
            asin=meta_entry.get("asin"),
            series_index=meta_entry.get("series_index"),  # DnD 並び替え後の順序（float）
        ))
    return summaries
```

### 9.2. シリーズ一覧

既存 `series.router` のエンドポイント（or 既存 service）を流用。novel ソース限定でフィルタする。

「シリーズ未所属」の書籍はシリーズスコープの選択肢から除外（要件定義 TBD-7）。

---

## 10. API エンドポイント

`routers/novel_db.py` に集約。`prefix="/api/novel_db"`、`tags=["novel_db"]` で登録。

| メソッド | パス | 概要 | レスポンス |
|---|---|---|---|
| GET | `/api/novel_db/books` | 書籍一覧 + DB 状態 | `BookSummary[]` |
| GET | `/api/novel_db/series` | シリーズ一覧（novel 限定） | `SeriesSummary[]` |
| POST | `/api/novel_db/search` | ハイブリッド検索 | `SearchHit[]`（ページネーション） |
| POST | `/api/novel_db/qa` | 質問応答（**SSE ストリーミング**） | `text/event-stream` |
| GET | `/api/novel_db/qa/history` | 履歴一覧（時系列降順） | `QaHistoryEntry[]` |
| GET | `/api/novel_db/qa/history/{id}` | 履歴詳細（プロンプト全文・コンテキスト含む） | `QaHistoryDetail` |
| DELETE | `/api/novel_db/qa/history/{id}` | 履歴削除 | 204 |
| POST | `/api/novel_db/rebuild` | 再構築ジョブ起動 | `{job_id, queued_position}` |
| GET | `/api/novel_db/rebuild/status` | 現在のキュー状態 | `{is_running, current_job, queued_jobs[]}` |
| DELETE | `/api/novel_db/rebuild/{job_id}` | 待機中ジョブのキャンセル | 204 |

詳細な JSON スキーマは [API仕様書.md](../API.md) §X に追加（後続）。

---

## 11. 既存資産との関係

### 11.1. 静的ファイルマウント

[backend/main.py](../../backend/main.py):

```python
# 既存（流用）
app.mount("/kindle_novel/images",      StaticFiles(directory=KINDLE_NOVEL_IMAGES_DIR), ...)
app.mount("/kindle_novel/thumbnails",  StaticFiles(directory=KINDLE_NOVEL_THUMBNAIL_DIR), ...)

# 既存（新ビューア動作確認後に削除）
app.mount("/kindle_novel/pdfs",        StaticFiles(directory=KINDLE_NOVEL_PDF_DIR), ...)

# 新規（DB は静的配信不要、ルート経由で読み出し）
app.include_router(novel_db.router, prefix="/api", tags=["novel_db"])
```

画像配信は `/kindle_novel/images/{書籍名}/{連番}.png` を継続利用。フロント側で URL を組み立てる。

### 11.2. meta.db / シリーズ機能

- 書籍メタ（authors / hidden / read_state / series_id）は `meta.db` の `meta` テーブルで管理（Phase 64 移行済み）
- 既存 `services/series_detector.py` / `services/meta_store.py` / `services/meta_db.py` を novel_db でも参照
- novel_db.py は meta テーブルには書き込まない（read-only 参照）

### 11.3. 既存 `routers/library.py` との棲み分け

- 既存 `library.py` は **PDF 一覧表示** が主目的（main / kindle / generated / novel）
- 新規 `novel_db.py` は **novel ソース限定** の検索・質問・DB 構築
- novel タブのフロントは novel_db.py のエンドポイントのみを使う

---

## 12. テスト方針

`backend/tests/` に追加。既存パターンを踏襲（[詳細設計書_バックエンド編 §5](../詳細設計書_バックエンド編.md)）。

| ファイル | 対象 |
|---|---|
| `test_novel_db_extractor.py` | PyMuPDF blocks 抽出、改行除去、空ページ |
| `test_novel_db_chunker.py` | chunk_page（句点境界・オーバーラップ）+ chunk_book（クロスページ・page_id 解決） |
| `test_novel_db_search.py` | FTS5 OR クエリ整形、RRF マージ、scope フィルタ |
| `test_novel_db_builder.py` | 1 冊構築（embedding はモック）、再構築での既存削除 |
| `test_novel_db_job_queue.py` | キュー登録・順次実行・キャンセル |
| `test_router_novel_db.py` | API レイヤ（検索 / 履歴 / rebuild）。LLM はモック |

embedding / LLM の Ollama 呼び出しは `responses` ライブラリ等でモック化（実通信はテストで行わない）。

---

## 13. 移行・撤去計画

### Phase 1: 並行運用（実装完了直後）
- novel_db API + 新フロント novel タブを稼働
- 既存 `/kindle_novel/pdfs` マウント・既存 novel ビューアも残す
- 動作確認（11 冊で要件 UC-1〜UC-5 が成立すること）

### Phase 2: 旧資産の削除
- [backend/main.py:69](../../backend/main.py#L69) の `app.mount("/kindle_novel/pdfs", ...)` を削除
- [frontend/src/config/api.ts:110](../../frontend/src/config/api.ts#L110) の `source === 'novel'` 分岐を削除
- `backend/data/kindle_novel/pdfs/` 配下の PDF を削除（`thumbnails/` も novel ビューアで使っていたら見直し）
- `kindle-pdf/batch_ocr.py` / `searchable_pdf.py` は kindle 用途で残す（novel 用途のみ撤去）
- `meta.db` の `meta` テーブルに残る `pdf_path` 相当フィールド等が PDF 前提なら整理（Phase 64 移行後は SQLite 直接編集）

### 永続資産（削除しない）
- `backend/data/kindle_novel/images/{書籍名}/*.png`: 画像表示・再 OCR 用途
- `kindle-pdf/main_novel.py`: novel 画像取り込みツール

---

## 14. 既知の制限・将来検討

- **OCR ミスは `bge-m3` の意味距離で吸収** しているが、完全ではない（PoC で「薔→蕎」は救えたが、より多い誤認識ページがあれば回答品質が下がる）。**頻出ミスの辞書置換は導入せず**、問題が見つかったら **その書籍の元画像から yomitoku で再 OCR して書籍単位で DB を再構築する** 方針 → 将来機能として追加（後述）
- **Qwen3.6:35b-a3b の応答時間 80〜130 秒** は変えられない。UI でストリーミング表示してユーザー体感を緩和。Gemma 4:26b 時代（30〜100 秒）より長くなったが、概括的な質問への踏み込みが大幅に改善されたため受容（[ADR-0007](../../基本設計/ADR/0007_llm-extraction-qwen-adoption.md)）
- **キャラ帰属誤統合（残存課題）**: `main_characters` ヒント付与で誤統合率を下げたが、ゼロにはできていない（PoC 計測で ~18%）。完全防止には RAG ではなく書籍ごとの fine-tuning が必要で、ローカル小説向け個人ツールとしてはコスト超過。許容範囲として運用
- **シリーズ未所属書籍のグルーピング表示**: 全件スコープのライブラリ画面で「未所属」セクションを設けるかは 要件定義 §10 TBD-7 の通り、シリーズスコープからは除外（全件・単冊では含む）
- **複数モデル対応**: 質問応答は `qwen3.6-iq4xs`（Qwen3.6:35b-a3b の IQ4_XS 量子化、B-12 で 2026-05-11 採用）、主要登場人物抽出 / コンテキスト生成は `gemma4:e4b`。`backend/config.py` の `NOVEL_DB_LLM_MODEL` / `NOVEL_DB_CHAR_EXTRACT_MODEL` / `NOVEL_DB_CONTEXT_MODEL` で切替可。ロールバックは環境変数 `NOVEL_DB_LLM_MODEL=qwen3.6:35b-a3b` で即時可能（旧モデルは保険として残置）。将来 UI からのモデル切替は要件定義 §9 「将来検討事項」を参照
- **俯瞰質問の天井（B-5 / B-8 / B-9 で 3 段の対応済み）**: `scope=all` / `scope=series` での「シリーズ全体のテーマ」のような概括質問は、ハイブリッド検索が拾える `top_k=16` 件のページ抜粋に依存するため、全 11 冊・1359 ページを俯瞰しきれない構造だった。3 段の改善を順次適用:
    - **B-5（2026-05-10）**: `books.summary` を Qwen 1-shot で事前生成し、QA プロンプトの先頭に「書籍俯瞰サマリ」ブロックとして埋め込む（§5.7 / §7.2）
    - **B-8（2026-05-10）**: `book_summaries_vec` にサマリの bge-m3 ベクトルを格納し、`scope=all` / `scope=series` で `search_book_summaries` でサマリ自体を retrieval 候補に。ページに引っかからなかった書籍も俯瞰サマリで Qwen に伝わる（§6.5）
    - **B-9（2026-05-11）**: Anthropic 流の Contextual Retrieval。各チャンクに 80 字の位置説明を gemma4:e4b で生成し、`(contextual_text + chunk_text)` を再 embedding。検索 recall を 35〜49% 改善（§5.8）
- **書籍単位の再 OCR 機能（実装済み, 2026-05-13）**: UI の「OCR」ボタンから `mode=ocr` / `mode=reocr` ジョブをキューに投入し、`images/*.png` を yomitoku で OCR して pages テーブルを更新する。実行方式の詳細は [§5.1.1](#511-画像-ocr-モードmodeocr--modereocr2026-05-13-追加) を参照。
  - OCR 実行は `ocr_worker.py` を `D:\61.tool\common\ocr\venv\Scripts\python.exe` で subprocess 起動する方式（yomitoku の GPU 依存を backend venv から分離）
  - `rebuild_jobs.mode` カラムで `rebuild` / `ocr` / `full_build` / `generate_contexts` を切替（旧 `pdf_text`/`reocr` は Phase 59 で廃止、起動時 migration で正規化）

---

## 16. 読書会ディスカッション生成（B-20）

### 16.1 概要

書籍 1 冊の本文テキスト全体を Qwen 131k コンテキストに投入し、2 人のキャラクター（ペルソナ）が交互に語り合う対話を SSE ストリーミングで生成する。会話を内容把握補助・エンタメ両用に提供。

### 16.2 新規ファイル（実装済み、2026-05-13）

| ファイル | 役割 |
|---|---|
| `routers/novel_discussion.py` | SSE エンドポイント（generate / history） |
| `services/novel_db/discussion_service.py` | トークン推計・プロンプト構築・ターン解析・保存/一覧 |

### 16.3 ディレクトリ・保存形式

```
backend/data/kindle_novel/discussions/
  └─ {book_name}/
       └─ {YYYYMMDDTHHMMSSz}.json   ← UTC タイムスタンプ（ISO 形式）
```

JSON 構造:
```json
{
  "book": "書籍名",
  "personas": [
    {"name": "批評家", "style_description": "批評家・敬語丁寧・文学評論"},
    {"name": "ファン",  "style_description": "ファン・フランク・感情重視"}
  ],
  "turns": [{"speaker": "A", "text": "..."}, ...],
  "partial": false,
  "created_at": "2026-05-13T14:30:22+00:00"
}
```

### 16.4 プロンプト設計

LLM には `astream_chat` で messages 形式（system + user）を投入する。ターン境界は `[A]:` / `[B]:` マーカーで識別する。

```
[system]
小説タイトル / キャラクター A・B の名前と口調説明 /
書籍全ページ（load_all_pages_of_book 経由）を埋め込む。

ルール:
- キャラ A の発言は `[A]:` で始め、キャラ B の発言は `[B]:` で始める
- 各発言 100〜300 字程度
- num_turns 往復の対話を生成する

[user]
{num_turns} 往復の読書会対話をお願いします。
```

### 16.5 トークン超過チェック

生成前に本文のトークン数を推計する（1 token ≒ 1.5 日本語文字）。推計値が 112,000（131,072 ctx から出力 8,192 + プロンプト構造オーバーヘッドを除いた入力上限）を超える場合はエラー SSE を即座に返す（HTTP 200 で SSE error イベント）。

### 16.6 SSE 配信フロー

1. リクエスト受信 → バリデーション → `load_all_pages_of_book` で全ページ取得
2. トークン超過チェック → 超過時はエラー SSE を返して終了
3. `build_messages` でプロンプト構築 → `stream_discussion_turns` で SSE ストリーミング開始
4. トークン受信ごとにバッファ累積。`[A]:` / `[B]:` マーカー検出で 1 ターン完結 → SSE `{"type": "turn", "speaker": "A"|"B", "text": "..."}` 配信
5. クライアント切断時 → ループ終了・保存スキップ
6. 全ターン完了 → `save_discussion` で JSON 保存 → SSE `{"type": "done", "saved_path": "..."}` 送信

### 16.7 スコープ外

- 3 人以上のキャラクター
- ユーザーが会話に介入（コメント・方向指示）
- 生成済み対話の再編集
- 漫画・同人誌ソースへの対応

---

## 15. 関連ドキュメント

- 要件定義: docs/01_要件定義/小説テキスト検索・RAG機能.md
- 既存 OCR 設計: [docs/03_詳細設計/OCR設計書.md](OCR設計書.md)
- 既存 backend 全体: [詳細設計書_バックエンド編.md](../詳細設計書_バックエンド編.md)
- API 仕様書（後続追加）: [API仕様書.md](../API.md)
- フロントエンド設計（後続作成）: [小説テキスト検索・RAG機能_フロントエンド設計.md](小説テキスト検索・RAG機能_フロントエンド設計.md)
- ADR: [ADR-0007 LLM 抽出と Qwen 採用](../../基本設計/ADR/0007_llm-extraction-qwen-adoption.md)
- **運用知見の蓄積（実機ベンチマーク・モデル選定指針・トラブルシューティング）**: [docs/05_記録/小説RAG_技術知見.md](../../../log/技術知見/小説RAG_技術知見.md)
- PoC スクリプト（旧 `tmp_poc/`）: 実装完了後に削除済み。実装は `backend/services/novel_db/` 配下に集約
