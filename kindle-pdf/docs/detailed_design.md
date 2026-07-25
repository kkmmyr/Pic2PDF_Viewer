# Kindle キャプチャツール 詳細設計書

## 1. モジュール構成・クラス設計

### 1.1. `capturer.py`（基底クラス群）

#### `Config`（データクラス）

アプリケーションの全体設定を管理する。

| フィールド | 説明 |
|---|---|
| `KINDLE_WINDOW_TITLE` | 対象ウィンドウタイトル |
| `PAGE_CHANGE_KEY` | ページめくり方向 (`'left'` / `'right'`) |
| `EXPECTED_PAGES` | 表紙等を含む期待撮影画面数（空欄時は画面無変化で自動終了）。Kindleの紙面ページ総数は指定しない |
| `WAIT_SEC` / `PAGE_STABLE_SEC` / `TIMEOUT_SEC` | 画面変化のポーリング間隔、描画安定時間、タイムアウト秒数 |
| `PAGE_CLICK_INSET_PX` | Microsoft Store 版の左右ページ送りボタンをクリックする端からの距離 |
| `CROP_X1` 〜 `CROP_Y2` | キャプチャ時のクロップ範囲（ウィンドウ相対座標） |
| `IMG_OUTPUT_DIR` | 漫画画像の出力先: `backend/data/comic/images/` |
| `PDF_OUTPUT_DIR` | 漫画 PDF の出力先: `backend/data/comic/pdfs/` |

#### `KindleCapturer`（クラス）

- **`find_window()`**: `EnumWindows` API で Kindle ウィンドウを検索しハンドル取得。
- **`setup_window()`**: ウィンドウ最前面化・フォーカス確保。
- **`get_book_title()`**: ウィンドウタイトルから書籍名を抽出し、ダイアログで確認。
- **`capture_loop(title)`**: メインキャプチャループ（安定画像取得→保存→ページめくり→変化・再安定待ち）。期待枚数指定時に途中で画面が変化しなければ異常終了し、期待枚数に達した時点で正常終了する。
- **`_next_page()`**: Microsoft Store 版ではウィンドウ左右のページ送りボタンをクリックし、旧 Kindle for PC では選択方向の矢印キーを送る。
- **`_wait_for_stable_page()`**: 直前ページとの差分を検出した後、同一画像が `PAGE_STABLE_SEC` 継続するまで待ち、白い遷移フレーム等を保存対象から除外する。
- **`create_pdf(title, image_dir)`**: 連番 PNG から PDF を生成。

#### `AutoConfig`（継承クラス）

フルスクリーン検出用の設定を追加。

| フィールド | 説明 |
|---|---|
| `FULLSCREEN_CROP_TOP` / `FULLSCREEN_CROP_BOTTOM_MARGIN` | 上下の固定マージン |
| `FULLSCREEN_SETTLE_SEC` | F11 後の新 Kindle 案内トーストが消えるまでの待機時間（実測 `5.0` 秒） |
| `NEW_KINDLE_SETTLE_SEC` | Microsoft Store 版を最大化した後の待機時間 |
| `NEW_KINDLE_CROP_TOP` / `NEW_KINDLE_CROP_BOTTOM_MARGIN` | Microsoft Store 版の上部ツールバー・下部進捗バー除外幅 |
| `NEW_KINDLE_SIDE_IGNORE_PX` | Microsoft Store 版の左右ページ送り UI 除外幅 |
| `BLACK_THRESHOLD` | 黒帯判定閾値 |
| `SIDE_IGNORE_PX` | 左右 UI（矢印等）を無視する開始オフセット |

#### `AutoKindleCapturer`（継承クラス）

- **`setup_window()` (オーバーライド)**: タイトルが厳密に `Kindle` の Microsoft Store 版は最大化し、旧 Kindle for PC は必要な場合だけ F11 で切り替える。実ウィンドウ矩形を取得して `_detect_boundaries` を実行し、マルチモニターでも対象ウィンドウの座標系を使用する。
- **`_detect_boundaries(img, w, h)`**: 上部・中央・下部の 3 ラインをスキャンし、黒帯を除いたコンテンツ領域を算出。
- **`cleanup()`**: ツール自身が最大化または F11 切り替えを行った場合だけ元の状態へ戻す。

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
| `MIN_CROP_WIDTH_RATIO` | 検出幅が安全領域に占める最小比率（デフォルト `0.9`） |
| `DETECTION_PADDING_PX` | 検出境界の外側へ残す余白（デフォルト `10`） |
| `IMG_OUTPUT_DIR` | 小説画像の出力先: `backend/data/kindle_novel/images/` |

#### `NovelKindleCapturer`（継承クラス）

`AutoKindleCapturer` を継承し以下をオーバーライド。

- **`_detect_boundaries(img, w, h)`**: 黒帯検出の代わりに白背景（全チャンネル ≥ WHITE_THRESHOLD）を基準にテキスト左右端を 10 点スキャンで検出。空白行を候補から除外し、検出幅が安全領域の `MIN_CROP_WIDTH_RATIO` 未満なら安全領域全体へフォールバックする。これにより章扉・挿絵・短い段落を開始ページに選んだ場合も後続本文を切らない。
- **`capture_loop(title)`**: OCR・PDF 生成を省略し、画像のみを `IMG_OUTPUT_DIR/<書籍名>/` に保存する。

### 1.5. `main_novel.py`（小説キャプチャ起動）

`NovelKindleCapturer` を使い小説をキャプチャするエントリーポイント。`run_novel.bat` から起動される。撮影完了後は管理画面（`/novel/manage`）から OCR ジョブを投入すること。

### 1.6. `diagnose_new_kindle.py`（実機診断）

