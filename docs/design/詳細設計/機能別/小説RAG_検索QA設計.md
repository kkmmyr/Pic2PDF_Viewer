# 小説 RAG 検索・QA 設計

> status: living | last-verified: 2026-08-22

novel タブのハイブリッド検索・RAG 質問応答・マルチターンチャット・読書会番組台本生成の現在形設計。DB 構築側は [パイプライン設計](小説RAG_パイプライン設計.md) を参照。

**環境変数・スキーマ・LLM backend / port・API 一覧は [データ設計](小説RAG_データ.md) が正本**。本書は重複記載せず、検索・QA の処理フローに集中する。段階拡大（num_ctx PoC→A→B→C・top_k）や俯瞰質問三段改善（B-5/B-8/B-9）の経緯は [設計過程（凍結）](../../../archive/小説RAG_設計過程.md)、実機ベンチ・モデル選定は [技術知見](../../../log/技術知見/小説RAG_技術知見.md)。

検索/QA のコアは `backend/services/novel_db/` の `search_scope.py` / `search.py` / `page_fts.py` / `book_summary_search.py` / `retrieval.py` / `prompt_builder.py` / `query_expander.py` / `llm.py` / `qa_history.py` / `qa_sessions.py` / `discussion_service.py`（+ `discussion_cast.py` / `discussion_prompts.py` / `discussion_checks.py`）、ルーターは `backend/routers/novel_db/{search,qa,chat}.py`。

---

## 1. 検索（`search_scope.py` / `search.py` / `book_summary_search.py`）

lexical検索（既定FTS5、段階導入中のpage-level LanceDB ICU BM25）とベクトル検索
（LanceDB KNN）を Reciprocal Rank Fusion（RRF）でページ単位に融合する。

- **Scope（`search_scope.py`）**: `Scope(type, id)`。`type` は `all` / `series` / `book`。`resolve_book_names(scope)`（lru_cache）が対象書籍名リストを返す（`all` は None = 全件、`series` は `meta2.db` から展開、`book` は 1 冊）。空リストなら 0 件。
- **lexical selector（`lexical_search`）**: `NOVEL_DB_LEXICAL_BACKEND`の`fts5` / `shadow` / `lance_icu`を選ぶ。初期既定値は`fts5`。`shadow`も利用者へ返す順位はFTS5と完全同一で、ICUは観測専用。`lance_icu`でICUがmissing / stale / 不整合 / 例外の場合はFTS5へ縮退するが、正常な0-hitはfallbackしない。
- **FTS5（`fts_search`）**: `build_fts5_or_query` が質問から 2 文字以上のトークンを抽出し `"t1" OR "t2" …` に整形。`snippet(pages_fts, …, '<mark>', '</mark>', …)` + `bm25()` で取得。`char_count >= min_chars` と先頭/末尾 `body_page_margin` ページ除外を WHERE に、scope を `b.name IN (...)` で適用。
- **ICU BM25（`page_fts.search_page_fts`）**: active世代がSQLiteの現行`source_revision`と一致する場合だけ`MatchQuery(query, "text")`を実行する。scopeはSQLiteでbook IDへ解決して数値prefilterし、`char_count` / `page_no`もLanceDB側でprefilterする。結果IDの本文・書名・公開可否はSQLiteから再取得し、snippetはquery中の最長一致断片を中心に最大200字へ決定的に切り出す。
- **ベクトル（`vec_search`）**: 質問を bge-m3 で埋め込み、LanceDB `chunks` を KNN 検索。フィルタ有り時は `k = max(top*5, 50)` を多めに取り、`char_count`・`book_name` を prefilter、`body_page_margin` は取得後にページ番号で後置フィルタ、`_distance` 昇順で top 件。**ベクトルの埋め込みは B-9 適用後 `(contextual_text + 本文)`**（[パイプライン設計 §5](小説RAG_パイプライン設計.md)）なので、語彙一致のない抽象クエリでも位置説明経由でヒットする。
- **RRF 融合（`hybrid_search`）**: FTS/ベクトル各リストの順位で `score += 1/(k_rrf + rank + 1)`（`k_rrf=60`）を `(book_name, page_no)` に加算。FTS ヒットは `sanitize_snippet` 済み snippet、ベクトルのみのヒットは本文先頭 200 字（`html.escape` のみ）。`max_per_book`（scope=all/series 用）で書籍偏りを抑え top 件に絞り、`_fetch_main_characters` で各ページの主要登場人物を JOIN。返り値は `SearchHit{book_name, page_no, snippet, has_highlight, image_url, rrf_score, main_characters}`。
- **snippet サニタイズ（`sanitize_snippet`）**: `html.escape` で全エスケープ後、`&lt;mark&gt;` のみ `<mark>` に復元。フロントは `dangerouslySetInnerHTML` を追加サニタイザ無しで安全に使える。
- **書籍サマリ検索（`book_summary_search.py` の `search_book_summaries`）B-8**: LanceDB `summaries` テーブルへの KNN（FTS5 は使わない — サマリは抽象表現中心で意味類似が効く）。`[(book_name, distance), …]`。空テーブル時は空リスト（後方互換）。
- **サマリ用途分離**: RAG検索・類似書籍・横断QAには網羅性を優先した`books.summary`を使う。`books.catalog_summary`は400〜700文字の選書用で、書籍一覧・詳細APIから返すが、検索embeddingの入力には使わない。
- **類似書籍（`book_summary_search.py` の `find_similar_books`）**: 対象書籍のサマリ embedding を取り自身を除く KNN。bge-m3 は正規化済みのため `score ≈ 1 - L2/2`（コサイン近似）。lib.py の類似書籍 API が利用。
- **全ページ読み（`load_all_pages_of_book`）B-13 段階 C**: hybrid_search を bypass し、`min_chars`/`body_page_margin` フィルタ後の全ページを `page_no` 順に `SearchHit` として返す。scope=book の full-book モード用。

