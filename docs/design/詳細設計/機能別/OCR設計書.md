# OCR設計・改善記録

> status: living | last-verified: 2026-07-27

縦書き小説を Surya OCR 2 でテキスト化し、ページ欠落検査と画像照合QAを経てから `novel.db` へ確定する設計。yomitoku は独立照合・比較・後方互換用エンジンとして残す。

- 関連: [ADR-0003: image-only モード](../../基本設計/ADR/0003_generated-image-only-mode.md)（`generated` ソースは OCR 対象外）、[GPU環境セットアップ.md](../../環境構築/GPU環境セットアップ.md)（`uv` ベースに更新済み）
- OCR結果の取り込み先（novel.db・検索・RAG）は [小説RAG パイプライン設計](小説RAG_パイプライン設計.md) / [検索QA設計](小説RAG_検索QA設計.md) を参照。

---

## アーキテクチャ概要

**現在の OCR フロー**（管理画面「OCR」タブ経由。旧 `ocr_service.py`・スレッド常駐方式は撤去済み）:
```
kindle-pdf/main_novel.py  →  kindle_novel/images/{書籍名}/*.png  (キャプチャのみ)
                                          ↓
POST /api/ocr/run（routers/ocr.py）→ job_queue に enqueue（rebuild_jobs テーブル）
  → job_worker.py（queue loopの互換facade）
  → job_state.py / job_targets.py / job_executor.py（状態 / 対象選択 / 工程実行）
  → ocr_run_store.py（実行開始 / 前回の未完了ページを再開）
  → extractor.py (iter_ocr_pages)
  → $OCR_PYTHON ocr_worker.py --manifest <一時JSON>
  → Surya OCR 2（OpenAI互換 llama-server。Windows CUDA）
  → ページ単位の構造・文字領域カバレッジ検査
  → ocr_page_results へページごとにチェックポイント保存
  → 全ページ処理後に awaiting_qa へ遷移（公開テーブルは未変更）
  → 必須ページQA + run承認
  → pages / pages_fts / books.ocr_done_at を一括更新
                                          ↓
                              novel.db (books / pages テーブル)
                              ← FTS5 + LanceDB でテキスト検索・RAG に利用
```
ジョブキュー管理・スキップロジック・API 詳細は [詳細設計書_バックエンド編](../詳細設計書_バックエンド編.md) が正。

**Windows OCR agentモード**:

`OCR_AGENT_ENABLED=true`の本番Linuxでは、通常workerは`mode=ocr`のジョブをclaimせず、
Windows agentが共有トークンで1件ずつclaimする。claim時にLinux側が入力連番・SHA-256を確定し、
`ocr_runs`とjob/run対応を作る。Windowsは登録済み画像URLだけを取得し、
ページ結果・heartbeat・完了または失敗をAPIへ返す。Windowsから`novel.db`を直接開かない。

**OCR 環境変数**（`.env` で設定）:

| 変数名 | 既定値 | 説明 |
|---|---|---|
| `OCR_PYTHON` | Windows: `D:\61.tool\common\ocr\venv\Scripts\python.exe` / Mac: `~/.venv/ocr/bin/python` | OCR venv の Python 実行ファイルパス |
| `OCR_PACKAGE_PATH` | `D:\61.tool\common\ocr` | backend設定名。subprocess起動時に `OCR_PATH` として渡し、ocr_worker.py が `sys.path` に追加するパッケージディレクトリ |
| `OCR_ENGINE` | `surya2` | `surya2` / `yomitoku`。本番既定は Surya OCR 2 |
| `SURYA_INFERENCE_URL` | `http://127.0.0.1:8768/v1` | OpenAI互換 llama-server のベースURL |
| `SURYA_MODEL` | `surya-ocr-2` | APIへ渡すモデル名 |
| `SURYA_MODEL_REVISION` | `unversioned` | model/mmproj/llama.cpp固定版の監査文字列。`ocr_runs.model`へ保存 |
| `SURYA_LLAMA_SERVER_PATH` | 未設定 | 自動起動する `llama-server.exe`。URL到達済みなら不要 |
| `SURYA_MODEL_PATH` | 未設定 | 固定した公式 Surya OCR 2 GGUF |
| `SURYA_MMPROJ_PATH` | 未設定 | 固定した公式 mmproj GGUF |
| `SURYA_REQUEST_TIMEOUT_SEC` | `600` | 1ページの推論タイムアウト |
| `SURYA_MAX_ATTEMPTS` | `3` | ページ全体OCRで比較する画像候補の最大試行数 |
| `OCR_QUALITY_MIN_INK_COVERAGE` | `0.85` | OCR bbox が覆う文字候補成分の最低比率 |
| `OCR_CROSSCHECK_ALL_PAGES` | `true` | Surya合格ページもyomitokuで独立再読する |
| `OCR_CROSS_ENGINE_MIN_SIMILARITY` | `0.85` | 正規化本文のエンジン間最低一致率 |
| `OCR_EXTERNAL_CONFIDENCE_MEDIAN` | `0.85` | 補助OCRのblock confidence中央値下限 |
| `OCR_EXTERNAL_CONFIDENCE_WEIGHTED_MEAN` | `0.75` | 補助OCRの文字数加重confidence平均下限 |
| `OCR_EXTERNAL_LOW_CONFIDENCE_CHAR_RATIO` | `0.25` | confidence 0.5未満の文字数比率上限 |
| `OCR_AGENT_ENABLED` | `false` | OCRジョブをWindows agentへ委譲する。本番Linuxだけで有効化する |
| `OCR_AGENT_HEARTBEAT_TIMEOUT_SEC` | `300` | agent heartbeat期限。次回claim時に期限切れjobを失敗回収する |

