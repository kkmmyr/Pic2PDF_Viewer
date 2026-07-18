# 小説 RAG データ設計（スキーマ・環境変数・API・レイアウト）

> status: living | last-verified: 2026-07-03

小説 RAG（novel_db）サブシステムの横断的な事実の正本。DB スキーマ / 環境変数 / ディレクトリレイアウト / API エンドポイント一覧 / LLM backend・port を 1 箇所に集約する。個別処理の設計は パイプライン設計（`小説RAG_パイプライン設計.md`）・検索QA設計（`小説RAG_検索QA設計.md`）を参照（※これら2文書は同 G4 で作成予定。作成後にリンク化する）。

本書は「現在の事実」だけを記載する。モデル選定の経緯・ベンチマークは `docs/log/技術知見/小説RAG_技術知見.md` を参照。

---

## 1. DB スキーマ

小説 RAG は **2 つのストア** を併用する。

- **SQLite**（`novel.db`）— 本文・チャンク・QA 履歴・キャラ辞典等のリレーショナルデータ。**スキーマの唯一の真実の源は Alembic**（`backend/alembic/versions/`）。起動時に `services/novel_db/migrations.py::upgrade_head()`（`main.py` から呼び出し）が `alembic upgrade head` を実行して最新 revision に追従する。
- **LanceDB**（`novel.lancedb`）— bge-m3 の埋め込みベクトル（ANN 検索用）。スキーマは `services/novel_db/lance_store.py` の PyArrow スキーマが定義。

`services/novel_db/models.py` に SQLModel 定義があるが、これは `alembic revision --autogenerate` の差分検出用であり、実行時クエリの多くは生 `sqlite3`（`connection.py`）で行われる。

### 1.1 SQLite テーブル（`novel.db`）

現行 head は revision `0003`。全 10 テーブル（通常 9 + FTS5 仮想 1）。カラム詳細・インデックス・制約は Alembic revision を参照。

| テーブル | 用途 | 主なカラム | 定義元 |
|---|---|---|---|
| `books` | 書籍メタ（1 冊 = 1 PDF） | `name`(UNIQUE), `pdf_path`, `images_dir`, `page_count`, `indexed_at`, `summary`, `summary_generated_at`, `ocr_done_at` | 0003 |
| `pages` | ページ単位の本文 | `book_id`(FK), `page_no`, `image_path`, `full_text`, `char_count`, `main_characters`; UNIQUE(book_id, page_no) | 0003 |
| `pages_fts` | `pages.full_text` の全文検索（FTS5, `tokenize='trigram'`, `content='pages'`） | `full_text` | 0003 |
| `chunks` | 埋め込み単位のチャンク | `page_id`(FK), `chunk_idx`, `text`, `char_count`, `contextual_text`, `contextual_generated_at`(B-9 Contextual Retrieval) | 0003 |
| `qa_history` | 単発 QA の実行ログ | `scope_type`, `scope_id`, `question`, `answer`, `prompt`, `context_json`, `model`, `options_json`, `eval_count`, `done_reason`, `error_message` | 0003 |
| `book_characters` | キャラ辞典（書籍 × キャラ, B-15） | `book_id`(FK), `name`, `summary`, `first_page`, `page_count`, `generated_at`; UNIQUE(book_id, name) | 0003 |
| `qa_sessions` | マルチターン QA のセッション | `scope_type`, `scope_id`, `title`, `started_at`, `last_message_at` | 0003 |
| `qa_messages` | セッション内のメッセージ | `session_id`(FK), `role`, `content`, `eval_count`, `done_reason`, `created_at` | 0003 |
| `rebuild_jobs` | 再構築ジョブキュー | `job_type`, `target_id`, `mode`, `state`, `enqueued_at`, `started_at`, `finished_at`, `progress_total`, `progress_done`, `error_message`, `current_step`, `current_detail` | 0003 |
| `character_relations` | キャラ関係グラフ（C-12） | `series_id`, `book_id`, `char_a`, `char_b`, `relation_type`, `weight`, `generated_at` | 0002 |

補足:
- `character_relations` は **SQLModel 定義を持たない**（`models.py` に無し）。migration 0002 の生 DDL でのみ定義され、`relation_extractor.py`（書込）/ `graph_query.py`（照会）が生 SQL で扱う。
- `created_at` 等のタイムスタンプは JST 固定（`datetime('now', '+9 hours')`）。
- FK は `PRAGMA foreign_keys = ON`（`connection.py`）で有効。`journal_mode = WAL`。