**検索フィルタのデフォルト値**（`NOVEL_DB_MIN_BODY_CHARS` / `NOVEL_DB_BODY_PAGE_MARGIN` / `NOVEL_DB_QA_MAX_PER_BOOK` / `NOVEL_DB_QA_TOP_K` 等）は [データ設計 §2](小説RAG_データ.md)。狙いと段階拡大の経緯は [設計過程](../../../archive/小説RAG_設計過程.md)。

OCR QAで `page_type` と `index_eligible` を明示確定した書籍は、`index_eligible=1`
を検索・QA本文選択の正本とする。旧来の文字数300未満除外と先頭・末尾5ページ除外は、
ページ種別が未整備だった時代のノイズ抑制策であり、検索・QA取得には重ねて適用しない。
これにより章間の短文、詩、短い会話だけの本文も検索できる。目次・挿絵・広告等は
`index_eligible=0`かつ公開本文空欄で除外する。文字数・ページ位置フィルタは、
サマリやコンテキスト生成の処理量抑制には引き続き利用できる。

### 1.1 ICU indexの構築・世代切替

`build_page_fts_index.py`はSQLite `pages`を`id`順で全件読み、`index_eligible=1`のpageを
新しい`pages_icu_r<revision>_<hash>_<build-id>` tableへ書く。既存の
`chunks` / `summaries`、旧active tableは変更しない。FTS設定はLanceDB 0.34系で検証した
`FTS(base_tokenizer="icu", stem=False, remove_stop_words=False, ascii_folding=False)`に固定する。

公開前に次をすべて検査する。

1. source page IDが一意で、LanceDB row数と一致する。
2. ID・book ID・page番号・文字数・book page数・書名・本文から作るcanonical SHA-256がbuild開始時の値と一致する。
3. FTS indexが1件存在し、`num_indexed_rows`がrow数、`num_unindexed_rows`が0である。
4. active pointer更新時にもSQLiteの`source_revision`がbuild開始時と同じである。

最後の条件付きUPDATEだけをSQLite transactionで確定するため、同時にOCR公開・補正が走った場合は
新tableをactiveにしない。canonical本文を更新するOCR QA公開、legacy OCR保存、補正ページ再構築は、
同じtransactionで`source_revision`を増やし`status=stale`にする。失敗したbuildは旧active pointerを
保持し、作成途中のtableだけをbest-effortで除去する。正常な世代tableはrollback用に保持する。

`shadow`ログはqueryのSHA-256先頭12桁、FTS5 / ICU件数、上位集合の重複数、各latency、成否だけを
記録し、query本文・OCR本文・snippetを記録しない。ICUが利用不能でも検索レスポンスはFTS5で継続する。

### 1.2 運用手順とrollback

**適用状態（2026-08-22 14:15 JST）**: productionへstage 1 `shadow`を適用済みである。active backendは
`backend-20260822141221-47136`、LanceDBは`0.34.0`、Alembicは`0014`。page ICUは8,576行を完全構築し、
source / active revision `0`、canonical SHA-256
`94f0bfab52393f2c8bc7b0bb53ce8d7e338d0096764c71bac2f33e2dee153cd0`、SQLite integrity `ok`、
未索引0件を確認した。production設定は`NOVEL_DB_LEXICAL_BACKEND=shadow`であり、利用者へ返す結果は
従来FTS5のまま。`lance_icu`への昇格は未承認である。

事前監査で検出したLanceDB `0.30.2`とdependency未同期の旧deploy経路は、source・common・venvを
一体化した世代releaseへ置換した。active環境を直接更新せず、検証済みbackup、locked dependency、
import / FTS5 smoke、backward-compatible migration、HTTP probeを通してsymlinkを切り替える。
旧backend releaseはrollback用に保持する。

**運用前提（2026-08-22承認）**: productionは信頼済みoperator 1名だけが利用する個人環境であり、
高可用性SLAは設けない。この前提では、短時間のmaintenance停止、shadow logの手動集計、旧index / venv
世代の手動整理、query hashが辞書推測され得る残存リスクを受容する。専用alert基盤や無停止blue-green
serviceまでは初回導入条件にしない。一方、個人利用でもデータ破損・検索欠落は受容しないため、workspace
lockによるdependency同期、実行中writer 0件、backupと復元検査、build manifest整合、`fts5` fallbackは
省略不可とする。

本番候補環境では次の順序を守る。page ICU構築はembeddingやLLMを呼ばず、GPUを使用しない。
revision `0014`は外部索引の状態表を追加するだけのbackward-compatible migrationである。deployは
このmigrationだけを直前backend世代にも配置してから適用し、DB revisionが進んだ後でも旧source / venvを
再起動できるようにする。今後、未承認migrationが追加された場合は自動deployをfail closedとし、rollback
互換性を別途設計するまで適用しない。

| 順序 | 操作 | 成功条件 / 失敗時の扱い |
|---|---|---|
| 0 | ルート`uv.lock`とworkspace memberを別backend世代へ配置し、その世代専用venvへdependencyを同期する。LanceDB `>=0.34,<0.35`、backend import、FTS5 smokeを確認する | active source / venvを直接更新しない。いずれか不合格なら世代切替・migration・index構築を行わず、従来backend世代を継続する |
| 1 | OCR / rebuild等のwriterと定期backupが重ならないmaintenance windowを確保し、SQLite / LanceDBの復元可能なbackupを作る | LanceDB backupはdirectory copyのため、書込みを停止して取得・復元検査する。configured pathが意図した本番実体を指す |
| 2 | backendを配置し、`cd backend && uv run python scripts/build_page_fts_index.py`を実行する | CLIがAlembicをheadへ上げ、stdoutの単一JSONが`ok=true`。`row_count`、`source_sha256`、table名、LanceDB version、index設定を保存する |
| 3 | `novel_search_index_state`の`status=active`、source / active revision一致、manifest row数を確認する | 不一致・build失敗・同時更新ではshadowへ進まず、FTS5を継続して原因解消後に完全再構築する |
| 4 | `NOVEL_DB_LEXICAL_BACKEND=shadow`を設定してbackendを再起動する | 利用者へ返す順位はFTS5と同一。`lexical shadow` / `lexical shadow unavailable`ログを集計CLIへ入力し、成功・fallback率、FTS5 / ICU latency、上位重複を保存する |
| 5 | 実運用shadowと未調整holdoutのゲートを評価する | 合格しても自動切替しない。`lance_icu`へのproduction切替は別承認・別変更とする |