### 関連ファイル

| ファイル | 役割 |
|---|---|
| `backend/routers/ocr.py` | `/api/ocr/run` `/api/ocr/stop` `/api/ocr/status` — job_queue ベースの OCR ジョブ API。`stop` は待機中ジョブだけをキャンセルする |
| `backend/services/novel_db/extractor.py` | `run_ocr_subprocess` — common/ocr venv を呼び出して画像からテキストを取得 |
| `backend/services/novel_db/surya_ocr.py` | 既存importを維持する互換facade |
| `backend/services/novel_db/surya_types.py` | OCR block・layout・page結果とserver再起動policyのデータ型 |
| `backend/services/novel_db/surya_parsing.py` | 公式promptとHTML/layout/bbox解析 |
| `backend/services/novel_db/surya_quality.py` | coverage・品質flag・補助OCR照合 |
| `backend/services/novel_db/surya_runtime.py` | llama-server寿命管理とOpenAI互換HTTP client |
| `backend/services/novel_db/ocr_staging.py` | 既存importを維持する互換facade |
| `backend/services/novel_db/ocr_run_store.py` | 入力画像SHA検証、run再開、ページ結果チェックポイント |
| `backend/services/novel_db/ocr_page_classification.py` | ページ種別・layout種別の安全側提案 |
| `backend/services/novel_db/ocr_qa.py` | QA対象選定・レビュー・原子的な正式公開 |
| `backend/services/novel_db/job_worker.py` | queue loopと既存テスト拡張点を維持するfacade |
| `backend/services/novel_db/job_state.py` / `job_targets.py` / `job_executor.py` | ジョブ状態永続化、対象解決、mode別工程 |
| `D:\61.tool\common\ocr\ocr_engine.py` | yomitokuラッパー。テキスト抽出・フリガナ除去・正規化 |
| `D:\61.tool\common\ocr\debug_yomitoku.py` | yomitoku出力構造の診断ツール |

---

## Surya OCR 2 実行設計

上記分割は責務境界だけを変更する。prompt、閾値、品質flag、ページ分類、
QA必須条件、正式公開トランザクションは分割前と同一である。
`surya_ocr.py`と`ocr_staging.py`は公開symbolを同一objectのまま再exportし、
既存worker・router・テストのimport契約を維持する。

