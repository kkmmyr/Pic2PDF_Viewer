# 小説テキスト検索・RAG 機能 バックエンド設計書

novel タブの OCR テキストを SQLite + FTS5 + ベクトルで検索し、ローカル LLM（Qwen3.6:35b-a3b）で質問応答する機能の **バックエンド側** 設計書。本ファイルに集約し、要件は [要件定義: 小説テキスト検索・RAG機能.md](../01_要件定義/小説テキスト検索・RAG機能.md) を参照。

最終更新: 2026-05-11（B-9 Contextual Retrieval 追記 / summarizer の 1-shot 経路 / builder の道連れ削除コメント追加 / B-12 で LLM を IQ4_XS 量子化に切替 / B-13 段階 A で QA num_ctx を 16384 化・top_k を 32 に拡大）

---

## 1. 概要

### 1.1. 目的

- 既存 Searchable PDF（`backend/data/kindle_novel/pdfs/*.pdf`）から OCR テキストを抽出して SQLite に取り込む
- ハイブリッド検索（FTS5 OR + ベクトル `bge-m3`）+ ローカル LLM `qwen3.6-iq4xs`（Qwen3.6:35b-a3b の IQ4_XS 量子化、2026-05-11 切替）でページ番号付き引用回答を返す
- 主要登場人物のページ単位抽出（`gemma4:e4b`）でキャラ帰属の誤りを抑制したプロンプトを構築
- ライブラリ表示・DB 再構築・履歴保存・画像配信を提供する

### 1.2. 設計原則

- **疎結合**: 既存 backend にミニマル追加。`routers/novel_db.py` と `services/novel_db/` 配下に閉じる
- **既存パターン踏襲**: routers / services 分離・`_deps.py` の validated_source・`utils/path_utils.py` の validate_safe_path を流用（[CLAUDE.md backend conventions](../../.claude/CLAUDE.md)）
- **SQLite 単一ファイル**: 書籍データ・チャンク・ベクトル・履歴・ジョブをすべて 1 ファイルにまとめ、DB 配置・バックアップを単純化
- **既存 series / meta は流用**: 書籍 ↔ シリーズの紐付けは既存 `series.router` / `data/meta/novel/meta.json` をそのまま参照
- **LLM クライアントは共通モジュール**: thinking モデルの呼び出しロジックは `D:\61.tool\common\Qwen` に切り出し、他プロジェクトと共有（詳細は [ADR-0007](../02_基本設計/ADR/0007_llm-extraction-qwen-adoption.md)）
- **リアルタイム配信は SSE**: Qwen3.6 の応答（80〜130 秒）を Server-Sent Events で逐次配信

### 1.3. 関連ドキュメント

- 要件: [docs/01_要件定義/小説テキスト検索・RAG機能.md](../01_要件定義/小説テキスト検索・RAG機能.md)
- 既存 OCR: [docs/03_詳細設計/OCR設計書.md](OCR設計書.md)（yomitoku ベース）
- 既存 backend 全体: [詳細設計書_バックエンド編.md](詳細設計書_バックエンド編.md)
- フロントエンド設計: 別途 [小説テキスト検索・RAG機能_フロントエンド設計.md](小説テキスト検索・RAG機能_フロントエンド設計.md)（後続作成）
- API 仕様: [API仕様書.md](API仕様書.md) §X（後続追加）
- 運用知見（実機ベンチマーク・モデル選定・トラブルシューティング）: [docs/05_記録/小説RAG_技術知見.md](../05_記録/小説RAG_技術知見.md)

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
                            (FTS5 + sqlite-vec)
                                          │
                                          ▼
                            [Ollama localhost:11434]
                            ├─ bge-m3              (embedding)
                            ├─ gemma4:e4b          (主要登場人物 + チャンク位置説明: 短答型)
                            └─ qwen3.6-iq4xs       (RAG 質問応答 + 書籍俯瞰サマリ: thinking モデル, IQ4_XS 量子化)
                                  ▲
                                  │ 共通モジュール経由
                              [D:\61.tool\common\Qwen\lib\qwen_client.py]