canonical本文の更新でstateが`stale`になった場合、shadow / `lance_icu`はいずれもFTS5を返す。
再びICUを利用するには同じCLIで全対象pageを再構築する。即時rollbackは
`NOVEL_DB_LEXICAL_BACKEND=fts5`へ戻してbackendを再起動するだけで、LanceDB tableの削除は不要。
旧世代tableのGCは自動化していないため、active tableを手動削除せず、容量整理はmanifestと
active pointerを照合する専用手順を設計してから行う。

---

## 2. 検索・コンテキスト構築（`retrieval.py`）

`retrieve(conn, question, scope) → RetrievalResult{hits, book_summaries, qa_options}`。単発 QA（qa.py）とチャット初手（chat.py）で共通。

- **full-book モード**（`scope=book` かつ `NOVEL_DB_QA_FULL_BOOK_MODE` 有効、既定 True）: `load_all_pages_of_book` で全ページ読み、`qa_options` の `num_ctx` を `NOVEL_DB_QA_FULL_BOOK_NUM_CTX`(131072) に上書き。`book_summaries` は None。
- **通常 RAG 経路**:
  1. **Query Expansion**（`query_expander.expand_query`、有効時）で元質問 + 追加クエリ = 計 N 個を生成。
  2. 各クエリで `hybrid_search`（`top=NOVEL_DB_QA_TOP_K`、scope=all/series では `max_per_book` 有効）。
  3. `(book_name, page_no)` でデデュープし RRF スコア最大値を採用、top_k に絞る。
  4. scope=all/series では `search_book_summaries` の hit 書籍とページ hit 書籍の和集合を `load_summaries_for_books` で取得し `book_summaries` に格納（B-8）。scope=book では None。

## 3. Query Expansion（`query_expander.py`）B-11

抽象質問・関係質問の retrieval recall を上げるため、軽量 Gemma（`QUERY_BACKEND`、`NOVEL_DB_QA_EXPAND_MODEL`）で「異なる切り口（場面 / キャラ / 行動 / 関係性 / 時期）の検索クエリ」を生成する。

- `expand_query(question, n)` は**元の質問を必ず先頭に**置き、展開クエリを重複除去して後続に追加、計 N 個を返す。
- 応答パース（`query_expansion_parser.parse_expansions`）は番号付け・箇条書き記号・前置きラベル・引用符を剥がし、60 字超の説明文行を除外する純粋関数。`query_expander._parse_expansions` は既存 import 用 facade とする。
- LLM 失敗（接続エラー / 空応答）や `n<=1` 時は `[question]` にフォールバック（通常検索に縮退）。B-9 が chunk 側、B-11 が query 側を強化する直交関係。

## 4. プロンプト構築（`prompt_builder.py`）

LLM 呼び出しとは独立した純関数群。

- **単発 QA（`build_prompt`）**: `PROMPT_TEMPLATE` に、各ページを `[page N, 主要登場人物: …]`（scope=book）/ `[書名 page N, …]`（all/series）ヘッダ + 本文で並べた `context` を差し込む。回答ルールは「根拠ページ番号明記」「発言者・行動者の帰属明示」「別ページのキャラを安易に統合しない」「抽象質問は具体シーン 3 つ以上で構造的に」等。`main_characters` が空ならヒント行は省略。
- **書籍俯瞰サマリブロック（`_build_summaries_block`）**: `book_summaries` があり scope が book 以外のとき、`【書籍俯瞰サマリ】` セクションを先頭に埋め込む（背景知識、根拠はページ抜粋を主とするよう指示）。scope=book では付与しない。
- **チャット用（`build_chat_context_block` + `build_chat_system_message`）B-16**: 本文抜粋 + サマリブロックを 1 文字列にまとめ、`CHAT_SYSTEM_TEMPLATE`（読書補助アシスタント、スコープ説明 + 参照本文）の system メッセージに埋める。質問・回答ルールは system 側に持たせる。

## 5. LLM 呼び出し層（`llm.py` / `llm_provider.py`）

- **provider（`llm_provider`）**: `NovelLlmProvider` が `qwen`（LlamaServer 11435またはMLX 11437）/ `gemma`（Ollama 11434、Qwen流用、またはMLX 11437）/ `query`（既定Ollama、GemmaがMLXならMLX、timeout 60）/ `verifier` を束ねる。未知のbackend値は構築時に`LLMError`で即失敗する。`get_llm_provider()` は設定から遅延構築した既定providerを返し、application serviceは省略可能なprovider引数でfakeを注入できる。`_llm_backend`は既存import用facadeで、新規コードの依存先にはしない。詳細は[データ設計 §5](小説RAG_データ.md)。
- **`LLM_OPTIONS`**: `temperature=0.2 / repeat_penalty=1.2 / num_predict=4096 / num_ctx=NOVEL_DB_QA_NUM_CTX`。`MlxBackend`は`repeat_penalty`を`repetition_penalty`へ変換し、`top_k`、`min_p`、`seed`、presence/frequency penaltyも転送する。**注意: llama-server / MLXとも`num_ctx`はserver起動時の上限で決まり、リクエスト値は使わない**。
- **ストリーミング**: `stream_qa(prompt)` はproviderの`qwen.astream_ask`、`stream_chat(messages)`は`qwen.astream_chat`（LlamaServer / MLX対応、Ollamaは`NotImplementedError`）に委譲。バックエンド分岐・thinking抑制（`enable_thinking=False`）・SSE→Ollama形式正規化はすべて共通モジュール`local_llm`側。`_astream_ask` / `astream_chat`の薄いラッパはテストのmonkeypatch点。イベントは`{response, done, done_reason, eval_count, …}`のOllama互換dict。