### 1.2 LanceDB テーブル（`novel.lancedb`）

`lance_store.py` が 2 テーブルを遅延生成する（埋め込み次元は bge-m3 の **1024** 固定）。

| テーブル | スキーマ | 用途 |
|---|---|---|
| `chunks` | `chunk_id:int64`, `book_name:utf8`, `page_no:int32`, `text:utf8`, `char_count:int32`, `page_count:int32`, `embedding:list<float32>[1024]` | チャンク単位の KNN ベクトル検索 |
| `summaries` | `book_id:int64`, `book_name:utf8`, `embedding:list<float32>[1024]` | 書籍サマリのベクトル（scope=all の書籍選定） |

- `chunks.chunk_id` は SQLite `chunks.id` と対応（LanceDB 側は本文とベクトルのみ保持、リレーショナル情報は SQLite が正）。
- ANN インデックス（IVF_PQ, `num_partitions=256`, `num_sub_vectors=64`）はチャンク数 > **50,000** で `maybe_create_index()` が自動構築する。それ未満はフルスキャン KNN。

---

## 2. 環境変数

### 2.1 env で上書き可能な設定（pydantic-settings）

定義元は **`backend/config/novel_db.py`**（`_NovelDbSettings`, `env_prefix=""`）。ただし `NOVEL_DB_DIR` のみ `backend/config/__init__.py`（`_AppSettings`）で定義。`.env`（プロジェクトルート）が `config/__init__.py` の `load_dotenv()` で読み込まれる。

| 環境変数 | デフォルト | 用途 |
|---|---|---|
| `NOVEL_DB_DIR` | `backend/data/novel_db` | `novel.db`（SQLite）の格納ディレクトリ（`__init__.py` 定義） |
| `NOVEL_DB_LANCE_PATH` | `backend/data/novel.lancedb` | LanceDB ベクトルストアのパス |
| `NOVEL_DB_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama エンドポイント（embedding / Gemma） |
| `NOVEL_DB_EMBED_MODEL` | `bge-m3` | 埋め込みモデル |
| `NOVEL_DB_EMBED_NUM_GPU` | `0` | embedding の GPU レイヤ数（0=CPU、llama-server に VRAM を譲る） |
| `NOVEL_DB_LLM_MODEL` | `qwen3.6-iq4xs` | 重量 LLM（QA / サマリ / 関係抽出） |
| `NOVEL_DB_LLM_BACKEND` | `llama_server` | 重量 LLM の backend（`llama_server` のみサポート。他値は起動時 `LLMError`） |
| `NOVEL_DB_LLAMA_SERVER_URL` | `http://127.0.0.1:11435` | llama-server エンドポイント |
| `NOVEL_DB_CHAR_EXTRACT_MODEL` | `gemma4:12b` | 主要登場人物抽出（短答型） |
| `NOVEL_DB_CONTEXT_MODEL` | `gemma4:12b` | B-9 チャンク文脈生成 |
| `NOVEL_DB_GEMMA_BACKEND` | `ollama` | Gemma 系タスクの backend（`ollama` / `qwen`=QWEN backend 流用） |
| `NOVEL_DB_QA_TOP_K` | `64` | RAG QA で LLM に渡すチャンク数（B-13 段階 B） |
| `NOVEL_DB_QA_NUM_CTX` | `32768` | QA 時の num_ctx（llama-server は `-c 36864` 起動が前提） |
| `NOVEL_DB_QA_EXPAND_ENABLED` | `True` | B-11 Query Expansion の有効化 |
| `NOVEL_DB_QA_EXPAND_N` | `3` | クエリ拡張の生成数 |
| `NOVEL_DB_QA_EXPAND_MODEL` | `gemma4:12b` | クエリ拡張モデル |
| `NOVEL_DB_QA_FULL_BOOK_MODE` | `True` | B-13 段階 C（scope=book で本文丸ごと読込） |
| `NOVEL_DB_QA_FULL_BOOK_NUM_CTX` | `131072` | full-book モード時の num_ctx |

### 2.2 env 非対応の固定定数

`config/novel_db.py` 末尾でモジュール定数として公開。env では変えられない（コード変更が必要）。