- **固定資材**: 公式GGUF、mmproj、`llama-server.exe` のパスとSHA-256を運用時に固定し、自動更新しない。
- **サーバー寿命**: OCR worker 起動時に `/v1/models` を確認する。到達不能かつ3パスが設定済みなら `llama-server` をCUDA全層オフロード・parallel=1で起動する。worker所有serverは有限ページ数、連続Surya不合格、または移動窓の不合格率超過で停止し、次のページを新規server世代で再開する。既存の外部管理serverへ接続した場合はworkerから停止しない。server世代、開始ページ、終了理由をstderr監査ログへ残す。
- **プロンプト**: 公式Surya OCR 2の学習時契約であるHTML+bbox・layout JSON・block HTMLの3プロンプトを改変せず固定する。OpenAI互換APIのマルチモーダルcontentも公式クライアントと同じ**画像→指示文**の順で送る。逆順では各タスクがlayout JSONへドリフトする実測がある。通常はtemperature=0のページ全体OCRを使い、ページ全体OCRが不成立のときだけ公式のlayout→block経路へ切り替える。
- **推論予算**: llama-serverは1並列・context 16,384を基準とし、ページ全体12,288、layout 3,072、blockはlayoutの`count + 100`（64〜8,192）の出力トークン枠を使う。長い縦書き本文を4,096トークンで途中打ち切りしない。
- **原本保持**: キャプチャPNGを加工・上書きしない。再試行用の縮小・コントラスト調整画像はメモリ上だけで生成する。
- **出力保持**: `raw_output`（HTML）、タグとルビ読みを除いた検索用 `full_text`、bbox・品質指標を別々に保存する。
- **独立補助系**: 列単位の欠落をSurya単独のbbox coverageだけで見逃さないため、既定ではSurya合格ページもyomitokuで再読する。補助結果はblock confidenceの中央値、文字数加重平均、confidence 0.5未満の文字比率、構造・重複検査で判定する。両方が合格でも正規化本文の一致率が0.85未満なら`cross_engine_disagreement`として不合格にし、一致する補助結果が2%以上長い場合は`external_ocr_more_complete`付きで補助結果を採用する。補助結果が不合格でSuryaだけが合格した場合は`external_crosscheck_unavailable`を残す。256文字以下の疎ページは分布判定合格を前提にcoverage不足だけを限定免除できる。日本語文字間に混入した単独ASCII空白は除去し、日本語とラテン文字間の意図的な空白は保持する。

### ページ品質ゲート

1. 入力PNGが復号でき、ファイル名が `001.png` から欠番のない連番であること。ここでのページ番号はキャプチャ画面番号であり、Kindleが表示する紙面ページ番号ではない。
2. Surya出力に解析可能な `div[data-label][data-bbox]` があり、bboxが正規化座標0〜1000内であること。
3. ページ全体OCRへlayout JSON（`label` / `bbox` / `count`）が返った場合は、文字なしページとして扱わず**タスク種別ドリフト**として検出する。JSONの順序・bboxを使って各blockを切り出し、公式block OCRを実行してHTML+bboxへ再構成する。block OCRが再びlayout JSONを返した場合は本文として保存せず、その候補を不合格にする。
4. 背景色に依存しない局所エッジを文字候補とし、OCR bboxによる coverage が設定値以上であること。単純な暗画素数は黒背景全体を文字と誤認するため使わない。挿絵・飾り枠があるページを一律に閾値緩和せず、全ページOCRが不合格なら検出済みbboxまたはlayout→block経路で再OCRする。
5. 20文字以上の正規化済みblock本文がページ内で完全重複した場合は、別列への幻覚コピーとして不合格にし、bbox単位で再OCRする。
6. 12〜80文字の同一列が4回以上連続する、または1画面の本文が6,000文字を超える場合は反復暴走として不合格にする。
7. 非空の出力に解析可能なblockが1件もない場合は`malformed_output`として、その画像候補の追加Surya再試行を打ち切り、yomitoku補助系へ移す。
8. 空白ページ、または `Image` / `Figure` / `Diagram` / `Blank-Page` 等の非本文ブロックだけのページは本文ゼロを許容し、理由を品質フラグへ残す。
9. ページ全体OCRの不合格時は公式の画素数上限に収めた正規化画像、原画像、コントラスト調整画像を比較する。全候補が不合格なら原画像でbbox単位のblock OCRを1回実行する。layout専用出力が得られない場合も、不合格HTMLのbboxを再利用する。
10. layout→block経路を含む全候補が不合格ならページ状態を `failed` とし、`pages` へ公開しない。fallback採用時は`layout_block_fallback`を品質フラグへ残す。ただし次の限定例外は監査フラグ付きで許容する。
   - 画像・表・目次等が明示された構造化ページで、構造・本文・bboxが正常かつcoverageだけが装飾領域により不足する場合: `structured_page_coverage_exempt`
   - 256文字以下の疎なページで、bbox単位のblock再OCRが成功した場合、または独立画像候補2件の本文が98%以上一致した場合: `sparse_page_block_fallback` / `sparse_page_variant_consensus` を補助照合のトリガーにする。yomitoku補助照合がconfidence 0.9以上で合格して初めて公開可とする。

限定例外では`duplicate_text_block`、不正bbox、空本文等を許容しない。全run完了後は例外フラグのページを原画像と突き合わせてスポット確認する。