[StaticFiles] /kindle_novel/images/{書籍名}/{連番}.png  (既存マウント流用)
```

### 2.2. 設計判断（Why）

- **既存 FastAPI に組み込む理由**: hitomi 監視は単発タスクなので別プロセスにしたが、本機能は対話型 API（検索・質問）が主であり、リクエスト都度の応答が必須。組み込み方が自然
- **SQLite + FTS5 + sqlite-vec を選んだ理由**:
    - PoC で検証済み、十分な性能（11 冊で約 10MB、検索 < 1 秒）
    - ChromaDB 等の別 DB を増やすより、メタ・FTS5・ベクトルを 1 ファイルで JOIN できる方が運用が楽
    - sqlite-vec は backend の uv に追加済み (`sqlite-vec==0.1.9`)
- **bge-m3 を採用した理由**: PoC で `nomic-embed-text` と比較し、日本語意味検索精度が明確に高い（OCR ミスを意味距離で吸収可能）
- **質問応答 LLM に Qwen3.6:35b-a3b を採用した理由**: 当初 PoC で gemma4:26b を採用したが、シリーズ全体の概括的な質問（「テーマ」「主人公の成長」など）に対する回答が浅く、踏み込みが足りなかった。Qwen3.6:35b-a3b（35B 総 / 活性 3B MoE）に切り替えたところ、同条件の質問で `done_reason='stop'` で完走し、章ごとの対比や具体例の引用を含む構造的回答が得られた。応答時間は 30〜100 秒 → 80〜130 秒に伸びたが、品質向上の方が大きい（詳細・経緯は [ADR-0007](../02_基本設計/ADR/0007_llm-extraction-qwen-adoption.md)）
- **主要登場人物抽出に gemma4:e4b を採用した理由**: 短答型タスク（人物名のリスト出力）であり、Qwen のような重量モデルは過剰。1300 ページの一括抽出を現実的な時間で回すために軽量モデルが必須。`stream=True` / `think=False` / `num_predict=4096` で安定動作する
- **LLM クライアントを共通モジュールに切り出した理由**: Qwen3.x は thinking モデルで `stream=True` / `think=False` の併用が必須。`num_predict` を thinking ブロックに食い潰される事故が起きやすく、地雷を踏み抜く呼び出しを各プロジェクトで再実装したくない（詳細は [ADR-0007](../02_基本設計/ADR/0007_llm-extraction-qwen-adoption.md)）
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
│   │   └── novel.db                 # SQLite + FTS5 + sqlite-vec
│   └── kindle_novel/                # 既存（PDF / 画像 / サムネイル）
│       ├── pdfs/                    # ★ 新ビューア動作確認後に削除予定
│       ├── images/                  # 元画像（永続保持）
│       └── thumbnails/              # 既存（流用または削除、後述）
├── routers/
│   ├── novel_db.py                  # 新規（検索 / 質問 / ライブラリ / 再構築）
│   └── ...
└── services/
    └── novel_db/                    # 新規パッケージ
        ├── __init__.py
        ├── schema.py                # SQLite スキーマ DDL
        ├── connection.py            # sqlite3 接続 + sqlite_vec.load()
        ├── extractor.py             # PyMuPDF blocks 抽出
        ├── chunker.py               # 句点境界チャンク（800 字 / overlap 50）
        ├── embedder.py              # Ollama bge-m3 ラッパー
        ├── character_extractor.py   # Ollama gemma4:e4b で主要登場人物を抽出
        ├── contextualizer.py        # gemma4:e4b でチャンクごとの位置説明を生成（B-9）
        ├── search.py                # FTS5 OR + ベクトル検索 + RRF + フィルタ + 主要キャラ JOIN + サマリ vec 検索
        ├── llm.py                   # 共通 Qwen モジュール経由のストリーミング（薄いラッパ）
        ├── builder.py               # 1 冊の DB 構築フロー（再構築含む）
        ├── summarizer.py            # 1 冊の俯瞰サマリ生成（Qwen 1-shot、num_ctx=131072）
        ├── job_queue.py             # 再構築ジョブの全体ロック + キュー
        └── library.py               # 書籍一覧取得・DB 状態問い合わせ

backend/scripts/                     # CLI 用ツール
├── build_novel_db.py                # 全件 / 個別書籍を CLI から再構築
├── extract_characters.py            # 主要登場人物の一括抽出
├── build_novel_summaries.py         # 書籍ごとの俯瞰サマリの一括生成（B-5）
└── build_chunk_contexts.py          # チャンク位置説明の一括生成 + 再 embedding（B-9）
```

