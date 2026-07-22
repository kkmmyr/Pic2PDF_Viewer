# OCR設計・改善記録

> status: living | last-verified: 2026-07-19

縦書き小説を Surya OCR 2 でテキスト化し、ページ欠落を検査してから `novel.db` へ確定する設計。yomitoku は比較・後方互換用エンジンとして残す。

- 関連: [ADR-0003: image-only モード](../../基本設計/ADR/0003_generated-image-only-mode.md)（`generated` ソースは OCR 対象外）、[GPU環境セットアップ.md](../../環境構築/GPU環境セットアップ.md)（`uv` ベースに更新済み）
- OCR結果の取り込み先（novel.db・検索・RAG）は [小説RAG パイプライン設計](小説RAG_パイプライン設計.md) / [検索QA設計](小説RAG_検索QA設計.md) を参照。

---

## アーキテクチャ概要

**現在の OCR フロー**（管理画面「OCR」タブ経由。旧 `ocr_service.py`・スレッド常駐方式は撤去済み）:
```
kindle-pdf/main_novel.py  →  kindle_novel/images/{書籍名}/*.png  (キャプチャのみ)
                                          ↓
POST /api/ocr/run（routers/ocr.py）→ job_queue に enqueue（rebuild_jobs テーブル）
  → job_worker.py（mode="ocr"）
  → ocr_staging.py（実行開始 / 前回の未完了ページを再開）
  → extractor.py (iter_ocr_pages)
  → $OCR_PYTHON ocr_worker.py --manifest <一時JSON>
  → Surya OCR 2（OpenAI互換 llama-server。Windows CUDA）
  → ページ単位の構造・文字領域カバレッジ検査
  → ocr_page_results へページごとにチェックポイント保存
  → 全ページ合格時だけ pages / pages_fts / books.ocr_done_at を一括更新
                                          ↓
                              novel.db (books / pages テーブル)
                              ← FTS5 + LanceDB でテキスト検索・RAG に利用
```
ジョブキュー管理・スキップロジック・API 詳細は [詳細設計書_バックエンド編](../詳細設計書_バックエンド編.md) が正。

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

### 関連ファイル

| ファイル | 役割 |
|---|---|
| `backend/routers/ocr.py` | `/api/ocr/run` `/api/ocr/stop` `/api/ocr/status` — job_queue ベースの OCR ジョブ API。`stop` は待機中ジョブだけをキャンセルする |
| `backend/services/novel_db/extractor.py` | `run_ocr_subprocess` — common/ocr venv を呼び出して画像からテキストを取得 |
| `backend/services/novel_db/surya_ocr.py` | llama-server の起動・HTTP呼び出し・HTML/bbox解析・品質検査 |
| `backend/services/novel_db/ocr_staging.py` | OCR run/page のチェックポイントと二段階確定 |
| `D:\61.tool\common\ocr\ocr_engine.py` | yomitokuラッパー。テキスト抽出・フリガナ除去・正規化 |
| `D:\61.tool\common\ocr\debug_yomitoku.py` | yomitoku出力構造の診断ツール |

---

## Surya OCR 2 実行設計

- **固定資材**: 公式GGUF、mmproj、`llama-server.exe` のパスとSHA-256を運用時に固定し、自動更新しない。
- **サーバー寿命**: OCR worker 起動時に `/v1/models` を確認する。到達不能かつ3パスが設定済みなら `llama-server` をCUDA全層オフロード・parallel=1で起動し、全対象ページで共有して worker 終了時に停止する。既存サーバーへ接続した場合は停止しない。2026-07-19の長時間実測ではセッション後半に壊れた出力・連続不合格が増え、新しいserverセッションで同じ画像が合格へ戻る事象を確認した。ただし劣化開始ページは一定と断定できないため、固定ページ数では区切らない。当面は**本文の壊れた出力または不合格が連続した時点で中断し、workerが所有するserverだけを停止して新規セッションからチェックポイント再開する**。連続数に基づく自動再起動は未実装である。
- **プロンプト**: 公式Surya OCR 2の学習時契約であるHTML+bbox・layout JSON・block HTMLの3プロンプトを改変せず固定する。OpenAI互換APIのマルチモーダルcontentも公式クライアントと同じ**画像→指示文**の順で送る。逆順では各タスクがlayout JSONへドリフトする実測がある。通常はtemperature=0のページ全体OCRを使い、ページ全体OCRが不成立のときだけ公式のlayout→block経路へ切り替える。
- **推論予算**: llama-serverは1並列・context 16,384を基準とし、ページ全体12,288、layout 3,072、blockはlayoutの`count + 100`（64〜8,192）の出力トークン枠を使う。長い縦書き本文を4,096トークンで途中打ち切りしない。
- **原本保持**: キャプチャPNGを加工・上書きしない。再試行用の縮小・コントラスト調整画像はメモリ上だけで生成する。
- **出力保持**: `raw_output`（HTML）、タグとルビ読みを除いた検索用 `full_text`、bbox・品質指標を別々に保存する。
- **限定補助系**: Suryaで不合格になったページ、列重複を検出したページ、または疎ページの限定例外候補だけをyomitokuでも再読する。yomitokuの全blockがconfidence 0.9以上で、構造・重複検査に合格し、原則としてcoverage検査にも合格した場合だけ`yomitoku_adjudication`としてSurya候補を置換する。256文字以下の疎ページは高confidenceを前提にcoverage不足だけを限定免除できる。日本語文字間に混入した単独ASCII空白は除去し、日本語とラテン文字間の意図的な空白は保持する。通常本文はSuryaのみで処理する。

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