Suryaのblock OCRは、極端に細い日本語縦列の切り出しで中国語混入・幻覚を生じた実測があるため、それ単独では公開可にしない。`sparse_page_block_fallback` / `duplicate_text_recovery`が生じたページはyomitoku補助照合を必須とし、補助照合が不合格ならページも不合格のままとする。

confidence は補助情報であり、列・文章欠落を直接表さないため単独の合格条件にはしない。
yomitoku判定は全blockの最小confidenceだけに依存せず、中央値、文字数加重平均、
低confidence blockの文字比率、構造検査、他エンジンとの一致率を併用する。
低confidence blockを含んでも、独立した品質根拠が揃う場合は監査フラグ付き候補として保持する。
既知の十三歳46画面は最低confidence 0.184、中央値0.907、文字数加重平均0.78、
confidence 0.5未満の文字比率約19%で、短い独立列を含む338文字を取得した。
旧最小値判定では不合格、新分布判定では`external_ocr_distribution_accepted`付き合格となる。

構造・coverage・反復検査の合格は、文字単位の完全一致を保証しない。実測では表紙・挿絵入りページ・目次・通常本文の一部に、助詞、小書き仮名、濁点、固有名詞の誤読や読み順のずれが残った。そのため全ページの機械処理後も`pages`へ自動確定せず、runを`awaiting_qa`へ置く。前付け全画面、限定例外フラグ付き画面、通常本文の標本など必須ページを原画像と照合し、補正または非索引承認を行ったうえでrunを承認する。このQAはDB上の公開をブロックする。

2026-07-26の新規小説2冊・全183画面の実測では、単独実行と全冊実行で
同一SHA-256画像の文字数が952文字から860文字へ変化し、双方がフラグなし合格になった。
人物名の誤読と短い縦列の全欠落もカバレッジ99%以上で合格した。
したがってFull Build前のQA承認をDB上の明示状態として追加し、
QA未承認runは公開・索引生成しない方式へ移行した。
段階実装と受入条件は
[小説OCR品質改善 実装計画](../../../log/計画/小説OCR品質改善_実装計画.md)を正本とする。

以下はPhase 5c導入前の初回本番再実行結果である。茉莉花官吏伝は91/91画面が機械合格したが、
69画面が`external_crosscheck_unavailable`となり、QA必須は73画面だった。
通常本文8画面目の原画像照合で、Suryaの人物名誤読「暗菜莉花」と、
yomitokuの複数の固有名詞誤読を確認した。両者の正規化一致率は0.820であり、
一致閾値0.85未満として停止させる現行判定は妥当だった。

十三歳10巻は88/92画面まで合格し、画像目次、リンク目次、
漢文と書き下しの併記、販促ページの4画面が3回の再試行後も
`cross_engine_disagreement`だった。このため両書籍とも未公開のまま保持する。
`external_crosscheck_unavailable`は、通常本文で補助系が品質根拠を提供できなかった
ことを示すため、QA必須対象から除外しない。

Phase 5cではページ種別分類とレイアウト別候補選択を実装済みである。
2026-07-26の最終再処理では、茉莉花91画面を本文81・画像のみ10、
十三歳92画面を本文81・画像のみ11として全画面承認した。
機械候補147画面、Codex補正文15画面、画像のみ21画面を公開し、
非本文の公開本文混入0件、QA採用本文との不一致0件を確認した。
固定20画面の機械CERは全体16.42%、通常散文1.82%であるため、
機械OCR単独の目標0.5%は未達と明記する。公開品質は機械CERではなく、
固定正解と難ページの原画像照合済み補正、および機械品質ゲート通過候補の
リスクベースQAによって確保する。

### キャプチャ画面番号と紙面ページ番号

- `ocr_page_results.page_no` / `pages.page_no` / 検索結果のページ番号は、PNGファイル名由来の**キャプチャ画面番号**を正とする。
- Kindleの紙面ページ番号はフォント・ウィンドウ幅・リフローの影響を受け、1回の画面送りと1対1対応しない。現状は紙面ページ番号をDBへ別保存しない。
- 2026-07-19の実測書籍では紙面1〜265ページと表紙が97画面へレイアウトされ、`001=表紙`、`002=紙面1`、`097=紙面265の最終画面`だった。
- OCR引用から元画像を開く場合はキャプチャ画面番号で `NNN.png` を参照する。紙面ページ番号として利用者へ表示してはならない。

### OCR投入前の画像QA