---

## 4. データモデル（SQLite スキーマ）

`services/novel_db/schema.py` に DDL を集約。マイグレーションは PoC では「破棄して再構築」で十分（履歴を保持したい場合は将来 alembic 等を導入）。

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

-- 書籍サマリの embedding（B-8、bge-m3 1024 次元）
-- rowid = books.id。scope=all / scope=series の retrieval で「サマリ自体が
-- ヒット候補」になるよう、書籍 1 冊あたり 1 ベクトルを格納する。summarizer の
-- update_book_summary() が summary 保存時に upsert する。
CREATE VIRTUAL TABLE book_summaries_vec USING vec0(embedding FLOAT[1024]);

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

-- ベクトル（chunks.id とリンク）
-- B-9 適用後の embedding は (contextual_text + text) で再計算済。contextual_text
-- が NULL のチャンクは text のみで embedding（後方互換）
CREATE VIRTUAL TABLE chunks_vec USING vec0(embedding FLOAT[1024]);

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
    error_message   TEXT
);
CREATE INDEX idx_rebuild_jobs_state ON rebuild_jobs(state, enqueued_at);
```

### 4.1. シリーズ ID の扱い

- `qa_history.scope_id` には文字列で series_id を保存
- series_id の実体は既存の `data/meta/novel/meta.json` の series 情報（既存 `services/series_detector.py` が生成）に従う
- novel.db 内には series テーブルを作らず、参照のたびに meta.json から取得（書籍数 11 冊規模では速度問題なし）

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
            └─→ chunks / chunks_vec テーブルに INSERT
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

### 5.2. チャンク分割（`chunker.py`）

- ページの全文長 ≤ 800 字 → 1 チャンク
- 800 字超 → 句点境界（`。」!?`）優先で分割、50 字オーバーラップ
- PoC スクリプト（旧 `tmp_poc/chunker.py`）を本実装に昇格

### 5.3. embedding（`embedder.py`）

- Ollama API (`POST /api/embed`) を urllib で叩く
- モデル: `bge-m3`（1024 次元）
- バッチサイズ: 16
- タイムアウト: 180 秒
- リトライ: 1 回（接続失敗時）

PoC スクリプトベースで、エラーハンドリング・ログ出力を追加して本実装。

### 5.4. ジョブごとの構築フロー（`builder.py`）

```python
def rebuild_book(conn, book_name: str) -> None:
    """1 冊を再構築する（既存レコードは削除して上書き）。"""
    pdf_path = NOVEL_PDF_DIR / f"{book_name}.pdf"
    images_dir = NOVEL_IMAGES_DIR / book_name
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    # 既存レコード削除（CASCADE で pages / chunks / chunks_vec も連動）
    # ⚠️ pages.main_characters / chunks.contextual_text / books.summary / books.summary_generated_at /
    #    book_summaries_vec の該当行も道連れに消える。再構築後に extract_characters /
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
            conn.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                (cur.lastrowid, serialize_f32(emb)),
            )
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

実機検証で `num_ctx=131072` が **VRAM 12GB（RTX 5070）+ システム RAM 32GB の環境**で OOM なく動作することを確認（[小説RAG_技術知見.md §0 ハードウェア前提](../05_記録/小説RAG_技術知見.md)）。モデル本体（Q4_K_M、27GB）は VRAM に乗り切らず Ollama が約 61% を CPU 側にオフロードしているため、num_ctx 拡大による KV cache 増加も主にシステム RAM 側で吸収される。1 冊あたり 1.6 chars/token 換算で 113k 字 = ~71k tokens のため、131k ctx に余裕で収まる。

**スキーマ**: `books.summary TEXT`（NULL = 未生成）/ `books.summary_generated_at TIMESTAMP`。`update_book_summary()` 内で `book_summaries_vec`（B-8）への upsert も同時に行う。

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
| プロンプト | 書名 + 書籍俯瞰サマリ + チャンク先頭 1200 字 → 80 字程度の位置説明 |
| 出力長 | `num_predict=256`, `num_ctx=8192` |
| 1 チャンク所要 | ~2.8 秒（実機計測） |
| 全件（2,230 チャンク） | 約 100〜110 分 |