| 定数 | 値 | 用途 |
|---|---|---|
| `NOVEL_DB_EMBED_DIM` | `1024` | bge-m3 の出力次元 |
| `NOVEL_DB_MIN_BODY_CHARS` | `300` | 薄いページ除外の文字数閾値 |
| `NOVEL_DB_QA_MAX_PER_BOOK` | `5` | 1 書籍あたりの取得上限 |
| `NOVEL_DB_BODY_PAGE_MARGIN` | `5` | 先頭/末尾の除外ページ数 |
| `NOVEL_DB_QA_TOP_SUMMARIES` | `11` | scope=all で使う書籍サマリ上限 |

---

## 3. ディレクトリレイアウト

### 3.1 サービス層 `backend/services/novel_db/`

RAG のコアロジック。主なモジュール:

- **接続 / スキーマ**: `connection.py`（sqlite3 接続）, `migrations.py`（Alembic 実行）, `models.py`（SQLModel）, `lance_store.py`（LanceDB）
- **構築パイプライン**: `builder.py`, `full_builder.py`, `extractor.py`, `ocr_worker.py`, `chunker.py`, `embedder.py`, `contextualizer.py`
- **ジョブ**: `job_queue.py`, `job_worker.py`
- **検索 / QA**: `search_scope.py`, `search.py`, `book_summary_search.py`, `retrieval.py`, `prompt_builder.py`, `query_expander.py`, `llm.py`, `qa_history.py`, `qa_sessions.py`, `discussion_service.py`
- **サマリ / キャラ**: `summarizer.py`, `character_extractor.py`, `character_summarizer.py`, `character_db.py`, `extractor.py`, `relation_extractor.py`, `graph_query.py`
- **LLM 配線**: `_llm_backend.py`（backend シングルトン）, `_prompts.py`, `_prompts` 系プロンプト, `library.py`

### 3.2 ルーター層 `backend/routers/novel_db/`

`__init__.py` が 6 サブルーターを `/novel_db` プレフィックスで結合。router ファイルは 8 個（うち 6 個がエンドポイント提供、2 個が支援モジュール）:

- エンドポイント: `character.py`, `chat.py`, `lib.py`, `qa.py`, `rebuild.py`, `search.py`
- 支援: `_deps.py`（共通依存: `require_not_locked` / `log_and_raise_500` / `sse_event` 等）, `schemas.py`（Pydantic 入出力スキーマ）

登録順は `character → lib → rebuild → search → qa → chat`（`/books/{name:path}/characters` を lib の `/books/{name:path}` に飲み込ませないため character を先に登録）。

### 3.3 CLI スクリプト `backend/scripts/`

いずれも `cd backend && uv run python scripts/xxx.py` で実行。冒頭で `upgrade_head()` を呼ぶ。

| スクリプト | 役割 |
|---|---|
| `build_novel_db.py` | OCR → チャンク → embedding の本構築（`--book` / `--all` / `--list`） |
| `build_chunk_contexts.py` | B-9 Contextual Retrieval のチャンク文脈生成 + 再 embedding |
| `build_novel_summaries.py` | 書籍サマリ（あらすじ）を map-reduce で生成 |
| `build_character_summaries.py` | B-15 キャラ辞典の人物像サマリ生成 |

（関連: `extract_characters.py`, `eval_chunk_strategy.py` も同ディレクトリに存在）

### 3.4 データ格納先

- SQLite: `backend/data/novel_db/novel.db`（`NOVEL_DB_DIR`）
- LanceDB: `backend/data/novel.lancedb`（`NOVEL_DB_LANCE_PATH`。※novel.db とは別階層）
- 小説の PDF / 画像 / サムネイル: `backend/data/kindle_novel/{pdfs,images,thumbnails}`（source=`novel` は内部的に `kindle_novel` ディレクトリに対応）

---

## 4. API エンドポイント

全て `/novel_db` プレフィックス。**リクエスト / レスポンススキーマの詳細は `/openapi.json`・Swagger UI（`/docs`）が正**。下表は所在把握用の一覧（全 21 エンドポイント）。