## 6. 単発 QA エンドポイント（`routers/novel_db/qa.py`）

`POST /qa`（SSE）: `require_not_locked` 依存でジョブ実行中は 503 + Retry-After（[パイプライン設計 §7](小説RAG_パイプライン設計.md)）。

1. `retrieve` → `build_prompt` → `save_start`（`qa_history` に prompt/context/options を記録）。
2. `stream_qa(prompt, options=qa_options)` を SSE 配信。各 token を `{"token": …}` で送出。
3. `done` で `save_finish`（answer / `done_reason` / `eval_count`）→ `{"done": True, "history_id", …}`。
4. クライアント切断（`is_disconnected`）検知時は `done_reason="canceled"` で途中応答を保存。例外時は `save_error` + `{"error": …}`。

履歴 API（`GET /qa/history`・`GET/DELETE /qa/history/{id}`）は `qa_history.py`（`list_history` / `get_history_detail` / `delete_history`）。連投警告はフロント側チェック（API はステートレス）。

## 7. マルチターンチャット（`routers/novel_db/chat.py` + `qa_sessions.py`）B-16

1 セッション = scope 固定（開始時に book/series/all を選び途中変更不可）。会話履歴を無圧縮で先頭から積む。

- **セッション/メッセージ（`qa_sessions`）**: `create_session` / `append_message`（`last_message_at` も更新）/ `load_chat_messages`（OpenAI `[{role, content}]` 形式）/ `list_sessions` / `get_session_detail` / `delete_session`（CASCADE）/ `update_session_title`。
- **初手（`POST /sessions`）**: 単発 QA と同じ `retrieve` → `build_chat_context_block` → `build_chat_system_message` で system を作り、session 作成 + system/user を append → `stream_chat([system, user])` を SSE。終端で assistant を append。
- **続行（`POST /sessions/{id}/messages`）**: `load_chat_messages`(system + 履歴) + 新 user を投入 → SSE → assistant append。scope=book かつ full-book モードなら `num_ctx` を上書き。
- **KV cache**: 続行ターンは同じ system prefix を再送するため llama-server の KV cache がヒットし、2 ターン目以降が高速化する。
- **backend 制約**: Ollama backend は `stream_chat` 非対応 → `NotImplementedError` を error SSE で 1 度返して終了。詳細（一覧 / タイトル変更 API 等）は [データ設計 §4](小説RAG_データ.md)。UI は system メッセージを応答から除外する。

## 8. 読書会 番組台本生成（`discussion_service.py` ほか）B-28

書籍全文を Qwen 131k コンテキストに投入し、固定ホストキャラ 2 人（レイ＆ミオ）による番組台本を 2 段の LLM 呼び出しで SSE 生成する。B-20（自由ペルソナ 2 人の読書会対話）を置き換えた（要件と設計判断の経緯は [読書会ロングフォーム拡張_要件.md](../../要件定義/読書会ロングフォーム拡張_要件.md)）。

- **モジュール構成**: `discussion_cast.py`（ホスト人格核）/ `discussion_prompts.py`（構成・台本prompt）/ `discussion_parser.py`（plan・turnの純粋parse/validate）/ `discussion_stream.py`（segment/turn event生成）/ `discussion_checks.py`（DoD機械チェック）/ `discussion_repository.py`（history保存・一覧・削除）/ `discussion_service.py`（application orchestrationと互換公開面）。
- **2 段パイプライン**:
    1. **構成ステップ** (`generate_plan`): 書籍を読ませて構成メモ JSON（対立する 2 つの推し解釈 `stances`・テーマ 2 件・脱線ネタカード 2〜3 枚 [facts=正確な固有情報 / keywords=言及判定用]）を生成。`temperature=0.4 / num_predict=2048`。LLM の JSON 出力は確率的に崩れるため、パース・バリデーション失敗時は同一プロンプトで最大 3 回まで自動リトライする（`_PLAN_MAX_ATTEMPTS`。KV cache が効くため再試行は安価）。
    2. **台本ステップ** (`stream_discussion_turns`): 番組構成（OPフック→テーマ1→テーマ2→脱線→締め、セグメント別ターン数指定）で台本を SSE ストリーミング。`temperature=0.7 / num_predict=8192`。
    - **KV cache 最適化**: 両呼び出しの system プロンプト先頭（課題本 + 小説本文の `_COMMON_PREFIX`）を完全一致させ、llama-server の prefix cache により 2 段目の prompt processing をほぼゼロにする。
- **台本品質指示**: 台本全体に「笑える / へえ」の山を最低 4 箇所設け、ボケ / ツッコミをテーマごとに交代する。トリビアの直後には相手の反応を続け、レイの年下キャラへの甘さとミオのカップリング語りは脱線時の小ネタに限定する。1 ターンは 20〜200 字（大半は 80〜150 字）、全体は 3,000〜3,800 字を目標とし、3,800 字超では後続を刈り込んで 4,500 字の機械チェック上限を超えないよう指示する。
- **パーサ**: ターンマーカーは表記揺れ許容（`[A]:` / `[A>:` / `[A]：` 等）。セグメント境界は `[S:segment_id]` 行を逐次検出し `segment` イベント化（チャンク分断による ID 誤検出のガードあり）。
- **機械チェック（DoD 層1）**: 生成完了時に `run_checks` で M1 字数 3,000〜4,500 / M2 5 セグメント出現 / M3 話者分割成功 / M4 言語リーク 0（簡体字 64 字セット + 4 字以上英字。正規作品名 `BLEACH` / `Fate/Grand Order` は許容）/ M5 ネタカード言及 を判定し、done イベントと保存 JSON に含める。不合格時は UI から再生成する運用（全保存 + 削除ボタン）。
- **SSE イベント**: `status(stage=planning|scripting)` → `segment(id,title)` / `turn(speaker,text,segment)` → `done(saved_path, checks)`。エラーは `error(message)`。
- **保存（format_version 2）**: `data/kindle_novel/discussions/{書籍名}/{JSTタイムスタンプ+0900}.json` に cast スナップショット（人格核 + 当回の stance）/ segments / cards / turns（segment 付き）/ checks を保存。旧 v1 JSON（personas/turns のみ）も `list_discussions` が互換で読める。クライアント切断時は保存スキップ。
- **API**: `POST /api/novel/discussion/generate`（body は `{book_name}` のみ）/ `GET /history` / `DELETE /history/{filename}?book_name=`（filename 正規表現 + resolve/is_relative_to のパストラバーサル対策）。