1. 正式な書籍フォルダだけを `kindle_novel/images/{書籍名}/` に置く。予備撮影・中断データ・診断画像は `kindle_novel/capture_diagnostics/` 等、`images/` の外へ移す。
2. 数値PNGが1から欠番なく連続していることを確認する。この連番検査はジョブ開始時にも自動実行する。全件復号可能・同一解像度であることは投入前に運用確認する（復号は各ページ処理時にも検査する）。
3. SHA-256完全重複と全面白画像が0件であることを投入前に運用確認する。ジョブは各画像のSHA-256を再開判定に保存するが、書籍内重複・全面白の一括事前検査は自動化していない。
4. 先頭が意図した表紙、末尾がKindleの100%地点であることを目視確認してからOCRジョブを投入する。

### 撮影完了からOCR投入への引継ぎ

- Kindle購入カタログの`capture_state=captured`は正式画像の登録完了を表し、
  OCR・索引の完了を表さない。OCR状態は`GET /api/novel_db/books`の
  `ocr_done_at`、チャンク・Embedding構築状態は`indexed_at`、実行状態は
  `GET /api/ocr/status`と
  `GET /api/ocr/qa/runs`で別々に確認する。
- `is_indexed`は`indexed_at IS NOT NULL`と同義とし、チャンク・Embedding構築の
  完了状態だけを表す。OCR公開済みかつFull Build前の書籍は、
  `ocr_done_at != null` / `is_indexed=false` / `indexed_at=null`となる。
- 複数冊を撮影した運用では、撮影jobの成功時点でOCR対象の書籍名を固定する。
  `POST /api/ocr/run`を対象指定なしで呼ぶと、今回の撮影対象以外の未OCR書籍も
  対象になり得るため、範囲を限定する作業では使用しない。
- OCRは`target_dir`へ書籍名を指定し、1冊ずつキューへ入れる。Windows OCR agentと
  GPU推論を直列利用し、失敗時に後続冊を無条件で進めない。再実行時は同一runの
  ページSHAチェックポイントを利用する。
- OCRの全ページ処理が終わっても、runはまず`awaiting_qa`となる。ページ種別分類、
  必須ページの画像照合・補正、run承認を終えるまで`books` / `pages` / FTSへ
  新しい本文を公開しない。
- 2026-07-27の茉莉花官吏伝シリーズでは、新規撮影した小説8〜17巻の10冊だけを
  OCR対象とする。既存の1〜3巻・18巻の承認済み本文は再処理せず、今回の対象外である
  4〜7巻の未OCR状態も暗黙に巻き込まない。

### 2026-07-27 茉莉花官吏伝8〜17巻の実行結果

- 10冊914ページを直列処理し、全runが`completed / approved`となった。
  806ページを本文として公開し、表紙・目次・人物紹介・挿絵・奥付・広告など
  108ページは画像のみ保持した。全ページの`page_type` / `layout_type`を確定し、
  `unknown`は0件とした。
- 機械OCRの品質判定に失敗した本文15ページは、Codexが原画像で本文範囲と段組みを
  照合し、補助OCR候補を公開正本として採用した。これは文字単位の完全一致を保証する
  ものではなく、固有名詞・ルビ・小書き文字を含む検索結果では原画像確認を残す。
- 自動ページ分類には、14巻p79の本文を目次とする誤判定と、16巻p95・17巻p97の
  あとがき／終章相当を終端位置だけで奥付・広告へ寄せる誤判定があった。終端付近でも
  連続した本文や著者あとがきは索引対象とし、文字量がある非本文候補は画像で再確認する。
- run承認により`books` / `pages` / FTSへの文字起こし公開と`ocr_done_at`更新は完了した。
  8巻を対象とした書籍内検索で「赤奏国 コウマツリカ」がp80ほかへ命中することを
  APIで確認した。
- 8〜17巻はチャンク・Embeddingの`rebuild`を完了し、10冊すべての
  `indexed_at`が非NULLであることを確認した。8巻の上記検索に加え、17巻の
  「茉莉花」がp12ほかへ命中することをAPIで確認した。
- Embedding構築は、サーバーCPUでは8巻が約8分14秒、Windows CPUでは9巻が
  約1分32秒、Windows RTX 5070では10巻が約12秒、11〜17巻が各約6〜8秒だった。
  GPU利用時は`NOVEL_DB_OLLAMA_BASE_URL`だけでなく
  `NOVEL_DB_EMBED_NUM_GPU=99`も必要である。リモートGPUは処理中だけ使用し、
  完了後は本番設定をサーバー内Ollamaへ戻す。
