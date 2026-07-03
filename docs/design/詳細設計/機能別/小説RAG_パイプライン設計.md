# 小説 RAG 構築パイプライン設計

> status: living | last-verified: 2026-07-03

novel タブの本文を検索・QA 可能にするための **DB 構築パイプライン**（OCR 取込 → チャンク分割 → embedding → 文脈生成 → キャラ抽出 → 書籍サマリ）の現在形設計。検索・QA 側は [検索QA設計](小説RAG_検索QA設計.md) を参照。

**スキーマ・環境変数・ディレクトリレイアウト・API 一覧・LLM backend / port は [データ設計](小説RAG_データ.md) が正本**。本書は重複記載せず、各ステップの入出力・skip 条件・統合フローに集中する。設計の経緯（三段改善史・チャンク実験・PDF 経路撤去）は [設計過程（凍結）](../../../archive/小説RAG_設計過程.md)、実機ベンチ・モデル選定は [技術知見](../../../log/技術知見/小説RAG_技術知見.md)。

すべて `backend/services/novel_db/` 配下。CLI は `backend/scripts/`。

---

## 1. パイプライン全体像

書籍 1 冊は「OCR → チャンク/embedding → サマリ+キャラ辞典 → チャンク文脈 →（キャラ関係）」の順で構築される。各ステップは**独立したジョブ**として実行でき、途中失敗からの再開・部分再構築が効く。UI の各ボタン / CLI が `rebuild_jobs` にジョブを投入し、単一 worker が直列実行する（§7）。

```
images/*.png ──[ocr]──────────► pages.full_text (+ pages_fts)         … builder.ocr_book
      │                              │
      │                              ▼
      │           [rebuild]  chunks + LanceDB chunks(embedding)        … builder.rebuild_from_pages
      │                              │
      │        [full_build] ────────┤ books.summary + book_characters  … full_builder（Qwen 1 回で一括）
      │                              │
      │  [generate_contexts] ───────┤ chunks.contextual_text + 再embed  … full_builder.build_book_contexts
      │                              │
      └──[extract_characters CLI]──► pages.main_characters              … character_extractor
                                     │
             [generate_relations] ──► character_relations (C-12)        … relation_extractor
```

各ジョブが対象とする「未処理書籍」の判定条件は §7 の `_resolve_targets` を参照。

---

## 2. ステップ 1: OCR 取込（`builder.ocr_book` / `extractor` / `ocr_worker`）

`images/{書籍名}/NNN.png` を yomitoku で OCR し、`pages` テーブルへ書き込む。

- **subprocess 分離**: yomitoku は `common/ocr/venv` の GPU パッケージ群に依存するため backend `.venv` に入れない。`extractor.run_ocr_subprocess(images_dirs)` が `ocr_worker.py` を OCR venv の Python で起動し、書籍ごとに 1 行 JSON（`{book_name, pages}` / エラー時 `{book_name, error}`）を stdout から受け取り yield する。yomitoku のモデルロード（~30 秒）は全書籍で 1 回のみ。stderr は backend ログにそのまま流れる。
- **worker 内部**: `ocr_worker._process_book` は `*.png` を stem 昇順に読み、cv2 の非 ASCII パス問題を避けるため `np.fromfile` → `cv2.imdecode` で読み込み、`engine.extract_text` の結果を改行連結して `PageText{page_no, full_text, char_count}` を返す。
- **保存（`_store_ocr_pages`）**: `books` を upsert（`ocr_done_at` を JST 現在時刻に、`page_count` 更新）、`pages` を `ON CONFLICT(book_id, page_no)` で upsert、`pages_fts` を該当書籍分だけ DELETE → 再 INSERT で同期する。
- **PDF モード（後方互換）**: `extractor.extract_pages(pdf)` は PyMuPDF `get_text("blocks")` で縦書きブロックを取得しブロック内改行を除去して連結する。旧 Searchable PDF 由来の書籍向けで、現行の取込は画像 OCR 経路が主。

## 3. ステップ 2: チャンク分割 + embedding（`builder.rebuild_from_pages`）

`pages.full_text` を入力に `chunks`（SQLite）と LanceDB `chunks` テーブルを再構築する。**`pages` は一切変更しない**（OCR 済みの本文を前提）。