---

## 9. 既知の制限

- **応答時間**: Qwen3.6 の QA は 80〜130 秒（full-book は ~170 秒）。SSE ストリーミングで体感を緩和。
- **キャラ帰属の誤統合**: `main_characters` ヒント + プロンプト帰属ルールで低減したがゼロにはできない（残存課題）。
- **OCR ミス**: bge-m3 の意味距離で一部吸収するが完全ではない。頻出ミスは書籍単位の再 OCR + 再構築で対応（辞書置換は導入しない）。
- **俯瞰質問の天井**: B-5 / B-8 / B-9 の三段改善で緩和済み。改善史の詳細は [設計過程](../../../archive/小説RAG_設計過程.md)。

---

## 10. 日本語検索基盤の比較検証ゲート

大量の日本語 OCR 本文に対する検索方式の変更は、生成 LLM の比較とは分離し、次の順序で
評価する。先に低コストな候補生成を改善し、その候補集合に対する reranker、最後に全件の
再 embedding が必要なモデル比較へ進む。

1. **Gate 0 — 隔離コーパスと正解集合**
    - Linux の検証済みバックアップを Mac の一時領域へ複製し、SQLite は read-only URI で開く。
      LanceDB を含め、本番パス・バックアップ原本・公開成果物は更新しない。
    - `PRAGMA integrity_check=ok`、books / pages / chunks / LanceDB 各テーブルの件数、評価元
      snapshot を結果 JSON に記録する。SQLite chunks と LanceDB chunks の件数差は、評価対象の
      indexed book / page と対応づけて説明できない限り fail closed とする。
    - 正解集合は本文を保存せず、query / scope / 関連する `(book_name, page_no)` / relevance grade
      のみを機械可読 fixture に持つ。既知 6 問を seed とし、本番採否前に 3 冊以上・20 問以上へ
      拡張する。検索結果を見てから同じ問の正解を変更しない。
2. **Gate A — lexical retrieval**
    - 現行 SQLite FTS5 trigram + phrase OR を基準線とし、隔離 LanceDB に page 本文の FTS index を
      作って ICU BM25 と ngram(2–3) BM25 を同一条件で比較する。
    - Recall@5 / Recall@10 / MRR@10 / nDCG@10、query latency p50 / p95、index build time / size を
      記録する。既知正解の Recall@10 を 1 件でも悪化させず、既知の 0-hit を救済し、p95 が
      200 ms 以下の方式だけを次段の候補生成器に残す。
3. **Gate B — reranker**
    - まずGate Aの高recall診断候補（ICU + ngram RRF top 30）と現行bge-m3 top 30の和集合で
      candidate coverageを確認する。2026-08-22のfixtureではbge-m3が新しい正解ページを追加しなかった
      ため、実際のreranker入力はICU + ngram RRF top 30へ固定し、`Qwen3-Reranker-0.6B`を600 pairで
      比較した。候補集合を変更した再試験では、この被覆診断からやり直す。
    - rerankerは候補外の文書を救済できないため、candidate Recall@30と最終MRR / nDCGを分けて
      記録する。候補被覆用の和集合と、実際にscoreを付ける固定集合を結果JSONへ別々に残す。
    - MRR@10 または nDCG@10 が基準線から相対 5% 以上改善し、Recall@10 が悪化せず、Mac での
      p95 追加時間が 2 秒以下、peak memory が 4 GiB 以下の場合だけ採用候補とする。
4. **Gate C — embedding model**
    - 現行 bge-m3（Mac は MLX FP16 + CLS）を基準線に、PPLX context 0.6B、
      Nemotron-3-Embed-1B、Qwen3-Embedding-0.6B、Harrier 0.6B の順で比較する。
    - model ID / immutable revision / dimension / pooling / normalization / query・document prefix /
      truncation を index manifest に固定する。モデルごとに別の隔離 LanceDB table を作り、現行
      1024 次元 table を上書きしない。次元切り詰めはモデルが公式に対応する場合だけ許可する。
    - MLX の BF16 checkpoint は `numpy.asarray()` へ直接渡さず、MLX 上で FP32 へ明示変換してから
      搬出する。変換後に shape・有限値・非ゼロ norm を検証し、BF16 丸め誤差を FP32 で L2
      再正規化してから FP16 / 量子化 checkpoint と同じ評価器へ接続する。これは Harrier 公式 BF16
      checkpoint で再現する PEP 3118 buffer 非互換と約 0.5% の norm 誤差を吸収する境界処理であり、
      モデル重みや検索スコアの量子化を意味しない。
    - Harrier 公式 BF16 checkpoint が複数入力の特定組み合わせで非有限値を返す場合、単体入力で
      各文書が正常なことを確認したうえで、同じ immutable revision の公式重みをローカルで FP16 へ
      変換した Mac 実行 variant を先に評価する。source / converter version / dtype / 変換後 hash を
      manifest に残し、公式の instruction・last-token pooling・L2 normalization は変えない。第三者
      量子化版は、その provenance と誤った prompt 例を監査せずに代替採用しない。
    - 全文 indexing throughput / peak memory / index size と、同じ Recall・MRR・nDCG・latencyを
      記録する。Recall@10 非劣化かつ MRR@10 または nDCG@10 相対 5% 以上改善を採用条件とする。

