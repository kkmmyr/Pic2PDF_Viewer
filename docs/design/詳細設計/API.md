# API 仕様

> status: living | last-verified: 2026-07-26

バックエンド (FastAPI) が提供する API のリファレンス方針と、OpenAPI では表現できない設計意図をまとめる。

## この文書の位置づけ

**エンドポイント一覧・リクエスト/レスポンススキーマは OpenAPI が正** — このファイルはエンドポイントを列挙しない。個別の HTTP メソッド・パス・パラメータ・レスポンス例は、実装（`response_model` / Pydantic スキーマ）から FastAPI が自動生成する以下で確認する。

- **Swagger UI**: `http://localhost:8766/docs`（開発時）。リリース／統合モードでもバックエンドポート（`:8090` 相当）で同様に配信されるが、フロントエンドからはリンクしていない。
- **OpenAPI スキーマ**: `http://localhost:8766/openapi.json`

旧 `API仕様書.md` として 1,900 行超のエンドポイント表を手書き維持していた方式は廃止した。実装とドキュメントが乖離するリスクを避けるため、スキーマは常にコードから機械生成されたものを正とする。

JSON エンドポイントはネストした要素を含めて Pydantic の `response_model` を明示し、`list[dict]` / `dict` のまま公開しない。フロントエンドのAPIレスポンス型は `openapi-typescript` で生成した `frontend/src/types/api.d.ts` の `components['schemas']` を参照し、同じ構造を手書きで複製しない。SSE・ファイルダウンロード・204レスポンスはこの対象外とする。

このファイルが記すのは、OpenAPI のスキーマ定義だけでは読み取れない **横断的な設計意図・挙動ルール** のみ。

---

## タイムスタンプ形式（JST 統一）

SQLite に保存・API で返されるタイムスタンプはすべて **JST (Asia/Tokyo, UTC+9)** で格納する。

- **SQLite**: `datetime('now', '+9 hours')` で挿入（スペース区切り `YYYY-MM-DD HH:MM:SS` 形式、タイムゾーン接尾辞なし）
- **Python (backend)**: `datetime.now(ZoneInfo("Asia/Tokyo"))`（`utils.dt.jst_now()` ラッパー経由）
- **フロントエンド**: `utils/date.ts` の `parseSqliteUtc` が `+09:00` を付与して Date 化し、`formatSqliteUtcAsJst` で JST 表示する

> **既存 DB データの注意**: 移行前（UTC 保存時代）のレコードには同様に `+09:00` が付与されるため、9 時間早い表示になる。rebuild / 再生成後のデータから正しい JST 時刻に切り替わる。

---

## novel_db 共通仕様

`novel_db` 配下（検索・QA・履歴・チャット等）のエンドポイントに共通するルール。

- **再構築ジョブ実行中の検索 / 質問**: `503 Service Unavailable` を `Retry-After: 10` ヘッダ付きで返す。
- **共通エラーレスポンス**: `{"detail": "<message>"}` 形式（FastAPI 標準）。
- **スコープオブジェクト (`Scope`)**: 検索 / QA / チャット / 履歴で共通の構造。`{"type": "all"}` / `{"type": "series", "id": "..."}` / `{"type": "book", "name": "..."}` の 3 種。シリーズ未所属書籍は `type=series` の選択肢に含めない。

---

## Kindle 購入カタログ共通仕様