| メソッド | パス | 概要 | router |
|---|---|---|---|
| POST | `/novel_db/search` | ハイブリッド検索（FTS + ベクトル） | search.py |
| GET | `/novel_db/books` | 書籍一覧 | lib.py |
| GET | `/novel_db/series` | シリーズ一覧 | lib.py |
| GET | `/novel_db/authors` | 著者一覧 | lib.py |
| GET | `/novel_db/books/{book_name}/similar` | 類似書籍 | lib.py |
| GET | `/novel_db/books/{book_name:path}` | 書籍詳細 | lib.py |
| GET | `/novel_db/books/{book_name:path}/characters` | キャラ一覧（B-15） | character.py |
| GET | `/novel_db/books/{book_name:path}/characters/{char_name}` | キャラ詳細（サマリ + 主要シーン） | character.py |
| POST | `/novel_db/builds` | 再構築ジョブ投入 | rebuild.py |
| GET | `/novel_db/builds/status` | ジョブ状態取得 | rebuild.py |
| DELETE | `/novel_db/builds/{job_id}` | ジョブ取消 | rebuild.py |
| POST | `/novel_db/qa` | 単発 RAG QA（SSE ストリーム） | qa.py |
| GET | `/novel_db/qa/history` | QA 履歴一覧 | qa.py |
| GET | `/novel_db/qa/history/{history_id}` | QA 履歴詳細 | qa.py |
| DELETE | `/novel_db/qa/history/{history_id}` | QA 履歴削除 | qa.py |
| GET | `/novel_db/sessions` | チャットセッション一覧 | chat.py |
| GET | `/novel_db/sessions/{session_id}` | セッション詳細 | chat.py |
| POST | `/novel_db/sessions` | セッション作成 | chat.py |
| DELETE | `/novel_db/sessions/{session_id}` | セッション削除 | chat.py |
| POST | `/novel_db/sessions/{session_id}/messages` | メッセージ送信（マルチターン QA, SSE） | chat.py |
| PATCH | `/novel_db/sessions/{session_id}/title` | セッションタイトル変更 | chat.py |

キャラ関係グラフ（`character_relations`）を返す専用エンドポイントは**現状無い**（`graph_query.py` は内部ロジックからのみ利用）。

---

## 5. LLM バックエンド

### 5.1 プロセス / ポート

| プロセス | URL / ポート | 提供モデル | 用途 |
|---|---|---|---|
| Ollama | `http://localhost:11434` | bge-m3, gemma4:12b | embedding / Gemma 系タスク |
| llama-server | `http://127.0.0.1:11435` | qwen3.6-iq4xs（Qwen3.6 35B-A3B iq4xs） | 重量 LLM（QA / サマリ / 関係抽出） |

共通 LLM モジュール `local_llm`（`D:\61.tool\common\llm`）の `OllamaBackend` / `LlamaServerBackend` を使用。

### 5.2 backend シングルトン（`services/novel_db/_llm_backend.py`）

各サービスは backend を個別構築せず、ここから import する。

| シングルトン | 実体 | モデル | 主な利用先 |
|---|---|---|---|
| `QWEN_BACKEND` | `LlamaServerBackend`（11435） | `NOVEL_DB_LLM_MODEL`（qwen3.6-iq4xs） | QA / 書籍サマリ / キャラサマリ / 関係グラフ |
| `GEMMA_BACKEND` | `OllamaBackend`（11434, timeout 120） | `NOVEL_DB_CHAR_EXTRACT_MODEL`（gemma4:12b） | キャラ抽出 / チャンク文脈生成。`NOVEL_DB_GEMMA_BACKEND=qwen` 時は `QWEN_BACKEND` を流用 |
| `QUERY_BACKEND` | `OllamaBackend`（11434, timeout 60） | `NOVEL_DB_QA_EXPAND_MODEL`（gemma4:12b） | B-11 Query Expansion 専用 |

補足:
- `NOVEL_DB_LLM_BACKEND` が `llama_server` 以外だと起動時に `LLMError` で即失敗（Ollama 分岐は Phase C で撤去済み）。
- embedding（bge-m3）は既定で CPU 推論（`NOVEL_DB_EMBED_NUM_GPU=0`）。llama-server の Qwen に VRAM を譲るため。GPU に戻すには `NOVEL_DB_EMBED_NUM_GPU=99` を設定して uvicorn を再起動。
- QA の num_ctx は `NOVEL_DB_QA_NUM_CTX=32768`（full-book モードは `131072`）。llama-server は `-c 36864` 以上で起動している前提。