### 10.1 評価器と結果の契約

- 評価 CLI は検索ごとの順位・relevance・所要時間と、集約指標を JSON へ保存する。本文・snippet・
  embedding は成果物へ含めない。
- 既知 6 問だけの結果は**診断**であり、本番採否には使わない。3 冊・20 問以上の blind fixture、
  回帰 test 合格を本番ゲートとする。lexical / dense検索は1回のwarmup後に3回を計測し、rerankerは
  model warmupを1回行った後、固定600 pairを決定的に1巡して品質とpair latencyを測る。rerankerへ
  3回の反復計測は要求しない。
- CPU だけで完了する Gate 0 / A を先に実行する。GPU / Metal を使う Gate B / C は他の推論 process
  がないことを確認し、一度に1モデルだけ起動する。この排他確認はoperatorの実行前条件であり、
  現評価CLIは他processの停止を自動強制しないため、確認結果を実行記録へ残す。
- Gate B / C の比較中は既存 API 型、`rrf_score`、`NOVEL_DB_*`、production DB / index を変更しない。
  採用決定後にのみ、query/document adapter、index manifest、rerank score と fallback を別変更として
  設計する。失敗時の rollback は隔離 table / checkpoint / 結果ディレクトリの破棄で完了する。

### 10.2 2026-08-22 実測結果と採否

評価は snapshot `2026-08-22_020001` の読み取り専用コピー、検索結果を見る前に固定した20問・
関連6冊の fixtureで実行した。SQLite全体は81冊・9,913ページで、page全文を使うlexical indexは
index対象8,576ページをすべて含む。一方、既存dense corpusの6,238チャンクは32冊・3,060ページだけを
覆っており、dense用chunkが存在しない正解ページも2件ある。dense単体の上限とlexical比較を混同せず、
全書籍を覆う索引として扱わない。

元バックアップのLanceDB `chunks` は3,489行・3,457 unique ID・重複32行・SQLiteから欠落2,781 ID・
19冊だけで、整合性ゲートを通らなかった。このtableは基準線にも再利用せず、以下はすべて隔離領域に
新規作成したtableの結果である。

#### Gate A — lexical

| 方式 | R@5 | R@10 | R@30 | MRR@10 | nDCG@10 | p95 | build / size | 判定 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 現行FTS5 trigram + phrase OR | .090 | .090 | .100 | .075 | .075 | 0.291ms | 既存 | 不採用 |
| LanceDB ICU BM25 | .782 | .886 | .950 | .720 | .708 | 2.120ms | 2.45s / 26.1MB | **採用候補** |
| LanceDB ngram(2–3) BM25 | .686 | .811 | .963 | .696 | .682 | 2.755ms | 7.66s / 113.2MB | R@10回帰1件 |
| ICU + ngram RRF | .694 | .898 | .963 | .685 | .701 | 5.105ms | 上記2索引 | R@10回帰1件 |

現行FTS5の低値はSQLite一般の限界ではなく、trigram tokenizerへ長いphraseをORするquery構築との
組み合わせで18/20問が0-hitになったことによる。最終順位は個別回帰がなく、R@5、MRR、nDCGも最良の
LanceDB ICUを採用候補とする。ngramとRRFはreranker用の高recall診断候補に限る。

#### Gate B — reranker

ICU + ngram RRF top 30（candidate R@30 `.963`）の600 query-page pairを
`Qwen3-Reranker-0.6B-4bit` revision `5f324548f1d20c2b5a450f126fc6ef2fb1126524`で再順位付けした。
事前にこの候補とbge-m3 top 30の和集合も診断したが、bge-m3が追加した正解ページは0件だったため、
rerankerのscore対象は上記600 pairへ固定した。
R@5 `.694 → .822`、R@10 `.898 → .903`、MRR `.685 → .816`、nDCG `.701 → .790`と平均値は
改善したが、`bureaucrat_prevents_war` と `matthias_murder_truth` のR@10が悪化したためfail closedで
不採用とする。600 pairで333.8秒、1 pair p95 846ms、MLX peak 1.73GBで、失敗理由は64GB不足や
速度上限ではなく個別recall回帰である。

#### Gate C — embedding

| dense方式 | dim | R@10 | R@30 | MRR@10 | nDCG@10 | 検索p95 | 全件生成 | MLX peak | bge比ゲート |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| bge-m3 FP16 | 1,024 | .669 | .804 | .595 | .536 | 6.09ms | 7分47秒 / 13.37件/s | 2.12GB | 基準 |
| PPLX context 0.6B | 1,024 | .707 | .829 | .517 | .486 | 6.21ms | 30分17秒 / 3.43件/s | 2.11GB | 不合格 |
| Nemotron-3-Embed-1B 8bit | 2,048 | .744 | .854 | .643 | .601 | 8.24ms | 31分44秒 / 3.28件/s | 2.17GB | **合格** |
| Qwen3-Embedding-0.6B 8bit | 1,024 | .769 | .844 | .569 | .569 | 5.33ms | 14分15秒 / 7.30件/s | 1.63GB | nDCGのみ合格 |
| Harrier 0.6B local FP16 | 1,024 | .707 | .844 | .569 | .522 | 5.28ms | 10分20秒 / 10.07件/s | 2.13GB | 不合格 |

全方式で入力切り詰めは0件だった。Nemotronはbge-m3比でR@10個別回帰0件、MRR +8.17%、nDCG
+12.19%となり、denseモデル中で唯一両方を5%以上改善した。ただしICU + Nemotron RRFはR@10
`.854`でICU単体`.886`を下回る。さらにICU + ngram top 30へNemotron top 30を和集合しても新しい
正解ページは0件、candidate R@30は`.963`のまま、平均候補数だけ30から43.05へ増えた。

