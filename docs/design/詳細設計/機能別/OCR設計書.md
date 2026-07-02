# OCR設計・改善記録

> status: absorption-pending | last-verified: 2026-05-09
<!-- 吸収予定（設計書ガバナンス再編 G4）。それまで本書が当該機能の正本。 -->

縦書き小説OCR（yomitoku）を用いたSearchable PDF生成の設計と改善記録。

- 関連: [ADR-0003: image-only モード](../../基本設計/ADR/0003_generated-image-only-mode.md)（`generated` ソースは OCR 対象外）、[GPU環境セットアップ.md](../../環境構築/GPU環境セットアップ.md)（`uv` ベースに更新済み）

> **2026-05-09 注記**: novel ソース（`backend/data/kindle_novel/`）については、Searchable PDF を中間成果物として持つ運用から、**OCR テキストを SQLite に取り込み検索・質問応答する新機能** に移行する方針が確定。novel タブの新ビューア仕様は [小説テキスト検索・RAG機能.md](小説テキスト検索・RAG機能_バックエンド設計.md) / [バックエンド設計](小説テキスト検索・RAG機能_バックエンド設計.md) / [フロントエンド設計](小説テキスト検索・RAG機能_フロントエンド設計.md) を参照。

> **2026-05-13 更新**: `ocr_service.py` を `start_batch_ocr.bat` 経由のサブプロセス起動からスレッドベース実装に刷新。`POST /api/ocr/run` は管理画面「OCR」タブから直接 `run_ocr_subprocess` + `_store_ocr_pages` を呼ぶ方式で再び動作する。
>
> **2026-05-17 更新**: `ocr_service._run_ocr()` の全件実行（`target_dir=None`）に skip ロジックを追加。`novel.db` の `books.ocr_done_at IS NOT NULL` な書籍を除外することで、2 回目以降は未 OCR の書籍のみを処理する。全件 OCR 済みの場合は "No books to process (all already OCR'd)." をログ出力して即終了する。

---

## アーキテクチャ概要

**現在の OCR フロー**（管理画面「OCR」タブ経由）:
```
kindle-pdf/main_novel.py  →  kindle_novel/images/{書籍名}/*.png  (キャプチャのみ)
                                          ↓
POST /api/ocr/run  →  job_queue ベース（routers/ocr.py）
  → services/novel_db/extractor.py (run_ocr_subprocess)
  → $OCR_PYTHON ocr_worker.py   # OCR_PYTHON env var（既定: D:\61.tool\common\ocr\venv\Scripts\python.exe）
  → YomitokuEngine.extract_text()
                                          ↓
                              novel.db (books / pages テーブル)
                              ← FTS5 + sqlite-vec でテキスト検索・RAG に利用
```

**OCR 環境変数**（`.env` で設定）:

| 変数名 | 既定値 | 説明 |
|---|---|---|
| `OCR_PYTHON` | Windows: `D:\61.tool\common\ocr\venv\Scripts\python.exe` / Mac: `~/.venv/ocr/bin/python` | OCR venv の Python 実行ファイルパス |
| `OCR_PATH` | `D:\61.tool\common\ocr` | ocr_worker.py サブプロセス内で `sys.path` に追加するパッケージディレクトリ |

**旧フロー（Phase 5 で削除済み）**:
```
kindle-pdf/batch_ocr.py (削除済み) → YomitokuEngine → kindle-pdf/searchable_pdf.py (削除済み)
→ kindle_novel/pdfs/{書籍名}.pdf
```
`batch_ocr.py` / `searchable_pdf.py` / `start_batch_ocr.bat` は Phase 5（旧 PDF 経路撤去）で削除。

### 関連ファイル

| ファイル | 役割 |
|---|---|
| `backend/services/novel_db/extractor.py` | `run_ocr_subprocess` — common/ocr venv を呼び出して画像からテキストを取得 |
| `D:\61.tool\common\ocr\ocr_engine.py` | yomitokuラッパー。テキスト抽出・フリガナ除去・正規化 |
| `D:\61.tool\common\ocr\debug_yomitoku.py` | yomitoku出力構造の診断ツール |

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

## Searchable PDF生成設計 (`SearchablePdfGenerator`)

**ファイル**: `kindle-pdf/searchable_pdf.py`

### テキスト配置方式

OCR結果の各bboxについて縦書き/横書きを判定し、個別に配置する。

```
rect_h > rect_w * 2 (aspect > 2)  →  _draw_vertical_text()
それ以外                            →  _draw_horizontal_text()
```

### 縦書き配置 (`_draw_vertical_text`)

1文字ずつ個別の `TextObject` で配置する（旧: `-90°` 回転+`textOut(全文)` 方式は廃止）。

```python
font_size = max(rect_w * 0.9, 6.0)   # 列幅に合わせる
char_step = rect_h / n                 # 文字数でbboxを等分
for i, char in enumerate(text):
    img_y_baseline = y1 + i * char_step + char_step * 0.8
    pdf_y = page_height - img_y_baseline  # ReportLab座標変換（y軸反転）
```

**旧方式廃止理由**: 50文字超の列で `textOut(全文)` がPDF描画域外にはみ出し、後半が切れていた。

### 横書き配置 (`_draw_horizontal_text`)

```python
font_size = max(rect_h * 0.8, 6.0)   # bbox高さに合わせる
pdf_y = page_height - y2 + rect_h * 0.15
```

---

## 検証結果（2026-04-13）

**対象**: `おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)/008.png`

| 指標 | 改善前 | 改善後 |
|------|--------|--------|
| 出力件数 | 52件（ルビ混在） | **27件（本文のみ）** |
| ルビ除去 | 不完全 | **完全に除去** |
| テキスト断片化 | — | **マージ不要と正しく判定** |
| 長列の切れ | 発生（50文字超） | **修正済み** |

---

## 既知の制限・残課題

### 目次・特殊レイアウトページでのテキスト配置ずれ（未対応）

**対象**: 目次ページ等（例: `おこぼれ姫と円卓の騎士 1/004.png`）

**症状**: デバッグPDFでテキストオーバーレイが画像と大きくずれる。

**原因**: yomitoku検出器が複数列を1 bboxに合体返却する。

| yomitoku返却 | w | h | aspect | 内容 |
|---|---|---|---|---|
| 本文列+ルビ列が合体 | 93px | 384px | 4.1 | 「プロローグ第一章 ヤ二人の円卓の騎士」 |
| 縦書きだがaspect<2 | 82px | 148px | 1.8 | 「あとがきエピローグ」 |

- 合体bbox (w=93): `font_size = 84pt` → 実際の文字サイズ（約30pt）の3倍になり画像外にはみ出す
- aspect<2: 横書き判定になり1行に詰め込まれる

**対応断念の理由**: `searchable_pdf.py` 側でfont_sizeを補正すると通常本文ページの配置が崩れる。
合体bboxを後処理で確実に判別する方法がなく、修正リスクが効果を上回るため対応しない。

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
