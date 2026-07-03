# OCR 旧 SearchablePDF 設計（凍結: 2026-07-03）

> 📦 本書は OCR設計書 から切り出した、Phase 5 で削除済みの SearchablePDF 生成設計・当時の検証記録。歴史記録として凍結。現行の OCR 設計は [OCR設計書](../design/詳細設計/機能別/OCR設計書.md)。以後編集しない。

---

## 旧フロー（Phase 5 で削除済み）

```
kindle-pdf/batch_ocr.py (削除済み) → YomitokuEngine → kindle-pdf/searchable_pdf.py (削除済み)
→ kindle_novel/pdfs/{書籍名}.pdf
```
`batch_ocr.py` / `searchable_pdf.py` / `start_batch_ocr.bat` は Phase 5（旧 PDF 経路撤去）で削除。

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

## 既知の制限・残課題（SearchablePDF固有）

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
