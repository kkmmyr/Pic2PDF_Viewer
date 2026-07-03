# 小説 RAG 検索・QA 設計

> status: living | last-verified: 2026-07-03

novel タブのハイブリッド検索・RAG 質問応答・マルチターンチャット・読書会ディスカッションの現在形設計。DB 構築側は [パイプライン設計](小説RAG_パイプライン設計.md) を参照。

**環境変数・スキーマ・LLM backend / port・API 一覧は [データ設計](小説RAG_データ.md) が正本**。本書は重複記載せず、検索・QA の処理フローに集中する。段階拡大（num_ctx PoC→A→B→C・top_k）や俯瞰質問三段改善（B-5/B-8/B-9）の経緯は [設計過程（凍結）](../../../archive/小説RAG_設計過程.md)、実機ベンチ・モデル選定は [技術知見](../../../log/技術知見/小説RAG_技術知見.md)。

検索/QA のコアは `backend/services/novel_db/` の `search.py` / `retrieval.py` / `prompt_builder.py` / `query_expander.py` / `llm.py` / `qa_history.py` / `qa_sessions.py` / `discussion_service.py`、ルーターは `backend/routers/novel_db/{search,qa,chat}.py`。

---

## 1. ハイブリッド検索（`search.py`）

FTS5（BM25）とベクトル（LanceDB KNN）を Reciprocal Rank Fusion（RRF）でページ単位に融合する。

- **Scope**: `Scope(type, id)`。`type` は `all` / `series` / `book`。`_resolve_book_names(scope)`（lru_cache）が対象書籍名リストを返す（`all` は None = 全件、`series` は meta.db から展開、`book` は 1 冊）。空リストなら 0 件。
- **FTS5（`fts_search`）**: `build_fts5_or_query` が質問から 2 文字以上のトークンを抽出し `"t1" OR "t2" …` に整形。`snippet(pages_fts, …, '<mark>', '</mark>', …)` + `bm25()` で取得。`char_count >= min_chars` と先頭/末尾 `body_page_margin` ページ除外を WHERE に、scope を `b.name IN (...)` で適用。
- **ベクトル（`vec_search`）**: 質問を bge-m3 で埋め込み、LanceDB `chunks` を KNN 検索。フィルタ有り時は `k = max(top*5, 50)` を多めに取り、`char_count`・`book_name` を prefilter、`body_page_margin` は取得後にページ番号で後置フィルタ、`_distance` 昇順で top 件。**ベクトルの埋め込みは B-9 適用後 `(contextual_text + 本文)`**（[パイプライン設計 §5](小説RAG_パイプライン設計.md)）なので、語彙一致のない抽象クエリでも位置説明経由でヒットする。
- **RRF 融合（`hybrid_search`）**: FTS/ベクトル各リストの順位で `score += 1/(k_rrf + rank + 1)`（`k_rrf=60`）を `(book_name, page_no)` に加算。FTS ヒットは `sanitize_snippet` 済み snippet、ベクトルのみのヒットは本文先頭 200 字（`html.escape` のみ）。`max_per_book`（scope=all/series 用）で書籍偏りを抑え top 件に絞り、`_fetch_main_characters` で各ページの主要登場人物を JOIN。返り値は `SearchHit{book_name, page_no, snippet, has_highlight, image_url, rrf_score, main_characters}`。
- **snippet サニタイズ（`sanitize_snippet`）**: `html.escape` で全エスケープ後、`&lt;mark&gt;` のみ `<mark>` に復元。フロントは `dangerouslySetInnerHTML` を追加サニタイザ無しで安全に使える。
- **書籍サマリ検索（`search_book_summaries`）B-8**: LanceDB `summaries` テーブルへの KNN（FTS5 は使わない — サマリは抽象表現中心で意味類似が効く）。`[(book_name, distance), …]`。空テーブル時は空リスト（後方互換）。
- **類似書籍（`find_similar_books`）**: 対象書籍のサマリ embedding を取り自身を除く KNN。bge-m3 は正規化済みのため `score ≈ 1 - L2/2`（コサイン近似）。lib.py の類似書籍 API が利用。
- **全ページ読み（`load_all_pages_of_book`）B-13 段階 C**: hybrid_search を bypass し、`min_chars`/`body_page_margin` フィルタ後の全ページを `page_no` 順に `SearchHit` として返す。scope=book の full-book モード用。

**検索フィルタのデフォルト値**（`NOVEL_DB_MIN_BODY_CHARS` / `NOVEL_DB_BODY_PAGE_MARGIN` / `NOVEL_DB_QA_MAX_PER_BOOK` / `NOVEL_DB_QA_TOP_K` 等）は [データ設計 §2](小説RAG_データ.md)。狙いと段階拡大の経緯は [設計過程](../../../archive/小説RAG_設計過程.md)。

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
- 応答パース（`_parse_expansions`）は番号付け・箇条書き記号・前置きラベル・引用符を剥がし、60 字超の説明文行を除外。
- LLM 失敗（接続エラー / 空応答）や `n<=1` 時は `[question]` にフォールバック（通常検索に縮退）。B-9 が chunk 側、B-11 が query 側を強化する直交関係。