- **チャンク分割（`chunker.chunk_page`）**: 全文 ≤ 800 字なら 1 チャンク。超える場合は末尾 100 字以内の句点境界（`。」!?`）優先で切り、50 字オーバーラップ。`char_count < 30` のページ（章扉・ヘッダのみ）はスキップ。
- **embedding（`embedder.embed_batch`）**: Ollama `/api/embed`（httpx）で bge-m3（1024 次元）。builder は 16 件バッチ。`options.num_gpu` に `NOVEL_DB_EMBED_NUM_GPU`（既定 CPU）を渡し llama-server に VRAM を譲る。次元・件数不一致は `EmbeddingError`。
- **保存**: 既存 chunks を LanceDB（`chunk_id IN (...)`）と SQLite の両方から削除 → `chunk_page` の結果を `chunks` に INSERT、embedding を LanceDB に `add`（本文・page_no・char_count・page_count を同梱）。完了時に `books.indexed_at` を更新。progress_callback で `embedding done/total` を通知。
- **クロスページ実験 `chunk_book`**: 全ページ連結 + bisect で page_id 解決する実験実装（1200 字 / overlap 120）。本番未採用、`eval_chunk_strategy.py` 用に残置（判断経緯は [設計過程](../../../archive/小説RAG_設計過程.md)）。

## 4. ステップ 3: 書籍サマリ + キャラクター辞典（`full_builder` + `summarizer`）

`full_builder.build_book_full()` が Qwen で一括生成する。**サマリとキャラ辞典は 1 回の Qwen 呼び出しで同時生成**する（旧 5 段構成から統合、`summarize_book_with_characters`）。

- **Step 1**: `rebuild_from_pages`（§3、常実行）。
- **Step 2 `_run_combined_step`**: `summarize_book_with_characters(conn, book_name)` が `_prompts.COMBINED_PROMPT`（`[SUMMARY]` / `[CHARACTERS]` / `[CHARACTER_DETAIL:名前]` マーカー）で **書籍サマリ 1 本 + 最大 20 キャラの人物像**を得る。`parse_combined_output` でマーカー分解。`update_book_summary` が `books.summary` を更新し LanceDB `summaries` テーブルへ embedding を upsert（B-8）。キャラ分は `book_characters` を書き直し、`first_page`/`page_count` を `full_text LIKE %名前%` で近似する。
- **skip 条件**: `books.summary` と `book_characters.summary` が両方存在 かつ `redo=False` なら Step 2 全体をスキップ。
- **本文入力（`_load_body_text`）**: `char_count >= NOVEL_DB_MIN_BODY_CHARS` かつ先頭/末尾 `NOVEL_DB_BODY_PAGE_MARGIN` ページを除いた本文をページ順連結。
- **サイズ分岐（`summarizer`）**: 本文 ≤ `ONE_SHOT_MAX_BODY_CHARS`(200,000) は 1-shot（`num_ctx=131072`）。超過時は combined を諦めサマリのみ map-reduce（20,000 字 × 最大 8 チャンク → reduce）で生成し、キャラ辞典は空。

補足: `character_summarizer.summarize_character`（1 キャラ × 1 冊を単独 Qwen 生成、body ≤ 80,000 字 / `num_ctx=65536`）と `character_db`（`book_characters` の集計・CRUD）は、`pages.main_characters` を材料にした**単独 B-15 経路**（CLI `build_character_summaries.py`）。full_build は上記の combined 経路を使うため、この単独経路とは独立に併存する。

## 5. ステップ 4: チャンク文脈生成（`full_builder.build_book_contexts` + `contextualizer`）B-9

Anthropic の Contextual Retrieval 手法。各チャンクに「書籍内のどの場面か」の 1 文（80〜120 字）を付け、`(contextual_text + 本文)` を再 embedding して recall を上げる。**B-23 で full_build から分離した独立ジョブ**（`mode=generate_contexts`）。

- **生成（`contextualizer.generate_chunk_context`）**: 書名 + 書籍サマリ + チャンク先頭 1200 字を GEMMA_BACKEND に投げる。プロンプトは**本文の固有名詞と特徴的フレーズを必ず含める**よう明示（`num_predict=256`, `num_ctx=8192`）。失敗時は空文字を返し未処理のまま残す。
- **対象**: `book.summary` がある書籍の、`contextual_text IS NULL` のチャンク（`redo=True` で全チャンク）。サマリ未生成の書籍はスキップ（Step 2 が前提）。
- **skip 判定（`should_skip_context`）**: `char_count < NOVEL_DB_MIN_BODY_CHARS`(300) または先頭/末尾 `NOVEL_DB_BODY_PAGE_MARGIN`(5) ページ以内のチャンクは `contextual_text = NULL` に保つ。
- **再 embedding（`make_embedding_input`）**: `ctx` があれば `ctx + "\n\n" + text`、無ければ `text` のみを bge-m3 で再計算し、LanceDB を `delete(chunk_id)` → `add` で更新。

