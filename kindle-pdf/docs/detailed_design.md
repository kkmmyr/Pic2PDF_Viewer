# Kindle キャプチャツール 詳細設計書

## 1. モジュール構成・クラス設計

### 1.1. `capturer.py`（基底クラス群）

#### `Config`（データクラス）

アプリケーションの全体設定を管理する。

| フィールド | 説明 |
|---|---|
| `KINDLE_WINDOW_TITLE` | 対象ウィンドウタイトル |
| `PAGE_CHANGE_KEY` | ページめくりキー (`'left'`) |
| `WAIT_SEC` / `TIMEOUT_SEC` | 待機・タイムアウト秒数 |
| `CROP_X1` 〜 `CROP_Y2` | キャプチャ時のクロップ範囲（ウィンドウ相対座標） |
| `IMG_OUTPUT_DIR` | 漫画画像の出力先: `backend/data/comic/images/` |
| `PDF_OUTPUT_DIR` | 漫画 PDF の出力先: `backend/data/comic/pdfs/` |

#### `KindleCapturer`（クラス）

- **`find_window()`**: `EnumWindows` API で Kindle ウィンドウを検索しハンドル取得。
- **`setup_window()`**: ウィンドウ最前面化・フォーカス確保。
- **`get_book_title()`**: ウィンドウタイトルから書籍名を抽出し、ダイアログで確認。
- **`capture_loop(title)`**: メインキャプチャループ（画面取得→保存→ページめくり→変化待ち）。
- **`create_pdf(title, image_dir)`**: 連番 PNG から PDF を生成。

#### `AutoConfig`（継承クラス）

フルスクリーン検出用の設定を追加。

| フィールド | 説明 |
|---|---|
| `FULLSCREEN_CROP_TOP` / `FULLSCREEN_CROP_BOTTOM_MARGIN` | 上下の固定マージン |
| `BLACK_THRESHOLD` | 黒帯判定閾値 |
| `SIDE_IGNORE_PX` | 左右 UI（矢印等）を無視する開始オフセット |

#### `AutoKindleCapturer`（継承クラス）

- **`setup_window()` (オーバーライド)**: F11 でフルスクリーム化 → `_detect_boundaries` 実行 → CROP 座標を更新。
- **`_detect_boundaries(img, w, h)`**: 上部・中央・下部の 3 ラインをスキャンし、黒帯を除いたコンテンツ領域を算出。
- **`cleanup()`**: 終了時に F11 でフルスクリーンを解除。

---

### 1.2. `main_manual.py`（固定クロップモード）

`KindleCapturer` を固定クロップ設定で起動するエントリーポイント。ウィンドウサイズ・レイアウトが一定の書籍向け。

### 1.3. `main_auto.py`（漫画用フルスクリーン起動）

`AutoKindleCapturer` を使い、フルスクリーン・自動検出モードで漫画をキャプチャして PDF を生成する。`run_comic.bat` から起動される。

---

### 1.4. `novel_capturer.py`（小説用クラス群）

#### `NovelConfig`（継承クラス）

`AutoConfig` を継承し、小説（白背景）向けの設定を変更。

| フィールド | 説明 |
|---|---|
| `WHITE_THRESHOLD` | 白画素判定閾値（デフォルト `240`） |
| `IMG_OUTPUT_DIR` | 小説画像の出力先: `backend/data/kindle_novel/images/` |

#### `NovelKindleCapturer`（継承クラス）

`AutoKindleCapturer` を継承し以下をオーバーライド。

- **`_detect_boundaries(img, w, h)`**: 黒帯検出の代わりに白背景（全チャンネル ≥ WHITE_THRESHOLD）を基準にテキスト左右端を 10 点スキャンで検出。
- **`capture_loop(title)`**: OCR・PDF 生成を省略し、画像のみを `IMG_OUTPUT_DIR/<書籍名>/` に保存する。

### 1.5. `main_novel.py`（小説キャプチャ起動）

`NovelKindleCapturer` を使い小説をキャプチャするエントリーポイント。`run_novel.bat` から起動される。撮影完了後は管理画面（`/novel/manage`）から OCR ジョブを投入すること。

---

## 2. 処理フロー

### 漫画（`run_comic.bat`）

```
起動 → Kindle ウィンドウ検索 → F11 フルスクリーン
    → ダイアログでタイトル確認
    → 黒帯スキャン → CROP 座標確定
    → キャプチャループ（左キーでページ送り、タイムアウトまで）
    → F11 でフルスクリーン解除
    → PNG → PDF 結合（backend/data/comic/pdfs/<書籍名>.pdf）
```

### 小説（`run_novel.bat`）

```
起動 → Kindle ウィンドウ検索 → F11 フルスクリーン
    → ダイアログでタイトル確認
    → 白背景スキャン → CROP 座標確定
    → キャプチャループ（左キーでページ送り、タイムアウトまで）
    → F11 でフルスクリーン解除
    → backend/data/kindle_novel/images/<書籍名>/ に PNG 保存のみ
        ↓
    管理画面（/novel/manage）で OCR・DB 構築ジョブを投入
```

## 3. 調整パラメータ

| パラメータ | 対象 | 用途 |
|---|---|---|
| `BLACK_THRESHOLD` | 漫画 | 書籍背景が純黒でない場合に調整 |
| `SIDE_IGNORE_PX` | 漫画 | ページ送り矢印位置が変わった場合に調整 |
| `WHITE_THRESHOLD` | 小説 | 背景がオフホワイトの場合に調整 |