構造・coverage・反復検査の合格は、文字単位の完全一致を保証しない。実測では表紙・挿絵入りページ・目次・通常本文の一部に、助詞、小書き仮名、濁点、固有名詞の誤読や読み順のずれが残った。全run合格時は機械判定により`pages`へ自動確定するが、Full Buildを手動投入する前に、前付け全画面、限定例外フラグ付き画面、通常本文の標本を原画像と照合する。特に表紙・挿絵・目次は構造合格だけで内容精度まで保証されたとは扱わない。この目視QAは現状、DB上の公開状態をブロックするワークフローではなく運用手順である。

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

### チェックポイントと確定

- `ocr_runs`: 書籍・エンジン・モデル・入力ページ数・状態・エラーを記録する。
- `ocr_page_results`: ページ番号、画像SHA-256、本文、raw出力、品質フラグ、coverage、試行回数を `UNIQUE(run_id, page_no)` で保存する。
- 同じ書籍・エンジン・モデル・入力ページ数で状態が `running` または `failed` のrunがある場合は、その最新runを再利用する。各 `passed` ページは、そのページ番号の画像SHA-256が現在の入力と一致する場合だけスキップする。変更されたページ、不合格ページ、未処理ページは再実行する。
- 全ページが `passed` かつページ番号と画像SHAが入力manifestに一致した場合のみ、1トランザクションで `books` / `pages` / `pages_fts` を更新してrunを `completed` にする。
- 中断・失敗時は既存の公開済み本文を保持する。新規書籍では中途半端な本文を公開しない。
- `POST /api/ocr/stop` は `rebuild_jobs` の待機中（`queued`）OCRジョブだけを `canceled` にする。実行中ジョブ・OCR worker・llama-serverは停止しない。待機中ジョブがなければ400を返す。実行中の安全な停止とserver更新の自動制御は未実装であり、手動中断時はrunとジョブを理由付きの `failed` として閉じ、ページチェックポイントを次回再開へ残す。

### 2026-07-19 実書籍runの停止時点

- 対象は97画面。run 5を81画面目の永続チェックポイントでユーザー指示により停止した。
- 保存済み結果は合格67、不合格14（画面番号 `4, 39, 58, 60〜69, 74`）。82〜97画面は未処理である。
- 全画面合格条件を満たさないため、`books` / `pages` / FTS / `ocr_done_at` への確定公開は行われていない。
- 次回は同一書籍・エンジン・モデル識別子・入力97件を指定し、各ページの画像SHA-256が一致する合格67件を再利用して、不合格14件と未処理16件だけを新しいserverセッションで処理する。
- server再起動後の再試行では、少なくとも画面4・25・26・39・44・50・52・53・55・56が合格へ回復した。一方、画面4・39・58・60〜69・74は停止時点でも不合格であり、server更新は品質ゲートの代替ではなく回復試行として扱う。
- 全画面yomitoku比較は通常本文で低confidence（実測最小0.06）、誤字、列欠落、隣接画面の混入があり主系にはできない。一方、3画面目の細い縦列は3列ともconfidence 0.993以上で正読したため、現行どおりSurya不合格ページに限定した補助判定に用いる。

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