- `full_build`にはチャンク・Embedding以外にQwenによる要約・人物抽出等が含まれる。
  本番のQwen llama-serverが未起動の状態で`full_build`を投入すると失敗するため、
  今回は成功条件を満たす`rebuild`だけを実行した。要約・人物抽出は本文・索引公開を
  ブロックしない独立工程として扱う。

### チェックポイントと確定

- `ocr_runs`: 書籍・エンジン・モデル・入力ページ数・状態・エラーを記録する。
- `ocr_agent_job_runs`: `rebuild_jobs.id`と書籍別`ocr_runs.id`を対応付け、再claim・再開時に同じrunを返す。
- `ocr_runs.qa_state`: `pending` / `approved` / `rejected`。承認者、承認日時、QAメモを同じrunへ保存する。
- `ocr_page_results`: ページ番号、画像SHA-256、採用本文、raw出力、品質フラグ、coverage、試行回数を `UNIQUE(run_id, page_no)` で保存する。`qa_state`は`not_required` / `required` / `approved` / `rejected`、`qa_note`と`reviewed_at`を保持する。ページ種別`page_type`は`unknown` / `narrative` / `toc` / `illustration` / `colophon_or_ad`、`index_eligible`は`narrative`だけ1とする。
- 意味上の`page_type`とは別に、OCR選択用の`layout_type`を`unknown` / `normal_prose` / `full_width` / `mixed_illustration` / `structured` / `image_only`で保持する。Surya候補とyomitoku候補を`primary_text` / `external_text`へ保存し、`selected_engine`は`primary` / `external` / `codex`のいずれを公開正本に採用したかを記録する。Codexまたは人が原画像と照合した補正文は`corrected_text`へ保存し、機械OCRの原文を上書きしない。
- 同じ書籍・エンジン・モデル・入力ページ数で状態が `running` または `failed` のrunがある場合は、その最新runを再利用する。各 `passed` ページは、そのページ番号の画像SHA-256が現在の入力と一致する場合だけスキップする。変更されたページ、不合格ページ、未処理ページは再実行する。
- ページ番号と画像SHAが入力manifestに一致し、全ページのOCR結果（`passed`または`failed`）が保存された場合、runを`awaiting_qa`へ進める。この時点では`books` / `pages` / `pages_fts`を更新しない。`failed`ページは必ずQA対象とし、本文なら画像照合済み補正文、非本文なら画像のみ公開の明示承認が必要である。
- 全ページへ決定論的なページ種別候補を設定する。目次は前付け位置と複数章見出しを
  組み合わせ、長い本文中に現れた単独の「目次」だけでは確定しない。`終章`、
  `エピローグ`、`あとがき`等で始まる長文は終端付近でも本文を優先する。
  奥付・広告は複数の発行語、または終端位置・発行語・短い文字量が揃った場合に限って
  確定する。安全に決まらない場合は`unknown`のまま残す。自動判定は既に手動設定された
  種別を上書きしない。
- OCR時はraw出力のbboxラベル、本文量、非文字領域の有無から`layout_type`を安全側に提案する。`mixed_illustration`ではyomitoku候補を必ず比較し、機械選択後もQA必須とする。`full_width` / `structured` / `unknown`も自動確定せずQAへ送る。通常散文を含め、機械候補に固有名詞・列欠落の疑いがあればCodexが原画像と照合し、`corrected_text`を保存する。
- ページ種別分類は`primary_text` / `external_text` / `selected_engine`を変更しない。
  意味上の索引可否と、レイアウトに基づくOCR候補選択を別々の判断として監査可能にする。
- 先頭7画面、先頭本文・中間・最終画面、OCR失敗、`unknown`または通常散文以外の
  レイアウト、および異常・限定例外を示す品質フラグ付き全画面を`required`とする。
  さらに、300文字以上ある非本文候補を`page_type_text_conflict`、Suryaとyomitokuで
  敬称付き人名・4文字以上のカタカナ語候補に同じ文字数の1文字違いがあるページを
  `named_entity_candidate_disagreement`としてQA必須にする。
  一方の候補にだけ語が存在する場合や、文字数・形が大きく異なる候補はこの規則だけでは
  必須化しない。実データで単純な語集合不一致は過剰検知になるためである。
  `cross_engine_consensus`と`yomitoku_adjudication`は、通常の2エンジン照合を実施した
  監査記録であり、それ単独ではQA必須ページを増やさない。QA画面で原画像・両OCR候補・
  採用本文・フラグ・ページ種別・レイアウト種別を比較し、ページ単位で承認または却下する。