Qwen3はbge比で個別R@10回帰0件かつnDCG +6.14%の形式条件を満たすが、MRRは-4.25%でNemotronと
ICUの両方に劣る。Harrier公式BF16は特定の複数入力batchで非有限値を返したため、公式revision
`f9b9dc8d367d443f2479d27aa5d8d2850c0774ee`から`mlx-embeddings 0.1.0`でlocal FP16を生成した。
問題の16件で元BF16単体とのcosineは最小`.99991`、token IDは完全一致し、FP16は全件完走したが
検索品質ゲートは不合格だった。

#### 現時点の決定

- 本番候補生成は**LanceDB ICU BM25単体**を第一候補とする。既存LanceDBは流用せず、全対象pageからの
  世代別完全再構築、SQLite revision / ID / 件数 / hash / index統計の検証、障害時FTS5 fallback、
  API回帰testを実装した。初期既定値は`fts5`を維持し、`shadow`観測を通過するまでICU順位を返さない。
- denseを将来置換する場合の第一候補はNemotron-3-Embed-1B 8bitだが、現fixtureではlexical候補へ
  正解を追加せず、2048次元で索引が約2倍、全件生成も31分44秒かかるため、現時点では本番採用しない。
- Qwen3 reranker、PPLX、Qwen3 Embedding、Harrierは本番配線しない。評価checkpointと一時tableは
  診断用に限る。既存API型、dense配線、`chunks` / `summaries` tableは変更しない。

### 10.3 B-37 rollout状態

実装段階は次の3段に分ける。

| 段階 | `NOVEL_DB_LEXICAL_BACKEND` | 利用者へ返すlexical順位 | 完了条件 |
|---|---|---|---|
| 0. rollback / 初期既定 | `fts5` | SQLite FTS5 | index未構築でも従来動作、全回帰test合格 |
| 1. shadow | `shadow` | SQLite FTS5 | 世代build後、実queryでerror率・p95・上位重複を観測。本文・queryはlogしない |
| 2. ICU候補 | `lance_icu` | ICU。利用不能時のみFTS5 | 未調整holdoutを含む個別Recall非劣化、API互換、障害注入、運用rollback確認後に別途承認 |

この変更の完了範囲は段階1までであり、production既定値の段階2切替は含まない。LanceDB dependencyは
検証済みAPIを保つため`>=0.34,<0.35`へ制約し、minor更新時もGate Aとindex障害testを再実行する。
設計判断は[ADR-0020](../../基本設計/ADR/0020_page-level-lancedb-icu-shadow.md)を参照する。

shadow観測はproductionの`backend/data/logs/app.log*`から対象期間だけを取り出し、次で集計する。

```bash
cd backend
grep -hE 'lexical shadow|lexical ICU fallback' data/logs/app.log* \
  | uv run python scripts/summarize_lexical_shadow.py --since 2026-08-22T00:00:00
```

出力はschema version付きJSONとし、shadow成功 / unavailable件数・率、unique query数、FTS5 / ICUの
p50 / p95 / max latency、0-hit件数、成功時top集合のJaccard平均 / p50 / 最小値、段階2で発生した
`lance_icu` fallback件数を含む。query本文とquery hash一覧は出力しない。shadow観測が0件なら
`status=insufficient_data`を出して終了code 2とし、採用ゲートを通過させない。smoke・障害注入ログは
実運用期間と分けて入力し、未調整holdoutの品質評価とは別の運用証跡として保存する。

#### 2026-08-22 production stage 1 実行記録

- deploy commitは`c31822f`。writerは各停止境界で`rebuild_jobs=0` / `ocr_runs=0`を確認し、snapshot
  `2026-08-22_141238_pre-deploy`を作成後、SQLite 3種とLanceDB `chunks=3,489` / `summaries=18`を
  別directoryへ復元検査した。
- active releaseは`/opt/pic2pdf-viewer/backend-20260822141221-47136`、直前releaseは
  `/opt/pic2pdf-viewer/backend-pre-release-20260822141202-2749904`。LanceDB 0.34.0、qwen-commonの
  世代source、backend import、既存FTS5、service / root / novel books HTTP probeが合格した。
- page table `pages_icu_r0_94f0bfab5239_1787375595960524766`は8,576行、ICU FTS index 1件、
  source hash / active pointer / row数が一致した。既存`chunks` / `summaries`は変更していない。
- corpusから決定的に導出した非0-hit 5 probeではICU追加時間がwarm時3.205〜14.047ms、例外0件。
  FTS5件数は18〜20、ICU件数は0〜20、top 20集合の重複は0〜16で、実方式差が観測できた。
  これはholdout品質評価ではなく運用smokeであり、段階2の採否には使わない。
- selectorをinstrumentした5/5 probeで、`shadow`が同じ呼出し内のFTS5 list objectをそのまま返すことを
  確認した。ICUを意図的に例外化した障害注入でも19件のFTS5結果を返し、service error logは0件だった。
- 集計CLIをproduction `app.log`へ適用し、14:15〜14:17のsmoke 10件は成功10 / fallback 0、
  unique query 5、FTS5 p95 0.711ms、ICU p95 19.848ms、top集合Jaccard平均0.183254、ICU 0-hit 2件だった。
  14:17〜14:18の障害注入1件はfallback率1.0として別集計できた。14:18以降の実利用観測は0件で
  `insufficient_data`・終了code 2となるため、production shadow観測ゲートは未合格のままとする。
- FTS5の順位契約はBM25 score昇順を第一キー、canonical `pages.id`昇順を第二キーとする。
  score同点時だけ一意なpage IDで順序を固定し、production検索と評価CLIで同じSQLを使う。これにより
  別connection / restartを跨ぐtop-k比較を決定的にし、shadow overlapから順序noiseを除く。

2026-08-22の実装後統合試験では、固定SQLiteのread-only原本から別scratchへ複製し、既存Alembic
0013から0014へupgradeして8,576ページを構築した。固定20問のtop 30順位は旧隔離ICU評価と20/20で
完全一致し、`num_indexed_rows=8,576`、`num_unindexed_rows=0`、SQLite integrity `ok`、canonical検索
p95 `13.239 ms`だった。原本SQLite SHA-256は試験前後で不変。scratch約414MBは試験後にゴミ箱へ移した。