- `/api/kindle-catalog/books` はサーバー側ページングし、`page >= 1`、`1 <= page_size <= 200` とする。
- 初回レガシー移行元と継続取り込み元はサーバー設定から解決し、HTTP で任意パスを受け取らない。
- レガシー移行は preview と commit の二段階とし、commit は短期確認トークンと移行元 fingerprint が一致した場合だけ実行する。
- 画像紐付けは候補取得と確定更新を分ける。候補が一件でも自動確定しない。
- `kindle購入履歴` の画像、表紙パス、表紙キャッシュは API・移行の対象外とする。
- capture job の agent 向け claim / 更新は条件付き状態遷移とし、同一ジョブの二重実行を拒否する。
- agent の claim 応答は capture job と `identity`（ASIN、正式・正規化タイトル、著者、シリーズ、巻）を返す。書誌情報は job 作成時の複製ではなく、claim 時にカタログ正本から合成する。
- 現行 agent の自動工程は `locating_book`、`downloading`、`positioning`、`capturing`、`awaiting_files` を使用する。旧 `waiting_user` は後方互換経路としてのみ受け付ける。
- claim・状態更新・heartbeat は `heartbeat_at` を更新する。次回 claim 時に既定 300 秒の期限を超えた active job を `agent_heartbeat_timeout` で失敗へ回収する。
- `capturing → capturing` の同一状態更新は、撮影済み画面数の進捗反映に限って許可する。`started_at` は初回の撮影開始時刻を保持する。
- 旧手動エージェントとの後方互換用に `claimed → waiting_user → capturing` は読み取り・更新契約として維持するが、現行自動エージェントは使用しない。

詳細なデータ境界は [Kindle 購入カタログ設計](機能別/Kindle購入カタログ設計.md) を参照。

---

## SSE イベントストリーム契約

OpenAPI 上は `text/event-stream` としてしか表現されず中身が読めないため、4 つのストリーミングエンドポイントのイベント形状をここに明記する。

### QA エンドポイント（`novel_db/qa.py`）

- `data: {"token": "..."}` — 部分トークン（生成の都度、複数回）

- `data: {"done": true, "history_id": <int>, "eval_count": <int>, "done_reason": "stop" | "length" | "canceled"}` — 終端イベント（1 回のみ）
  - `done_reason` の enum: `"stop"`（自然終了）/ `"length"`（`num_predict` 到達で打ち切り）/ `"canceled"`（クライアント切断）
  - クライアントが `AbortController.abort()` 等で切断した場合、サーバ側は接続断を検知して `done_reason="canceled"` を確定させ、**そこまでに生成済みの途中経過を `qa_history.answer` へ保存する**（応答を破棄せず、履歴には不完全な回答として残る）

### チャット（マルチターン会話）エンドポイント（`novel_db/chat.py`）

- `data: {"token": "..."}` — 部分トークン
- `data: {"done": true, "session_id": <int>, "message_id": <int>, "eval_count": <int>, "done_reason": "..."}` — 終端（`done_reason` の enum は QA エンドポイントと同一）
- `data: {"error": "..."}` — 失敗（LLM バックエンド未対応・タイムアウト等を含む）

セッション作成 (`POST .../sessions`) と追加ターン (`POST .../sessions/{id}/messages`) のどちらも同じイベント形状を返す。

### ディスカッション生成エンドポイント（`novel_discussion`）

- `data: {"type": "status", "stage": "planning" | "scripting"}` — 構成作成 / 台本生成の開始通知
- `data: {"type": "segment", "id": <int>, "title": "..."}` — セグメント開始通知
- `data: {"type": "turn", "speaker": "A" | "B", "text": "...", "segment": <int>}` — 発言 1 件（完全な発言文として配信され、QA/チャットのような部分トークンではない）
- `data: {"type": "done", "saved_path": "...", "checks": {...}}` — 完了。保存先パスと品質チェック結果を含む。本文が空の場合は `saved_path` / `checks` なしで完了する
- `data: {"type": "error", "message": "..."}` — 失敗

**事前チェック**: 書籍本文全体の推定トークン数を数え、**112,000 トークンを超える場合は生成を開始せずエラー SSE を即座に返して終了する**（部分生成して打ち切ることはしない）。

完了時は発言全件を `kindle_novel/discussions/{book_name}/{YYYYMMDDTHHMMSS+0900}.json` に保存する。クライアント切断によるキャンセル時は保存しない（中途半端な会話ログを残さない）。

### Build / ジョブ進捗ストリームエンドポイント（`novel_build`）

- `data: {"is_running": bool, "current_job": {...} | null, "queued_jobs": [...], "recent_finished": [...]}`

