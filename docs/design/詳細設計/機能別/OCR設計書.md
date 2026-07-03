# OCR設計・改善記録

> status: living | last-verified: 2026-07-03

縦書き小説OCR（yomitoku）を用いたテキスト抽出（`YomitokuEngine`）の設計。

- 関連: [ADR-0003: image-only モード](../../基本設計/ADR/0003_generated-image-only-mode.md)（`generated` ソースは OCR 対象外）、[GPU環境セットアップ.md](../../環境構築/GPU環境セットアップ.md)（`uv` ベースに更新済み）
- OCR結果の取り込み先（novel.db・検索・RAG）は [小説テキスト検索・RAG機能_バックエンド設計.md](小説テキスト検索・RAG機能_バックエンド設計.md) / [フロントエンド設計](小説テキスト検索・RAG機能_フロントエンド設計.md) を参照。

---

## アーキテクチャ概要

**現在の OCR フロー**（管理画面「OCR」タブ経由。旧 `ocr_service.py`・スレッド常駐方式は撤去済み）:
```
kindle-pdf/main_novel.py  →  kindle_novel/images/{書籍名}/*.png  (キャプチャのみ)
                                          ↓
POST /api/ocr/run（routers/ocr.py）→ job_queue に enqueue（rebuild_jobs テーブル）
  → job_worker.py（mode="ocr"）
  → services/novel_db/extractor.py (run_ocr_subprocess)
  → $OCR_PYTHON ocr_worker.py   # OCR_PYTHON env var（既定: D:\61.tool\common\ocr\venv\Scripts\python.exe）
  → YomitokuEngine.extract_text()
                                          ↓
                              novel.db (books / pages テーブル)
                              ← FTS5 + LanceDB でテキスト検索・RAG に利用
```
ジョブキュー管理・スキップロジック・API 詳細は [詳細設計書_バックエンド編](../詳細設計書_バックエンド編.md) が正。

**OCR 環境変数**（`.env` で設定）:

| 変数名 | 既定値 | 説明 |
|---|---|---|
| `OCR_PYTHON` | Windows: `D:\61.tool\common\ocr\venv\Scripts\python.exe` / Mac: `~/.venv/ocr/bin/python` | OCR venv の Python 実行ファイルパス |
| `OCR_PATH` | `D:\61.tool\common\ocr` | ocr_worker.py サブプロセス内で `sys.path` に追加するパッケージディレクトリ |

### 関連ファイル

| ファイル | 役割 |
|---|---|
| `backend/routers/ocr.py` | `/api/ocr/run` `/api/ocr/stop` `/api/ocr/status` — job_queue ベースの OCR ジョブ API |
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