- フロントエンドは`useOCRQaController`がQA run/page選択、TanStack Query、
  承認mutation、候補・補正入力を所有し、`OCRQaPanel`は表示へ限定する。
  API、QA必須条件、候補選択、公開可否は分割前から変更しない。
- `required`ページがすべて`approved`、`rejected`ページ、`unknown`ページ種別、`unknown`レイアウトが各0件で、再度画像SHAが一致した場合だけ、run承認APIが1トランザクションで`books` / `pages` / `pages_fts`を更新し、runを`completed`・`qa_state=approved`にする。`narrative`は機械合格した採用候補または非空の画像照合済み補正文を必須とする。
- 公開後の`pages.page_type`と`pages.index_eligible`はQA確定値を保持する。`toc` / `illustration` / `colophon_or_ad`は画像パスを正本ページとして保持するが、公開本文は空文字にしてFTS検索、chunk、Embedding、全文読込、サマリ、人物・関係抽出の入力から除外する。OCR候補は`ocr_page_results`に監査用として残す。
- 中断・失敗時は既存の公開済み本文を保持する。新規書籍では中途半端な本文を公開しない。
- `POST /api/ocr/stop` は `rebuild_jobs` の待機中（`queued`）OCRジョブだけを `canceled` にする。実行中ジョブ・OCR worker・llama-serverは停止しない。待機中ジョブがなければ400を返す。実行中の安全な停止とserver更新の自動制御は未実装であり、手動中断時はrunとジョブを理由付きの `failed` として閉じ、ページチェックポイントを次回再開へ残す。

### 2026-07-19 実書籍runの停止時点

- 対象は97画面。run 5を81画面目の永続チェックポイントでユーザー指示により停止した。
- 保存済み結果は合格67、不合格14（画面番号 `4, 39, 58, 60〜69, 74`）。82〜97画面は未処理である。
- 全画面合格条件を満たさないため、`books` / `pages` / FTS / `ocr_done_at` への確定公開は行われていない。
- 次回は同一書籍・エンジン・モデル識別子・入力97件を指定し、各ページの画像SHA-256が一致する合格67件を再利用して、不合格14件と未処理16件だけを新しいserverセッションで処理する。
- server再起動後の再試行では、少なくとも画面4・25・26・39・44・50・52・53・55・56が合格へ回復した。一方、画面4・39・58・60〜69・74は停止時点でも不合格であり、server更新は品質ゲートの代替ではなく回復試行として扱う。
- 全画面yomitoku比較は通常本文で低confidence（実測最小0.06）、誤字、列欠落、隣接画面の混入があり主系にはできない。一方、3画面目の細い縦列は3列ともconfidence 0.993以上で正読したため、現行どおりSurya不合格ページに限定した補助判定に用いる。

### 正解コーパス

- `ocr_ground_truth_pages`はrun・画面番号・画像SHA-256を一意キー相当として保持し、OCR結果の変更や画像差し替えを追跡可能にする。
- `reference_text`は原画像と照合した人手確定文字列だけを保存する。OCR本文から初期化した文字列は`draft`であり、評価の正解には数えない。
- 状態は`draft` / `verified`。`verified`への変更は非空の`reference_text`、確定ページ種別、現在画像SHA一致を必須とする。
- 評価は空白を正規化した文字列のLevenshtein距離からCERを計算し、ページ別、
  全`verified`ページの加重CER、ページ種別別の件数・文字数・加重CERを返す。
  全体CERは表紙・目次・挿絵混在・広告の難度に強く影響されるため、
  通常本文の受入可否は`narrative`集計と個別の列欠落を併記して判断する。
- 初期20画面は、通常本文だけでなく表紙、目次、挿絵・章扉、漢文併記、奥付・広告、既知不一致ページを含める。20件を登録しただけでは受入完了とせず、`verified`件数を別表示する。
- コーパスの画像は複製せず正式画像を参照する。画像SHAが変わった項目は検証済み扱いを解除し、再確認する。

#### 固定20画面の実測基準（2026-07-26）

全20画面を原画像と照合して`verified`にした。同じ画像SHA-256と正解本文に対し、
現行Surya系、yomitoku、Tesseract `jpn_vert`を再実行した加重CERは次のとおり。
CERは挿入が正解文字数を超える場合に100%を超え得る。