Kindle 関連のトップレベルウィンドウを列挙し、キャプチャ対象のタイトル・HWND・矩形、`GetWindowDisplayAffinity`、黒画面率を表示する。Microsoft Store 版の本文ウィンドウ（タイトルが厳密に `Kindle`）をキャプチャ対象として明示し、マルチモニターを含む実座標で画像取得可否を判定する。

---

### 1.7. `kindle_app_controller.py`（Kindle自動操作）

起動済みMicrosoft Store版 Kindleへ接続し、購入済みライブラリから対象書籍を安全に開いて撮影開始位置へ移動する。

- `uiautomation` を使い、検索欄とASIN固有のAutomationIdを限定探索する。
- `library-more-menu-<ASIN>` が一意に見つかった場合だけ対象カードを操作する。
- 未ダウンロード時は `download-button-<ASIN>` を開始し、ボタン消失と正式コンテンツフォルダの安定を待つ。
- 読書画面では `FooterLabelText` の変化停止を3回確認して先頭境界とする。
- Kindleの起動、ログイン、画面ロック解除は行わない。
- 候補なし・複数・UI取得不能・ダウンロード期限超過・先頭移動不能は工程別エラーとして終了し、capturerを起動しない。

### 1.8. `capture_agent.py`（ジョブ実行）

バックエンドから1件ずつjobをclaimし、`KindleAppController`による準備、既存capturerによる全ページ撮影、Samba inboxへの原子的公開、完了APIを直列実行する。処理中はheartbeatを定期送信し、状態を `locating_book → downloading（必要時）→ positioning → capturing → awaiting_files` として通知する。

---

## 2. 処理フロー

### 漫画（`run_comic.bat`）

```
起動 → Kindle ウィンドウ検索 → 新 Kindle は最大化 / 旧 Kindle は F11
    → ダイアログでタイトル確認
    → 黒帯スキャン → CROP 座標確定
    → キャプチャループ（新 Kindle は左ボタン、旧 Kindle は左キー。安定画像だけ保存）
    → ツールが変更した最大化/F11状態だけ復元（起動時フルスクリーンは維持）
    → PNG → PDF 結合（backend/data/comic/pdfs/<書籍名>.pdf）
```

### 小説（`run_novel.bat`）

```
起動 → Kindle ウィンドウ検索 → 新 Kindle は最大化 / 旧 Kindle は F11
    → ダイアログでタイトル確認
    → 白背景スキャン → CROP 座標確定
    → 任意で期待撮影画面数を指定（通常は空欄。紙面ページ総数とは別の値）
    → キャプチャループ（新 Kindle は左ボタン、旧 Kindle は左キー。安定画像だけ保存）
    → ツールが変更した最大化/F11状態だけ復元（起動時フルスクリーンは維持）
    → backend/data/kindle_novel/images/<書籍名>/ に PNG 保存のみ
        ↓
    管理画面（/novel/manage）で OCR・DB 構築ジョブを投入
```

## 3. 調整パラメータ

| パラメータ | 対象 | 用途 |
|---|---|---|
| `BLACK_THRESHOLD` | 漫画 | 書籍背景が純黒でない場合に調整 |
| `FULLSCREEN_SETTLE_SEC` | 漫画・小説 | F11 後の案内トーストが残る場合に調整 |
| `PAGE_STABLE_SEC` | 漫画・小説 | ページ描画の中間フレームを除外する安定待ち時間 |
| `NEW_KINDLE_CROP_TOP` / `NEW_KINDLE_CROP_BOTTOM_MARGIN` | 漫画・小説 | Microsoft Store 版の上下 UI 除外幅 |
| `NEW_KINDLE_SIDE_IGNORE_PX` | 漫画・小説 | Microsoft Store 版の左右 UI 除外幅 |
| `SIDE_IGNORE_PX` | 漫画 | ページ送り矢印位置が変わった場合に調整 |
| `WHITE_THRESHOLD` | 小説 | 背景がオフホワイトの場合に調整 |
| `MIN_CROP_WIDTH_RATIO` | 小説 | ページ内容に依存した過剰クロップを防ぐ最小幅を調整 |
| `DETECTION_PADDING_PX` | 小説 | 検出した本文領域の左右余白を調整 |

## 4. Microsoft Store版 Kindle 実機基準（2026-07-19）

- **検証環境**: Windows、3840×2160モニター、新Kindle本文ウィンドウ（タイトルは厳密に `Kindle`）。最大化後の保存画像は全件1918×3516px。
- **F11を使わない理由**: F11中にページ送りすると、本文描画が全面白のまま復帰しない事象を実測した。最大化ウィンドウでは同じページが正常描画される。
- **入力方式**: 新版は矢印キーが反応しない場合がある一方、左右端から120pxの画面ボタンは安定して反応した。縦書き・右開きでは左ボタンを次画面に使う。
- **描画確定**: ページ送り直後の白い中間フレームを保存しないよう、同一画像が0.75秒継続してから保存する。無変化時はページ送りを1回再試行し、再度無変化なら末尾とする。
- **ページ数の意味**: Kindleの `ページX/265` は紙面ページ番号であり、画面送り回数ではない。検証書籍では表紙から最終画面まで97画像だった。連番対応は `001=表紙`、`002=紙面ページ1`、`097=紙面ページ265の末尾ロゴ画面`。
- **完走実測**: 同じ開始位置から2回取得し、同番号画像のpHash差は中央値0・最大2/64。正式結果は連番97件、SHA-256重複0件、全面白0件、最終UI表示 `ページ265/265・100%`。
- **運用上の排他**: 自動取得中はKindle・マウス・キーボードを操作しない。操作が入った可能性のある結果は正式フォルダと分離して再取得する。