**スキーマ**: `chunks.contextual_text TEXT`（NULL = 未生成）/ `chunks.contextual_generated_at TIMESTAMP`。

**embedding 再構築**: 生成完了後、`(contextual_text + "\n\n" + chunk_text)` を bge-m3 でバッチ 16 で embedding し、`chunks_vec` を DELETE → INSERT で更新する（`make_embedding_input` ヘルパ）。

**生成タイミング**: 別 CLI（[§5.9](#59-cli) の `build_chunk_contexts.py`）でユーザーが任意のタイミングで実行する。B-5 のサマリが前提（プロンプトのコンテキストに使う）。

**フォールバック**:
- `book.summary IS NULL` の書籍はスキップ（コンテキスト無しでは位置説明が薄くなるため）
- LLM 接続エラーや空応答時は `contextual_text` を NULL のまま続行 → そのチャンクの embedding は text のみで計算（後方互換）
- 重量モデルにフォールバックしたい場合は `NOVEL_DB_CONTEXT_MODEL=qwen3.6:35b-a3b` 等で切替

**実機検証**: 書籍 1 巻（202 チャンク）のパイロットで以下を確認:
- avg 63 字 / min 29 字 / max 88 字 の位置説明が生成される
- サンプル 5 件すべて本文の内容と整合
- 「父王が次期女王を発表する場面」→ p11 が distance 最良で top 1 に来る retrieval 結果

### 5.9. CLI

| スクリプト | 用途 |
|---|---|
| `backend/scripts/build_novel_db.py` | 全件 / 個別書籍の DB 再構築（PDF テキスト抽出 + チャンク + embedding）|
| `backend/scripts/extract_characters.py` | 主要登場人物の一括抽出（`pages.main_characters` を埋める）|
| `backend/scripts/build_novel_summaries.py` | 書籍俯瞰サマリの一括生成（`books.summary` を埋める）|
| `backend/scripts/build_chunk_contexts.py` | チャンク位置説明の一括生成 + 再 embedding（`chunks.contextual_text` を埋め、`chunks_vec` を更新）|

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
```

`build_novel_db.py` は内部的に `services/novel_db/job_queue.py` を経由（同時実行禁止）。
`extract_characters.py` / `build_novel_summaries.py` / `build_chunk_contexts.py` はジョブキューを使わず逐次実行（再構築と並行しない前提）。

**処理順序の推奨**: `build_novel_db` → `extract_characters` → `build_novel_summaries` → `build_chunk_contexts`。`build_chunk_contexts` は `book.summary` を要求するため、サマリ生成より後に実行する必要がある。

---

## 6. 検索（`search.py`）

### 6.1. ハイブリッド検索（FTS5 OR + ベクトル + RRF）

PoC スクリプト（旧 `tmp_poc/search.py`）の `hybrid_search()` を本実装に昇格。

**ベクトル embedding の構成（B-9 適用後）**: `chunks_vec.embedding` は `(contextual_text + "\n\n" + chunk_text)` を bge-m3 で計算した値。`contextual_text` が NULL の chunk は `chunk_text` のみで計算する（後方互換）。これにより「該当ページに直接の語彙的一致がない抽象的なクエリ」でも、位置説明込みの semantic 距離で top に来るようになる。

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
            # series_id は meta.json 参照で book_name のリストに展開
            ...
```

シリーズスコープでは `meta.json` から該当 series_id の書籍リストを取得し、`b.name IN (...)` で SQL に展開する。

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
    """`book_summaries_vec` に対する vec0 ベクトル検索。
    Returns: [(book_name, distance), ...]（distance 昇順）
    """
```

**動作確認**: 「メルディの軍師としての活躍」→ 「10 二人の軍師」が distance 0.97 で 1 位（タイトル通り軍師がテーマの巻が圧勝）、「1 巻」が 1.18 で 2 位、と意味的に妥当な順位を返すことを実機確認。

**フォールバック**: `book_summaries_vec` が無い古い DB（B-8 マイグレーション前）では空リストを返し、page 単位の hit-book-summaries だけが prompt に乗る（後方互換）。

### 6.6. 検索フィルタ（2026-05-10 追加）

`hybrid_search()` には章扉・目次・人物紹介・あとがき等の **薄いページや書誌付録** をノイズとして除外するためのフィルタを 3 つ持たせる。デフォルト値は `backend/config.py` で集中管理する。

| パラメータ | デフォルト | 役割 |
|---|---|---|
| `min_chars` | `NOVEL_DB_MIN_BODY_CHARS = 300` | `pages.char_count` がこの値未満のページを除外。章扉・目次・人物紹介の薄い 1 ページを弾く |
| `body_page_margin` | `NOVEL_DB_BODY_PAGE_MARGIN = 5` | 各書籍の **先頭・末尾 N ページ** を除外。表紙・口絵・あとがき・解説・奥付を弾く |
| `max_per_book` | `NOVEL_DB_QA_MAX_PER_BOOK = 2` | 1 書籍あたりの取得上限。`scope=all` / `scope=series` で特定書籍に偏らないよう均等化 |

`top_k` のデフォルトも引き上げた（`NOVEL_DB_QA_TOP_K = 32`、B-13 段階 A で 2026-05-11 に 16 → 32 に拡大）。フィルタで弾かれた分を見越して多めに取り、`max_per_book` で書籍を分散させる方針。`max_per_book = 2` のままで `top_k = 32` を満たすには 16 冊以上の書籍が必要なので、現状 11 冊では `max_per_book` を超える前に書籍数で上限に達する（実際の取得件数は最大でも 22 件程度）。

**フィルタの効き方の注意**:
- `min_chars` を厳しくしすぎると挿絵が多い章でヒットを取り逃す。300 字は経験値（PoC で「短すぎる」と感じた境界）
- `body_page_margin=5` は標準的な軽小説の付録厚みに合わせた値。前付け / 後付けが薄い書籍では誤って本編序盤・終盤を削る可能性がある。実害が出たら値を見直す
- `max_per_book` は `scope=book` のときは効かない（同一書籍内で `top_k` 件取得する設計）

---

## 7. 質問応答（`llm.py`）

### 7.1. Qwen SSE ストリーミング（共通モジュール経由）

- LLM クライアントは `D:\61.tool\common\Qwen\lib\qwen_client.py` の `astream_ask()` を直接呼ぶ
- `llm.py` 自体は薄いラッパで、Pic2PDF 固有の `LLM_OPTIONS` を渡しつつイベントを yield する
- 共通モジュール側で **Qwen3.x の thinking モデル必須要件**（`stream=True` / `think=False` を毎回送る、`num_predict` を thinking で食い潰されない値にする）を担保している
- レスポンスは NDJSON。各行を `event: token` / `data: {...}` 形式の SSE に変換してフロントへ流す
- 完了後（`done: true` 受信時）に履歴を保存

```python
# services/novel_db/llm.py（抜粋）
import os, sys
os.environ.setdefault("QWEN_OLLAMA_BASE_URL", NOVEL_DB_OLLAMA_BASE_URL)
sys.path.insert(0, r"D:\61.tool\common\Qwen\lib")
from qwen_client import astream_ask as _astream_ask

async def stream_qa(prompt, *, model=NOVEL_DB_LLM_MODEL, options=None, timeout=600.0):
    async for event in _astream_ask(prompt, model=model, options=options or LLM_OPTIONS, timeout=timeout):
        yield event
```

なぜ共通モジュールに切り出したかは [ADR-0007](../02_基本設計/ADR/0007_llm-extraction-qwen-adoption.md) を参照。

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
    "num_ctx": NOVEL_DB_QA_NUM_CTX,  # config 化、既定 16384（B-13 段階 A、2026-05-11）
}
```

`num_predict=4096` は Qwen 系で `done_reason='stop'` で完走するのに十分な値（共通モジュールのデフォルト 8192 を `LLM_OPTIONS` で上書き）。

**`num_ctx` は `NOVEL_DB_QA_NUM_CTX`（既定 16384）で config 化**（B-13 段階 A、2026-05-11）。従来 8192 では:
- `top_k=32` のページ抜粋（~12k 字）+ 全 11 冊サマリ（~11k 字）+ システムプロンプト + 質問 ≒ **~25k 字 / ~15k tokens** に達し、`num_ctx=8192` では切り詰めが発生していた可能性
- 16384 に拡大して切り詰めリスクを解消、応答時間は +20〜30% を許容

後続の段階 B / C（`num_ctx=32768` / `131072` 等）は機能追加候補 B-13 を参照。`NOVEL_DB_QA_NUM_CTX` 環境変数で切替可能。

### 7.4. SSE エンドポイント

```python
@router.post("/qa")
async def qa_endpoint(req: QaRequest) -> StreamingResponse:
    """ハイブリッド検索 → Qwen ストリーミング → 履歴保存"""
    rows = hybrid_search(
        conn, req.question, scope=req.scope,
        top=NOVEL_DB_QA_TOP_K,
        min_chars=NOVEL_DB_MIN_BODY_CHARS,
        body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
        max_per_book=NOVEL_DB_QA_MAX_PER_BOOK,
    )
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

### 7.5. 連投警告

連投警告（直前と完全一致）はフロントエンド側のチェックで行い、バックエンド側ではチェックしない。フロントから常に送ってもよい設計（API はステートレス）。

### 7.6. 質問の停止（クライアント切断）

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

## 8. 再構築ジョブ（`job_queue.py`）

### 8.1. 全体ロック + ジョブキュー

- `services/novel_db/job_queue.py` に `NovelDbJobQueue` クラス
- バックエンド起動時に `main.py` の lifespan で起動・停止
- 単一の worker スレッドで `rebuild_jobs` テーブルを polling し、`state='queued'` のジョブを古い順に実行

```python
class NovelDbJobQueue:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self.is_running: bool = False  # 検索 / 質問 API がチェック

    def start(self) -> None:
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        self._wakeup.set()
        if self._worker:
            self._worker.join(timeout=10)

    def enqueue(self, job_type: str, target_id: str | None = None) -> int:
        """ジョブを rebuild_jobs に INSERT し、worker を起こす。job_id を返す。"""
        with sqlite_conn() as conn:
            cur = conn.execute(
                "INSERT INTO rebuild_jobs (job_type, target_id) VALUES (?, ?)",
                (job_type, target_id),
            )
            conn.commit()
            job_id = cur.lastrowid
        self._wakeup.set()
        return job_id

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wakeup.wait(timeout=5)
            self._wakeup.clear()
            self._drain_queue()

    def _drain_queue(self) -> None:
        while True:
            with self._lock:
                with sqlite_conn() as conn:
                    row = conn.execute(
                        "SELECT id, job_type, target_id FROM rebuild_jobs "
                        "WHERE state='queued' ORDER BY enqueued_at LIMIT 1"
                    ).fetchone()
                    if not row:
                        return
                    conn.execute(
                        "UPDATE rebuild_jobs SET state='running', started_at=datetime('now') "
                        "WHERE id=?",
                        (row[0],),
                    )
                    conn.commit()
                self.is_running = True
            try:
                self._execute_job(row)
                self._mark_completed(row[0])
            except Exception as e:
                self._mark_failed(row[0], str(e))
            finally:
                self.is_running = False
```

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

`routers/novel_db.py` の検索 / 質問エンドポイントの先頭で呼び出す。

### 8.3. ジョブ進捗表示

`rebuild_jobs.progress_total` / `progress_done` を builder 側から逐次更新。フロントは `GET /api/novel_db/rebuild/status` でポーリング（5 秒間隔）。

### 8.4. ジョブのキャンセル仕様

- **`state='queued'`（待機中）のジョブのみキャンセル可能**: `DELETE /api/novel_db/rebuild/{job_id}` で `state='canceled'` に更新
- **`state='running'`（実行中）のジョブはキャンセル不可**: 実行途中で中断すると embedding バッチの整合性が崩れるリスクと実装複雑化が利得を上回る。実行中の DELETE は **409 Conflict** を返す
- 待機中ジョブの一括キャンセル（例: 「キューを全部空に」）は当面非対応。必要になったら別エンドポイントで追加

---

## 9. ライブラリ表示（`library.py`）

### 9.1. 書籍一覧

```python
def list_books() -> list[BookSummary]:
    """既存の data/kindle_novel/pdfs/ + meta.json から書籍リストを構築し、
    novel.db の DB 状態（is_indexed / page_count / indexed_at）を結合して返す。"""
    pdf_files = list(NOVEL_PDF_DIR.glob("*.pdf"))
    meta = load_meta_json("novel")  # 既存 meta_store の流用
    indexed_books = {b.name: b for b in load_indexed_books_from_db()}

    summaries = []
    for pdf in pdf_files:
        name = pdf.stem
        info = indexed_books.get(name)
        summaries.append(BookSummary(
            name=name,
            authors=meta.get(name, {}).get("authors", []),
            series_id=meta.get(name, {}).get("series_id"),
            is_indexed=info is not None,
            page_count=info.page_count if info else None,
            indexed_at=info.indexed_at if info else None,
        ))
    return summaries
```

### 9.2. シリーズ一覧

既存 `series.router` のエンドポイント（or 既存 service）を流用。novel ソース限定でフィルタする。

「シリーズ未所属」の書籍はシリーズスコープの選択肢から除外（[要件定義 TBD-7](../01_要件定義/小説テキスト検索・RAG機能.md)）。

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

詳細な JSON スキーマは [API仕様書.md](API仕様書.md) §X に追加（後続）。

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

### 11.2. meta.json / シリーズ機能

- `data/meta/novel/meta.json` はそのまま残す（authors / hidden / read_state / series_id）
- 既存 `services/series_detector.py` / `services/meta_store.py` を novel_db でも参照
- novel_db.py は meta.json には書き込まない（read-only 参照）

### 11.3. 既存 `routers/library.py` との棲み分け

- 既存 `library.py` は **PDF 一覧表示** が主目的（main / kindle / generated / novel）
- 新規 `novel_db.py` は **novel ソース限定** の検索・質問・DB 構築
- novel タブのフロントは novel_db.py のエンドポイントのみを使う

---

## 12. テスト方針

`backend/tests/` に追加。既存パターンを踏襲（[詳細設計書_バックエンド編 §5](詳細設計書_バックエンド編.md)）。

| ファイル | 対象 |
|---|---|
| `test_novel_db_extractor.py` | PyMuPDF blocks 抽出、改行除去、空ページ |
| `test_novel_db_chunker.py` | 句点境界分割、800 字超分割、オーバーラップ |
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
- 既存 `data/meta/novel/meta.json` の `pdf_path` フィールド等が PDF 前提なら整理

### 永続資産（削除しない）
- `backend/data/kindle_novel/images/{書籍名}/*.png`: 画像表示・再 OCR 用途
- `kindle-pdf/main_novel.py`: novel 画像取り込みツール

---

## 14. 既知の制限・将来検討

- **OCR ミスは `bge-m3` の意味距離で吸収** しているが、完全ではない（PoC で「薔→蕎」は救えたが、より多い誤認識ページがあれば回答品質が下がる）。**頻出ミスの辞書置換は導入せず**、問題が見つかったら **その書籍の元画像から yomitoku で再 OCR して書籍単位で DB を再構築する** 方針 → 将来機能として追加（後述）
- **Qwen3.6:35b-a3b の応答時間 80〜130 秒** は変えられない。UI でストリーミング表示してユーザー体感を緩和。Gemma 4:26b 時代（30〜100 秒）より長くなったが、概括的な質問への踏み込みが大幅に改善されたため受容（[ADR-0007](../02_基本設計/ADR/0007_llm-extraction-qwen-adoption.md)）
- **キャラ帰属誤統合（残存課題）**: `main_characters` ヒント付与で誤統合率を下げたが、ゼロにはできていない（PoC 計測で ~18%）。完全防止には RAG ではなく書籍ごとの fine-tuning が必要で、ローカル小説向け個人ツールとしてはコスト超過。許容範囲として運用
- **シリーズ未所属書籍のグルーピング表示**: 全件スコープのライブラリ画面で「未所属」セクションを設けるかは [要件定義 §10 TBD-7](../01_要件定義/小説テキスト検索・RAG機能.md) の通り、シリーズスコープからは除外（全件・単冊では含む）
- **複数モデル対応**: 質問応答は `qwen3.6-iq4xs`（Qwen3.6:35b-a3b の IQ4_XS 量子化、B-12 で 2026-05-11 採用）、主要登場人物抽出 / コンテキスト生成は `gemma4:e4b`。`backend/config.py` の `NOVEL_DB_LLM_MODEL` / `NOVEL_DB_CHAR_EXTRACT_MODEL` / `NOVEL_DB_CONTEXT_MODEL` で切替可。ロールバックは環境変数 `NOVEL_DB_LLM_MODEL=qwen3.6:35b-a3b` で即時可能（旧モデルは保険として残置）。将来 UI からのモデル切替は要件定義 §9 「将来検討事項」を参照
- **俯瞰質問の天井（B-5 / B-8 / B-9 で 3 段の対応済み）**: `scope=all` / `scope=series` での「シリーズ全体のテーマ」のような概括質問は、ハイブリッド検索が拾える `top_k=16` 件のページ抜粋に依存するため、全 11 冊・1359 ページを俯瞰しきれない構造だった。3 段の改善を順次適用:
    - **B-5（2026-05-10）**: `books.summary` を Qwen 1-shot で事前生成し、QA プロンプトの先頭に「書籍俯瞰サマリ」ブロックとして埋め込む（§5.7 / §7.2）
    - **B-8（2026-05-10）**: `book_summaries_vec` にサマリの bge-m3 ベクトルを格納し、`scope=all` / `scope=series` で `search_book_summaries` でサマリ自体を retrieval 候補に。ページに引っかからなかった書籍も俯瞰サマリで Qwen に伝わる（§6.5）
    - **B-9（2026-05-11）**: Anthropic 流の Contextual Retrieval。各チャンクに 80 字の位置説明を gemma4:e4b で生成し、`(contextual_text + chunk_text)` を再 embedding。検索 recall を 35〜49% 改善（§5.8）
- **書籍単位の再 OCR 機能（将来）**: 検索結果や質問回答を見て「この書籍の OCR が壊れている」と気づいた際に、UI から「この本を再 OCR」ボタンで **元画像 (`data/kindle_novel/images/{書籍名}/*.png`) を yomitoku に流して新しい OCR テキストを得る → その書籍の DB レコード（pages / chunks / chunks_vec）を丸ごと作り直す** 機能。
  - 実装方針: `services/novel_db/builder.py` に `mode` 引数を追加し、`mode='pdf_text'`（現行: PDF テキスト層から抽出、数分）と `mode='reocr'`（画像から yomitoku で再 OCR、GPU 必須・数十分）を切替できるようにする
  - スキーマ変更: `rebuild_jobs.mode` カラムを追加（`'pdf_text' | 'reocr'`、デフォルト `'pdf_text'`）
  - API 拡張: `POST /api/novel_db/rebuild` のリクエストに `mode` フィールドを追加
  - UI: ライブラリ画面の各書籍に「再構築」ボタンと並んで「再 OCR」ボタンを置く（実行確認ダイアログで GPU 使用と所要時間を警告）
  - 本フェーズでは未実装、要件定義 §9 に記載のとおり別途実装予定

---

## 15. 関連ドキュメント

- 要件定義: [docs/01_要件定義/小説テキスト検索・RAG機能.md](../01_要件定義/小説テキスト検索・RAG機能.md)
- 既存 OCR 設計: [docs/03_詳細設計/OCR設計書.md](OCR設計書.md)
- 既存 backend 全体: [詳細設計書_バックエンド編.md](詳細設計書_バックエンド編.md)
- API 仕様書（後続追加）: [API仕様書.md](API仕様書.md)
- フロントエンド設計（後続作成）: [小説テキスト検索・RAG機能_フロントエンド設計.md](小説テキスト検索・RAG機能_フロントエンド設計.md)
- ADR: [ADR-0007 LLM 抽出と Qwen 採用](../02_基本設計/ADR/0007_llm-extraction-qwen-adoption.md)
- **運用知見の蓄積（実機ベンチマーク・モデル選定指針・トラブルシューティング）**: [docs/05_記録/小説RAG_技術知見.md](../05_記録/小説RAG_技術知見.md)
- PoC スクリプト（旧 `tmp_poc/`）: 実装完了後に削除済み。実装は `backend/services/novel_db/` 配下に集約