| 評価範囲 | 画面数 | 現行Surya系 | yomitoku | Tesseract |
|---|---:|---:|---:|---:|
| 全体 | 20 | 16.42% | **11.51%** | 57.20% |
| 通常散文 | 4 | **1.82%** | 4.55% | 8.46% |
| 全幅要約 | 1 | 19.19% | 11.22% | **8.03%** |
| 本文＋挿絵 | 3 | 38.28% | **10.71%** | 151.74% |
| 漢文・書き下し | 1 | **22.64%** | 57.23% | 67.30% |
| 目次 | 4 | 70.00% | **50.00%** | 141.54% |
| 挿絵・表紙 | 4 | **61.24%** | 64.61% | 340.45% |
| 奥付・広告 | 3 | **0.87%** | 21.68% | 65.32% |

- 全体CERだけではyomitokuが最良だが、通常散文と漢文は現行Surya系が優位である。
  主エンジンをyomitokuへ一律置換しない。
- yomitokuの改善は本文＋挿絵に集中した。意味上の`page_type`とは別に
  `layout_type`を保存し、両候補を失わずQAで選択・補正する。
- Tesseractは挿絵の網点・輪郭を大量の文字として誤認した。
  全画面OCRには採用せず、将来文字領域を限定できた場合の列欠落・文字数確認候補に留める。
- 現在の`metrics_by_page_type`は意味上のページ種別を集計する。
  `narrative`には通常散文、全幅要約、本文＋挿絵、漢文が含まれるため、
  受入判断では個別画面と実装計画のレイアウト別集計を併記する。

---

## OCRエンジン設計 (`YomitokuEngine`)

**ファイル**: `D:\61.tool\common\ocr\ocr_engine.py`

### yomitokuが返す構造（実測値）

通常の縦書き小説ページでは `paragraphs` / `lines` は返らず、`words` のみ返る。

```
paragraphs: 0件
lines:      0件
words:     52件（本文列 約30件 + ルビ 約22件）
```

### wordsの分類

| 種別 | width | height | aspect | 例 |
|------|-------|--------|--------|-----|
| 本文列 | 38-48px | 数百〜2000px超 | >10 | 「レティは礼を言い捨て...」（1列全体） |
| ルビ/ふりがな | 18-33px | 27-152px | <6 | 「ぬし」「おおまた」 |

- 本文の各列は**1つのwordとして丸ごと認識**される（断片化は通常起きない）
- ルビ(18-33px)と本文(38-48px)の間に**明確なギャップ（34-37px）**が存在

### フリガナ除去 (`filter_ruby_text`)

ヒストグラムの「谷（valley）」を自動検出して閾値を決定する。

```python
# thickness = width（縦書きドキュメント前提で全word統一）
# ヒストグラムの投票数0のビンを谷として検出
threshold = _detect_valley_threshold(thicknesses)
# 谷が検出できない場合は median * 0.88 にフォールバック
```

**実データでの効果**: ルビ(18-33px)と本文(38-48px)の間のギャップ(34-37px)を自動検出し、ルビを確実に除去。

### テキスト断片化対策 (`_merge_text_fragments`)

通常は断片化が起きないため、aspect比で判定してからマージを実行する。

```python
long_col_count = sum(1 for w in filtered if w['aspect'] > 10)  # 本文列
fragment_count = sum(1 for w in filtered if w['aspect'] < 8)   # 断片
if fragment_count > long_col_count:
    filtered = self._merge_text_fragments(filtered)  # Xビン分割方式
```

### テキスト正規化 (`normalize_text`)

OCR出力に含まれる記号を日本語の正式な記号に変換する。

| 入力 | 変換後 |
|---|---|
| `......` `........` (ASCII `.` 連続) | `……` `………` |
| `·····` (中黒 U+00B7 連続) | `……` |
| `--` `––` (ハイフン連続) | `——` |

---

## 既知の制限・残課題

### 認識精度起因の問題（後処理では解決困難）

- `score=0.00〜0.07` の低信頼度列は文字化けが発生する → yomitokuモデル自体の認識限界
- GPU環境での再処理で改善する可能性あり
- イタリック体・心内語の認識精度が低い

### 未検証: 他書籍でのルビ除去精度

- ルビと本文の幅差が小さい書籍
- ルビなしのページ（全件が本文 → フィルタで誤除去されないか）

---

## GPU環境について

GPU（CUDA）を使用するとOCR処理速度が大幅に向上する。
セットアップ手順: [GPU環境セットアップ.md](../../環境構築/GPU環境セットアップ.md)

---

設計過程・削除済み SearchablePDF 設計は [凍結記録](../../../archive/OCR_旧SearchablePDF設計.md) を参照。