## 4. プロンプト構築（`prompt_builder.py`）

LLM 呼び出しとは独立した純関数群。

- **単発 QA（`build_prompt`）**: `PROMPT_TEMPLATE` に、各ページを `[page N, 主要登場人物: …]`（scope=book）/ `[書名 page N, …]`（all/series）ヘッダ + 本文で並べた `context` を差し込む。回答ルールは「根拠ページ番号明記」「発言者・行動者の帰属明示」「別ページのキャラを安易に統合しない」「抽象質問は具体シーン 3 つ以上で構造的に」等。`main_characters` が空ならヒント行は省略。
- **書籍俯瞰サマリブロック（`_build_summaries_block`）**: `book_summaries` があり scope が book 以外のとき、`【書籍俯瞰サマリ】` セクションを先頭に埋め込む（背景知識、根拠はページ抜粋を主とするよう指示）。scope=book では付与しない。
- **チャット用（`build_chat_context_block` + `build_chat_system_message`）B-16**: 本文抜粋 + サマリブロックを 1 文字列にまとめ、`CHAT_SYSTEM_TEMPLATE`（読書補助アシスタント、スコープ説明 + 参照本文）の system メッセージに埋める。質問・回答ルールは system 側に持たせる。

## 5. LLM 呼び出し層（`llm.py` / `_llm_backend.py`）

- **backend シングルトン（`_llm_backend`）**: `QWEN_BACKEND`（LlamaServer, 11435）/ `GEMMA_BACKEND`（Ollama 11434、`NOVEL_DB_GEMMA_BACKEND=qwen` 時は QWEN 流用）/ `QUERY_BACKEND`（Ollama, timeout 60）。`NOVEL_DB_LLM_BACKEND` が `llama_server` 以外だと import 時に `LLMError` で即失敗（Ollama 分岐は Phase C で撤去）。詳細は [データ設計 §5](小説RAG_データ.md)。
- **`LLM_OPTIONS`**: `temperature=0.2 / repeat_penalty=1.2 / num_predict=4096 / num_ctx=NOVEL_DB_QA_NUM_CTX`。**注意: llama-server では `num_ctx` は起動時 `-c` で決まり、ここで渡しても無視される**（実効値の変更は `start-qwen-server.bat` の `-c` を編集）。
- **ストリーミング**: `stream_qa(prompt)` は `QWEN_BACKEND.astream_ask`、`stream_chat(messages)` は `QWEN_BACKEND.astream_chat`（LlamaServer 専用、Ollama は `NotImplementedError`）に委譲。バックエンド分岐・thinking 抑制（`enable_thinking=False`）・SSE→Ollama 形式正規化はすべて共通モジュール `local_llm` 側。`_astream_ask` / `astream_chat` の薄いラッパはテストの monkeypatch 点。イベントは `{response, done, done_reason, eval_count, …}` の Ollama 互換 dict。

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

## 8. 読書会ディスカッション（`discussion_service.py`）B-20

書籍全文を Qwen 131k コンテキストに投入し、2 ペルソナが交互に語り合う対話を SSE 生成する。

- **フロー**: `load_all_pages_of_book` で全ページ取得 → `estimate_book_tokens`（1 token ≒ 1.5 日本語字）が `MAX_INPUT_TOKENS`(112,000) 超なら error SSE で即終了 → `build_messages`（2 ペルソナの system + user）→ `stream_discussion_turns`。
- **ターン分割**: LLM 出力を逐次バッファし `[A]:` / `[B]:` マーカー検出で 1 ターン完結ごとに `{"type":"turn", "speaker", "text"}` を yield。終端で最後のターンをフラッシュ。
- **保存**: 全ターン完了で `save_discussion` が `data/kindle_novel/discussions/{書籍名}/{UTCタイムスタンプ}.json`（personas / turns / created_at）へ保存。クライアント切断時は保存スキップ。`list_discussions` / `count_discussions` で一覧。LLM オプションは `temperature=0.7 / num_predict=8192 / num_ctx=131072`。

---

## 9. 既知の制限

- **応答時間**: Qwen3.6 の QA は 80〜130 秒（full-book は ~170 秒）。SSE ストリーミングで体感を緩和。
- **キャラ帰属の誤統合**: `main_characters` ヒント + プロンプト帰属ルールで低減したがゼロにはできない（残存課題）。
- **OCR ミス**: bge-m3 の意味距離で一部吸収するが完全ではない。頻出ミスは書籍単位の再 OCR + 再構築で対応（辞書置換は導入しない）。
- **俯瞰質問の天井**: B-5 / B-8 / B-9 の三段改善で緩和済み。改善史の詳細は [設計過程](../../../archive/小説RAG_設計過程.md)。