### 10.4 固定入力・モデル・再現手順

今回の比較はfixture
`backend/scripts/fixtures/novel_search_eval_v1.json`（SHA-256
`b61f76a2f06e6980c82f9cacab0c78b49230ee6a778c7f404ed9d27d6c1a499e`）と、SQLite
SHA-256 `3040ca3641ae8030aea53b1d0321419e420d2319dc05ee7755763a23ce78e85f`を固定入力とした。
再評価時はsnapshot labelだけで同一性を判断せず、両hashとmanifestを照合する。

| 役割 | 固定モデル / 変換 | immutable revision / provenance |
|---|---|---|
| reranker | `mlx-community/Qwen3-Reranker-0.6B-4bit` | `5f324548f1d20c2b5a450f126fc6ef2fb1126524` |
| dense基準 | `mlx-community/bge-m3-mlx-fp16` | `a37eddded9a6a1273a87fb8b0da0d1cdbd98aeec` |
| PPLX | `agentmish/pplx-embed-context-v1-0.6b-mlx` | 変換`51c6d3cb34a9063c363ee5e94ac6ffc851088630` / 公式元`c2fe8bee1aee42534425a1dfa7f976f6c1a5d16b` |
| Nemotron | `mlx-community/Nemotron-3-Embed-1B-BF16-8bit` | 変換`78d1c33d503cafe42fa2b590396a115523445d7c` / 公式元`a5e0f804b9e90a1ca6784ecbf6e41595774fc834` |
| Qwen3 Embedding | `mlx-community/Qwen3-Embedding-0.6B-8bit` | `407ad2329cd30702720aafe83f74a1ba30fdfbca` |
| Harrier | `microsoft/harrier-oss-v1-0.6b` local FP16 | 公式元`f9b9dc8d367d443f2479d27aa5d8d2850c0774ee`、`mlx-embeddings 0.1.0`、変換後weight SHA-256 `e78f6826d6059b7b0a00a3ab16efaffcf1ddcf8a52f394371be2b6233b619b1a` |

再現順序は次のとおりとする。各CLIの必須引数と実行例はscript先頭のdocstringを正本とする。

1. backend環境で`uv run python scripts/eval_novel_search.py`を実行し、Gate 0 / Aのresult JSONと
   隔離lexical tableを作る。
2. repo外の専用MLX venvで`export_novel_embeddings_mlx.py --profile bge_m3`を実行し、backend環境の
   `eval_novel_dense.py`でbge基準を作る。高recall lexical top 30との和集合で候補被覆を先に診断する。
3. bgeが正解ページを追加しないことを確認した同一入力では、専用MLX venvの
   `eval_novel_reranker_mlx.py`へ`lance_icu_ngram_rrf` top 30を渡してrerankerを評価する。
4. PPLX / Nemotronは各専用export script、Qwen3 Embedding / Harrierは
   `export_novel_embeddings_mlx.py`の対応profileで1モデルずつ生成し、その都度`eval_novel_dense.py`を
   bge基準resultと比較してから次モデルへ進む。

result / manifest JSONは本文・snippet・embeddingを含まないため、hash付きの再現記録として保持できる。
一方、読み取り専用SQLiteコピーとlexical LanceDB tableはOCR本文を、NPZとdense用LanceDB tableは
識別子・ページ参照・vectorを含む。これらは隔離scratch成果物としてcommitせず、必要期間後に破棄し、
固定SQLite・fixture・モデルrevisionから再生成する。`/tmp`配下の実体を永続的な正本として参照しない。

評価実装は`backend/scripts/eval_novel_search.py`、`eval_novel_reranker_mlx.py`、
`eval_novel_dense.py`、`export_novel_embeddings_mlx.py`、
`export_novel_embeddings_pplx_mlx.py`、`export_novel_embeddings_nemotron_mlx.py`、回帰testは
`backend/tests/test_eval_novel_*.py`と`test_export_novel_embeddings_*.py`を正本とする。

### 10.5 B-37 未調整holdoutの封印・一回評価

既存20問の正解集合と検索結果を使わず、別シリーズの`後宮の烏`、
`薬屋のひとりごと (ヒーロー文庫)`、`蜘蛛ですが、なにか？`から各4問、計12問を作る。
各書籍で先頭・末尾5ページを除いたeligible page列の20% / 45% / 70% / 85%位置を先に固定し、
その本文と隣接pageだけを読んで自然文query、関連page、3段階relevanceを付与する。方式別の検索順位、
score、hit有無はfixtureをGitへcommit / pushするまで実行しない。

fixture正本は`backend/scripts/fixtures/novel_search_holdout_v1.json`（SHA-256
`8e8b3ccde781e90b2a7a13af21da356163f29a510288a4dbe230e9fba55fc86b`）とする。production page ICUの
source SHA-256と全関連pageの本文SHA-256を同梱し、評価CLIは次を満たさなければindex構築・検索前に
fail closedとする。

- `novel_search_index_state.page_icu`が`active`で、source SHA-256が封印値と一致する。
- fixtureの関連page集合と封印page集合が完全一致し、重複がない。
- 各`book_name / page_no`が一意に存在し、`full_text` SHA-256が封印値と一致する。

封印時のproduction read-only照合ではsource state一致、関連page 27件、本文hash不一致0件だった。
この照合は検索API・FTS5・ICU queryを呼ばず、正解集合とcorpus同一性だけを確認した。

封印後の評価は`current_fts5`とproduction候補と同設定の`lance_icu`だけを、limit 30、warmup 1回、
実測3回で一度実行する。採用条件は個別Recall@10回帰0件、集約Recall@10非劣化、かつMRR@10または
nDCG@10のどちらかが改善することとする。結果を開封したfixtureは採否にかかわらず調整用へ退役し、
同じholdoutを見てquery・正解page・grade・tokenizer・閾値を変更して再採用判定しない。