## 6. 補助ステップ

- **主要登場人物抽出（`character_extractor.extract_main_characters`）**: 各ページ本文（先頭 1500 字）を GEMMA_BACKEND に投げ、最大 3 名をカンマ区切りで取得 → `pages.main_characters`。CLI `extract_characters.py` で任意実行。用途は 3 つ: 検索ヒットのキャラヒント（[検索QA設計](小説RAG_検索QA設計.md)）、`character_db` のキャラ集計（B-15 単独経路）、C-12 の共起カウント。失敗ページは NULL のまま続行。
- **キャラクター関係グラフ（`relation_extractor.generate_book_relations`）C-12**: `pages.main_characters` の同一ページ共起を数えエッジ重みとし、`book_characters.summary` を Qwen に渡して関係タイプ（友人・師弟・敵対 等）を JSON 抽出 → `character_relations` に REPLACE。`mode=generate_relations` ジョブ。読み取りは `graph_query`（series 単位で nodes/edges 組み立て、内部利用のみで専用 API 無し）。

---

## 7. 再構築ジョブ（`job_queue` + `job_worker`）

全処理は `rebuild_jobs` テーブル経由の**全体ロック + 単一 worker 直列実行**。並列化は GPU/CPU 高負荷のため逆効果、書籍単位ロックの実装複雑化は利得薄、という判断。

- **`NovelDbJobQueue`**: `enqueue(job_type, target_id, mode)` / `cancel` / `get_status` とライフサイクル。`start()` で「`running` を `failed` に戻す（サーバ再起動時）」+ 旧 mode 名の migration（`pdf_text→rebuild` / `reocr→ocr`）を実行し worker スレッドを起動。`main.py` の lifespan で start/stop。
- **`NovelDbJobWorker`**: 5 秒 polling + wakeup Event。`_claim_next_job`（`queued` を古い順に 1 件 `running` 化）→ `_execute_job`（mode 分岐）→ `_mark_finished`。progress/step/detail を `rebuild_jobs` に逐次書き込み、UI がポーリング表示する。

**JobMode と対象書籍（`_resolve_targets`, `job_type="all"` 時）**:

| mode | 処理 | `all` 時の対象 |
|---|---|---|
| `ocr` | 画像 → yomitoku → `pages.full_text` | `ocr_done_at IS NULL`（未 OCR） |
| `rebuild` | `pages` → chunks/embedding 再構築 | `ocr_done_at IS NOT NULL`（OCR 済み全冊） |
| `full_build` | rebuild + サマリ + キャラ辞典 | `ocr_done_at IS NOT NULL AND indexed_at IS NULL` |
| `generate_contexts` | チャンク文脈 + 再 embedding | `contextual_text IS NULL` のチャンクを持つ書籍 |
| `generate_relations` | キャラ関係グラフ（C-12） | OCR 済み全冊 |

`job_type="book"` は `target_id` の 1 冊、`job_type="series"` は meta.db から解決したシリーズ内 novel 書籍。旧 `pdf_text`/`reocr` は起動時 migration で正規化済み。

**キャンセル仕様**: `queued` のジョブのみ `DELETE /builds/{id}` で `canceled` にできる。`running` の DELETE は **409 Conflict**（実行途中中断は embedding バッチ整合性を壊すため不可）。

**失敗時**: `_execute_job` 例外は `state='failed'` + `error_message`（traceback 込み）。`rebuild_from_pages` は `with conn:` トランザクションで囲まれ、失敗時はロールバックされ「再構築前の状態」に戻る（半端な部分データは残らない）。

---

## 8. CLI と処理順序

CLI 一覧は [データ設計 §3.3](小説RAG_データ.md)。UI の各ボタンは同等のジョブを投入する。推奨順序:

```
ocr → full_build（= rebuild + summary + characters）→ generate_contexts →（任意）generate_relations
```

`generate_contexts` は `books.summary` を前提とするため full_build より後。テストは `backend/tests/test_novel_db_*.py`（embedding / LLM はモック）。
