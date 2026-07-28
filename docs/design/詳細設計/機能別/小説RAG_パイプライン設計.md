# 小説 RAG 構築パイプライン設計

> status: living | last-verified: 2026-07-28

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
      │        [full_build] ────────┤ books.summary + book_characters  … full_builder（事実抽出→個別執筆→校正）
      │                              │
      │  [generate_contexts] ───────┤ chunks.contextual_text + 再embed  … full_builder.build_book_contexts
      │                              │
      └──[extract_characters CLI]──► pages.main_characters              … character_extractor
                                     │
             [generate_relations] ──► character_relations (C-12)        … relation_extractor
```

各ジョブが対象とする「未処理書籍」の判定条件は §7 の `_resolve_targets` を参照。

---

## 2. ステップ 1: OCR 取込（`job_worker` / `ocr_staging` / `extractor` / `ocr_worker`）

`images/{書籍名}/NNN.png` を Surya OCR 2 でページ単位に処理し、
品質結果を staging へ保存する。処理完了後は `awaiting_qa` とし、
必須ページのQAとrun承認が完了した1冊分だけを `pages` テーブルへ書き込む。
yomitoku は独立照合と `OCR_ENGINE=yomitoku` の比較・後方互換用として残す。

- **subprocess 分離**: `extractor.iter_ocr_pages` が対象ページmanifestを一時JSONで渡し、`ocr_worker.py` をOCR venvのPythonで1回起動する。workerは1ページごとにJSON Linesを返し、stderrはbackendログへ流す。
- **Surya推論**: Windows上のCUDA対応 `llama-server` へOpenAI互換APIで接続する。到達不能時は設定済みの実行ファイル・model・mmprojからworkerが所有サーバーを1回だけ起動する。
- **worker内部**: PNGをバイト列として読み、SHA-256を計算してPillowで復号する。Suryaのraw HTML/bboxを解析し、不合格時だけ入力条件を変えて最大3候補を比較する。`OCR_ENGINE=yomitoku` の後方互換経路だけは OpenCV で復号する。
- **チェックポイント**: `ocr_staging` が `ocr_runs` / `ocr_page_results` にページ単位で保存する。再実行時は画像SHAが同じ `passed` ページをスキップする。
- **二段階保存**: 全ページの結果を staging へ保存して `awaiting_qa` に進める。この時点では公開済み本文を変更しない。必須ページの承認・補正と run 承認後だけ `_store_ocr_pages` と同等の更新を1トランザクションで行い、`books.ocr_done_at` とFTSを同期する。
- **直接呼出し互換経路**: `builder.ocr_book` は旧CLI向けに残る直接保存APIで、チェックポイント・二段階確定を行わない。管理画面とjob queueは必ず上記のステージング経路を使用する。
- **PDF モード（後方互換）**: `extractor.extract_pages(pdf)` は PyMuPDF `get_text("blocks")` で縦書きブロックを取得しブロック内改行を除去して連結する。旧 Searchable PDF 由来の書籍向けで、現行の取込は画像 OCR 経路が主。

## 3. ステップ 2: チャンク分割 + embedding（`builder.rebuild_from_pages`）

`pages.full_text` を入力に `chunks`（SQLite）と LanceDB `chunks` テーブルを再構築する。**`pages` は一切変更しない**（OCR 済みの本文を前提）。

- **チャンク分割（`chunker.chunk_page`）**: 全文 ≤ 800 字なら 1 チャンク。超える場合は末尾 100 字以内の句点境界（`。」!?`）優先で切り、50 字オーバーラップ。`char_count < 30` のページ（章扉・ヘッダのみ）はスキップ。
- **embedding（`embedder.embed_batch`）**: Ollama `/api/embed`（httpx）で bge-m3（1024 次元）。builder は 16 件バッチ。`options.num_gpu` に `NOVEL_DB_EMBED_NUM_GPU`（既定 CPU）を渡し llama-server に VRAM を譲る。次元・件数不一致は `EmbeddingError`。
- **保存**: 既存 chunks を LanceDB（`chunk_id IN (...)`）と SQLite の両方から削除 → `chunk_page` の結果を `chunks` に INSERT、embedding を LanceDB に `add`（本文・page_no・char_count・page_count を同梱）。完了時に `books.indexed_at` を更新。progress_callback で `embedding done/total` を通知。
- **ページ単位再構築（`page_index_builder.rebuild_page_from_pages`）**:
  画像照合後に1ページだけ本文を補正した場合、
  対象ページのSQLite `chunks`とLanceDBベクトルだけを再生成する。他ページのchunk IDと
  embeddingは保持する。FTS5はexternal-contentテーブルから古い語を確実に除くため
  `pages_fts`全体を`rebuild`するが、embedding計算は対象ページに限定する。運用時は
  `build_novel_db.py --book "<書籍名>" --page <画面番号>`から実行する。2026-07-28の
  本番6ページ再構築では、全件で対象外ページのchunk件数・ID合計が不変で、
  書籍全体のchunk総数も再構築前後で一致した。
- **入力の責務**: ページ単位再構築は`pages.full_text`、`char_count`、
  `index_eligible`を変更しない。OCR runの承認・画像照合補正を先に完了し、公開済み
  `pages`を正本として索引だけを同期する。`page_no`は紙面ページではなくキャプチャ画面番号。
- **ページ単位再構築の失敗安全性**: 新本文のチャンク分割とembeddingを変更前に完了し、
  旧LanceDB行を退避してから更新する。更新開始時に`books.indexed_at=NULL`を確定して
  不完全状態を可視化する。SQLiteまたはLanceDB更新に失敗した場合はSQLiteをrollbackし、
  追加したLanceDB行を削除して退避行を復元する。復元の成否にかかわらず
  `indexed_at`はNULLのままとし、通常の書籍単位`rebuild_from_pages`を復旧手段とする。
  更新前から対象chunk IDのSQLite件数とLanceDB件数が一致しない場合は変更せず中止し、
  ページ単位処理で不整合を上書きせず書籍単位再構築へフォールバックする。
- **クロスページ実験 `chunk_book`**: 全ページ連結 + bisect で page_id 解決する実験実装（1200 字 / overlap 120）。本番未採用、`eval_chunk_strategy.py` 用に残置（判断経緯は [設計過程](../../../archive/小説RAG_設計過程.md)）。

## 4. ステップ 3: 書籍サマリ + キャラクター辞典（`full_builder` + `summarizer`）

`full_builder.build_book_full()`は、本文から完成文を一度に生成せず、**事実抽出 → 要約・人物の個別執筆 → 編集校正 → 品質ゲート → 一括確定**の順で処理する。処理時間より、本文根拠の維持、後半の変化の取りこぼし防止、読みやすい日本語を優先する。

LLM呼び出しごとのtemperature・出力長・context長は用途別定数として各機能側に残す。一方、Ollama互換options辞書のキー組み立ては`llm_options.make_llm_options()`に集約し、キー名の表記揺れや型なし辞書の複製を避ける。

- **Step 1**: `rebuild_from_pages`（§3、常実行）。
- **Step 2a 事実抽出**: `summarizer`が採用本文を`[page N]`付きでQwenへ渡し、
  まず出来事の発端・行動・理由・結果・関係変化を`[BOOK_FACTS]`として抽出する。
  続けて、この書籍事実だけを入力に人物名と立場・行動・変化を
  `[CHARACTER_FACT:人物名]`へ再編する。書籍事実と人物事実を一度に生成すると、
  長編では書籍事実だけで出力上限へ達し人物マーカーが欠落するため、2回に分離する。
  本文が入力上限を超える場合だけページ境界で複数ブロックへ分け、各ブロックの
  書籍事実・人物事実を後段へすべて渡す。事実抽出では完成した紹介文を書かせない。
- **Step 2b 要約執筆**: 書籍要約は事実表だけから独立生成する。中心人物、因果、時系列、対立、転機、結果、関係変化、巻の意味を自然な複数段落へ編集する。
- **Step 2c 人物別執筆**: 事実表の人物名を`character_names.normalize_character_entries`で正規化し、本文に根拠がある人物を登場ページ数順で最大20名選ぶ。人物ごとに関連ページと事実メモを渡し、他人物と混在させず個別に説明を生成する。
- **全巻を覆う人物入力**: 関連本文が入力上限を超える場合、先頭からの単純切り捨ては禁止する。初出と最終出現を必ず含め、全登場範囲を時間帯に分けて各区間から情報量の多いページを選び、その後に残容量を埋める。終盤の選択や関係変化を入力から落とさない。
- **Step 2d 編集校正**: 書籍要約と人物説明を別の編集プロンプトへ渡し、主語不明、因果の飛躍、曖昧な代名詞、電文調、重複、名詞句の連結を修正する。校正は事実表にない設定や心理を追加してはならない。校正版が品質ゲートを通らない場合は、合格している初稿へ戻す。
- **品質ゲート**: 空出力、生成マーカーやコードフェンスの混入、同一文・同一段落の反復、人物名を一度も明示しない人物説明を不合格にする。人物は本文一致ページが1件以上必要で、保守的な短縮別名は2ページ以上一致した場合だけ根拠に使う。
- **一括確定**: 要約と全人物説明をメモリ上で完成・検査してから、`books.summary`と`book_characters`を単一SQLiteトランザクションで置換する。いずれかの人物生成・校正・検査が失敗した場合はDBを書き換えず、既存公開版を維持する。コミット後にLanceDBのサマリembeddingを更新し、失敗時は従来どおりSQLite本文を正として次回再実行する。
- **skip 条件**: `books.summary`と`book_characters.summary`が両方存在し、かつ`redo=False`ならStep 2全体をスキップする。
- **本文入力**: `char_count >= NOVEL_DB_MIN_BODY_CHARS`かつ先頭/末尾`NOVEL_DB_BODY_PAGE_MARGIN`ページを除いた`index_eligible=1`本文を、ページ番号付きでページ順に使用する。
- **生成文の品質方針**: 書籍サマリ、分割要約、人物像には目標文字数や
  1段落固定を設けない。`num_predict`はLLM暴走防止とcontext保護の技術上限であり、
  文章をその長さへ縮める要件ではない。必要情報を過不足なく伝え、主語・因果・
  時系列・人物関係を省略しない自然な日本語を優先する。
- **書籍サマリの受入条件**: 中心人物、発端、主要な対立と出来事、転機、結果、
  関係性の変化、巻のテーマまたはシリーズ上の意味が、未読の内部事情を知らない
  読者にも流れとして理解できる。場面羅列、名詞句の連結、文字数合わせの圧縮を
  避け、話題の切れ目では段落を分ける。
- **人物像の受入条件**: 「誰で、どの立場にあり、誰とどう関係するか」を最初に
  明示し、この巻での主要な行動・選択、その理由や心情、関係の変化、物語上の役割を
  根拠本文の範囲で説明する。登場量が少ない人物は情報を水増しせず、重要人物は
  必要に応じて複数段落で説明する。曖昧な代名詞、電文調、根拠のない補完を避ける。
- **不完全出力の扱い**: 事実表の書籍事実または人物事実を識別できない、完成文を品質ゲートへ通せない場合はエラーにして再実行する。不完全な生成物の一部だけを保存しない。
- **再生成監査**: 既存公開版を`audit_generated_content.py snapshot`でJSONへ退避してから
  再生成する。再生成後は`diff`で要約・人物集合・人物説明・生成日時・機械品質ゲートの
  差分をJSONとMarkdownへ出力し、変更された全文をCodex補助QAの対象にする。
  人手QAで不採用の場合は、書名の完全一致確認を必須とする`restore`でSQLiteの旧版を
  トランザクション復元する。復元後のサマリembedding更新に失敗した場合もSQLiteを正本とし、
  エラー終了して次回の再index対象とする。

補足: `character_summarizer.summarize_character`は、1キャラ×1冊の個別執筆と全巻範囲入力選択を担い、full buildとCLI `build_character_summaries.py`から共用する。`character_db`は`book_characters`の集計・CRUDを担う。

## 5. ステップ 4: チャンク文脈生成（`full_builder.build_book_contexts` + `contextualizer`）B-9

Anthropic の Contextual Retrieval 手法。各チャンクに「書籍内のどの場面か」の 1 文（80〜120 字）を付け、`(contextual_text + 本文)` を再 embedding して recall を上げる。**B-23 で full_build から分離した独立ジョブ**（`mode=generate_contexts`）。

- **生成（`contextualizer.generate_chunk_context`）**: 書名 + 書籍サマリ + チャンク先頭 1200 字を GEMMA_BACKEND に投げる。プロンプトは**本文の固有名詞と特徴的フレーズを必ず含める**よう明示（`num_predict=256`, `num_ctx=8192`）。失敗時は空文字を返し未処理のまま残す。
- **対象**: `book.summary` がある書籍の、`contextual_text IS NULL` のチャンク（`redo=True` で全チャンク）。サマリ未生成の書籍はスキップ（Step 2 が前提）。
- **skip 判定（`should_skip_context`）**: `char_count < NOVEL_DB_MIN_BODY_CHARS`(300) または先頭/末尾 `NOVEL_DB_BODY_PAGE_MARGIN`(5) ページ以内のチャンクは `contextual_text = NULL` に保つ。
- **再 embedding（`make_embedding_input`）**: `ctx` があれば `ctx + "\n\n" + text`、無ければ `text` のみを bge-m3 で再計算する。文脈生成は LLM の失敗をチャンク単位で隔離し、成功分を最大 16 件ずつ `embed_batch` へ渡す。LanceDB は同一バッチの `chunk_id IN (...)` を一括削除してから行群を 1 回で追加し、SQLite は `executemany` と 1 transaction で `contextual_text` を確定する。Embedding / LanceDB 更新に失敗したバッチは SQLite を未更新に保つため、`redo=False` の次回ジョブで再試行できる。

## 6. 補助ステップ

- **主要登場人物抽出（`character_extractor.extract_main_characters`）**: 各ページ本文（先頭 1500 字）を GEMMA_BACKEND に投げ、最大 3 名をカンマ区切りで取得 → `pages.main_characters`。CLI `extract_characters.py` で任意実行。用途は 3 つ: 検索ヒットのキャラヒント（[検索QA設計](小説RAG_検索QA設計.md)）、`character_db` のキャラ集計（B-15 単独経路）、C-12 の共起カウント。失敗ページは NULL のまま続行。保存済み文字列のカンマ・読点分割、敬称・肩書除去、匿名役職除外、重複排除、上限適用は`character_names`を正本とし、ページ抽出・キャラ集計・full build・関係抽出から共用する。外国人名の中黒`・`は名前の一部として保持し、区切りには使わない。
- **キャラクター関係グラフ（`relation_extractor.generate_book_relations`）C-12**: `pages.main_characters` の同一ページ共起を数えエッジ重みとし、`book_characters.summary` を Qwen に渡して関係タイプ（友人・師弟・敵対 等）を JSON 抽出 → `character_relations` に REPLACE。`mode=generate_relations` ジョブ。読み取りは `graph_query`（series 単位で nodes/edges 組み立て、内部利用のみで専用 API 無し）。

---

## 7. 再構築ジョブ（`job_queue` + `job_worker`）

全処理は `rebuild_jobs` テーブル経由の**全体ロック + 単一 worker 直列実行**。並列化は GPU/CPU 高負荷のため逆効果、書籍単位ロックの実装複雑化は利得薄、という判断。

- **`NovelDbJobQueue`**: `enqueue(job_type, target_id, mode)` / `cancel` / `get_status` とライフサイクル。`start()` で「`running` を `failed` に戻す（サーバ再起動時）」+ 旧 mode 名の migration（`pdf_text→rebuild` / `reocr→ocr`）を実行し worker スレッドを起動。`main.py` の lifespan で start/stop。
- **`NovelDbJobWorker`**: 5 秒 polling + wakeup Event。`_claim_next_job`（`queued` を古い順に 1 件 `running` 化）→ `_execute_job`（mode 分岐）→ `_mark_finished`。progress/step/detail を `rebuild_jobs` に逐次書き込み、UI がポーリング表示する。ただし、`rebuild_from_pages` が同じ `novel.db` の書込みトランザクションを保持している間の `current_detail` 更新は補助的な表示情報として扱う。別接続が `database is locked` になった場合は詳細更新だけを省略し、本文チャンク・embedding の本処理を失敗させない。ジョブ終了時の progress/state 更新は必須とする。
- **シリーズメタ索引**: `series_meta.load_book_series_ids()` が meta2.db の novel メタを `book_name → series_id` の辞書へ変換する正本。`generate_relations` のジョブ開始時に1回だけ読み、全対象書籍で共有する。CLIの `--series` 対象解決も `book_names_for_series()` を使い、PDF拡張子除去や空ID判定を重複実装しない。

**JobMode と対象書籍（`_resolve_targets`, `job_type="all"` 時）**:

| mode | 処理 | `all` 時の対象 |
|---|---|---|
| `ocr` | 画像 → Surya OCR 2（yomitoku限定補助）→ 品質ゲート → `pages.full_text` | `ocr_done_at IS NULL`（未 OCR） |
| `rebuild` | `pages` → chunks/embedding 再構築 | `ocr_done_at IS NOT NULL`（OCR 済み全冊） |
| `full_build` | rebuild + サマリ + キャラ辞典 | `ocr_done_at IS NOT NULL AND indexed_at IS NULL` |
| `generate_contexts` | チャンク文脈 + 再 embedding | `contextual_text IS NULL` のチャンクを持つ書籍 |
| `generate_relations` | キャラ関係グラフ（C-12） | OCR 済み全冊 |

`job_type="book"` は `target_id` の 1 冊、`job_type="series"` は meta2.db から解決したシリーズ内 novel 書籍。旧 `pdf_text`/`reocr` は起動時 migration で正規化済み。

**キャンセル仕様**: `queued` のジョブのみ `DELETE /builds/{id}` で `canceled` にできる。`running` の DELETE は **409 Conflict**（実行途中中断は embedding バッチ整合性を壊すため不可）。

**失敗時**: `_execute_job` 例外は `state='failed'` + `error_message`（traceback 込み）。
SQLiteとLanceDBをまたぐ更新は単一トランザクションではないため、書籍単位
`rebuild_from_pages`が失敗した場合は同じ書籍を再実行して両ストアを収束させる。
ページ単位`rebuild_page_from_pages`は旧ベクトル退避・補償復元と
`indexed_at=NULL`の不完全状態マーカーを備え、復元できない場合は書籍単位再構築へ
フォールバックする。

---

## 8. CLI と処理順序

CLI 一覧は [データ設計 §3.3](小説RAG_データ.md)。UI の各ボタンは同等のジョブを投入する。推奨順序:

```
ocr → full_build（= rebuild + summary + characters）→ generate_contexts →（任意）generate_relations
```

`generate_contexts` は `books.summary` を前提とするため full_build より後。テストは `backend/tests/test_novel_db_*.py`（embedding / LLM はモック）。