1.5 秒間隔でジョブキューの状態をポーリングし、スナップショットをそのまま配信する（差分ではなく全体状態を毎回送る）。クライアント切断で自動終了する。

---

## 横断的な挙動ルール

個別のスキーマ定義だけを見ても気づきにくい、複数エンドポイントにまたがる挙動をここに集約する。

- **OCR停止APIの対象範囲**: `POST /api/ocr/stop` は、`rebuild_jobs` で `mode="ocr"` かつ `state="queued"` の待機中ジョブをすべてキャンセルする。実行中のOCRジョブ、OCR worker、workerが所有する`llama-server`は停止しない。待機中OCRジョブが1件もない場合は `400 Bad Request`（`{"detail":"No queued OCR jobs to cancel"}`）を返す。エンドポイント名は後方互換のため`stop`だが、実行中処理の停止APIではない。

- **PATCH エンドポイントの部分更新セマンティクス**: フィールドを省略した場合は「変更しない」。指定した場合のみ上書きする（空文字・空配列・`null` を「削除」の意味で使う個別ルールがあるものは各スキーマの `description` を参照）。他フィールド（閲覧履歴・作者情報等）は更新対象でなければ常に保持される。

- **チャットセッション題名更新**: `PATCH /api/novel_db/sessions/{session_id}/title` は `ChatSessionTitleUpdate`（`title: string`）を受け取り、成功時は `204 No Content` を返す。OpenAPIにも同じstatus codeと空bodyを出力する。

- **`view_count` デバウンス**: `POST /api/meta/view` は呼び出しごとに `last_viewed_at` を更新するが、`view_count` は前回の閲覧から `VIEW_COUNT_DEBOUNCE_SEC=300`（5 分）以上経過した場合のみ +1 する（クリック連打によるカウント水増しを防ぐ）。

- **ハイブリッド検索 (RRF)**: `novel_db/search` は FTS5 全文検索とベクトル検索（bge-m3 embedding）の 2 種類のランキングを Reciprocal Rank Fusion で融合する。キーワード完全一致に強い FTS5 と、言い換え・同義表現に強いベクトル検索の両方の強みを単一スコアに反映する。

- **snippet の `<mark>` サニタイズ**: 検索結果の `snippet` はバックエンドで HTML エスケープ済みの上で `<mark>` タグのみをハイライト用に許可する。任意の HTML を許可しないため、フロントエンドは追加のサニタイズなしに `dangerouslySetInnerHTML` で安全に描画できる。

- **`has_highlight` フィールド**: `false` の場合は FTS5 ヒットなし（ベクトル検索のみのヒット）を意味し、`snippet` はチャンク先頭 200 字（`<mark>` なし、HTML エスケープのみ）になる。

- **シリーズ並べ替えの再採番規則**: `series/reorder` は渡された配列の順序どおりに `series_index` を `1.0, 2.0, 3.0, ...` へ振り直す（欠番・重複を許さず常に連番化する。DnD 並べ替え UI からの呼び出しを想定）。

- **Hitomi検出履歴**: `GET /api/hitomi/new-arrivals` は `status=unread|read|all`（既定 `unread`）、`offset`、`limit` を受け付ける。レスポンスは選択状態の `total` と全体の `unread_count` / `read_count` を含む。既読化は `is_read=1` と `read_at` の更新であり、作品行を削除しない。旧 `new_arrivals.json` から移行した既読行は元データに既読日時がないため `read_at=null` のまま保持する。

---

## 認証・セキュリティ

ローカル単一ユーザー向けツールのため認証機構は持たない。信頼モデルの詳細は [セキュリティ設計書](セキュリティ設計書.md) を参照。

## OpenAPI がフロントエンドの型ソースであることの裏付け

`frontend/package.json` の `generate:types` スクリプト（`openapi-typescript http://localhost:8766/openapi.json -o src/types/api.d.ts`）が、`/openapi.json` を型定義の正として自動生成している。バックエンドの `response_model` / Pydantic スキーマを変更すれば、この文書を編集しなくても型は追従する。
