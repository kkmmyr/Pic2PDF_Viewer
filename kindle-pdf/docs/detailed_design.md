# Kindle キャプチャツール 詳細設計書

実機依存の観測値、障害切り分け、再撮影後の品質確認は
[Kindle 自動撮影 実機知見](../../docs/log/技術知見/Kindle自動撮影_実機知見.md)を参照する。

## 1. モジュール構成・クラス設計

### 1.1. 撮影クラス群

`capturer.py`は既存import用facadeとし、実装を次へ分割する。

- `capture_base.py`: `Config`、window操作、手動タイトル確認、PDF作成。
- `capture_loop.py`: 撮影、描画安定判定、ページ送り、連番保存、終了判定。
- `capture_ui.py`: `BookInfoDialog`。
- `comic_capturer.py`: `AutoConfig`と漫画用crop・表示状態復元。

#### `Config`（データクラス）

アプリケーションの全体設定を管理する。

| フィールド | 説明 |
|---|---|
| `KINDLE_WINDOW_TITLE` | 対象ウィンドウタイトル |
| `PAGE_CHANGE_KEY` | ページめくり方向 (`'left'` / `'right'`) |
| `EXPECTED_PAGES` | 表紙等を含む期待撮影画面数（空欄時は画面無変化で自動終了）。Kindleの紙面ページ総数は指定しない |
| `WAIT_SEC` / `PAGE_STABLE_SEC` / `TIMEOUT_SEC` | 画面変化のポーリング間隔、描画安定時間、タイムアウト秒数 |
| `PAGE_VISUAL_DIFF_THRESHOLD` | hover等の微小UI差分を同一画面とみなす平均画素差の上限 |
| `CROP_X1` 〜 `CROP_Y2` | キャプチャ時のクロップ範囲（ウィンドウ相対座標） |
| `IMG_OUTPUT_DIR` | 漫画画像の出力先: `backend/data/comic/images/` |
| `PDF_OUTPUT_DIR` | 漫画 PDF の出力先: `backend/data/comic/pdfs/` |

#### `KindleCapturer`（クラス）

- **`find_window()`**: `EnumWindows` API で Kindle ウィンドウを検索しハンドル取得。
- **`setup_window()`**: ウィンドウ最前面化・フォーカス確保。
- **`get_book_title()`**: ウィンドウタイトルから書籍名を抽出し、ダイアログで確認。
- **`capture_loop(title)`**: メインキャプチャループ（安定画像取得→保存→ページめくり→変化・再安定待ち）。期待枚数指定時に途中で画面が変化しなければ異常終了し、期待枚数に達した時点で正常終了する。表紙から2画面目へ進む最初の遷移に限り、選択済みキーで無変化なら反対キーを1回だけ試し、本文開始後と終端では方向を切り替えない。
- **`_next_page()`**: Kindle の世代にかかわらず、利用者が確定した方向の矢印キーを送る。
- **`_wait_for_stable_page()`**: 直前ページとの平均画素差を検出した後、同等画像が `PAGE_STABLE_SEC` 継続するまで待ち、白い遷移フレームやhover表示等を保存対象から除外する。
- **`create_pdf(title, image_dir)`**: 連番 PNG から PDF を生成。

#### `AutoConfig`（継承クラス）

フルスクリーン検出用の設定を追加。

| フィールド | 説明 |
|---|---|
| `FULLSCREEN_CROP_TOP` / `FULLSCREEN_CROP_BOTTOM_MARGIN` | 上下の固定マージン |
| `FULLSCREEN_SETTLE_SEC` | F11 後の新 Kindle 案内トーストが消えるまでの待機時間（実測 `5.0` 秒） |
| `NEW_KINDLE_SETTLE_SEC` | Microsoft Store 版を最大化した後の待機時間 |
| `NEW_KINDLE_CROP_TOP` / `NEW_KINDLE_CROP_BOTTOM_MARGIN` | controller provider を使わない手動・互換経路だけの Microsoft Store 版上下フォールバック。自動 agent は UI 矩形取得失敗時に停止する |
| `NEW_KINDLE_SIDE_IGNORE_PX` | Microsoft Store 版の左右ページ送り UI 除外幅 |
| `BLACK_THRESHOLD` | 黒帯判定閾値 |
| `SIDE_IGNORE_PX` | 左右 UI（矢印等）を無視する開始オフセット |
| `CAPTURE_SPREAD` | 自動agentの漫画で 2 ページ分の安全幅を確保するか |
| `COMIC_WHITE_THRESHOLD` / `COMIC_MIN_PAGE_ASPECT_RATIO` | 先頭ページの非白色領域と最小 1 ページ幅を推定する閾値 |

#### `AutoKindleCapturer`（継承クラス）

- **`setup_window(reading_area_bounds_provider=None)` (オーバーライド)**:
  タイトルが厳密に `Kindle` の Microsoft Store 版は最大化し、旧 Kindle for PC は必要な場合だけ F11 で切り替える。
  agent 経路では最大化後に provider から `ReadingArea` の画面座標を再取得し、
  実ウィンドウ矩形に対する相対上下境界へ変換する。
  座標確定後は `ReadingArea` 中央を通常クリックし、最大化で外れたキーボード
  フォーカスを読書領域へ戻してから境界検出と撮影を開始する。
- **`_detect_boundaries(img, w, h)`**: 手動互換経路は従来の黒帯検出を使う。
  `CAPTURE_SPREAD` の agent 漫画は、読書領域内の非白色列から 1 ページ幅を推定し、
  その 2 倍以上を中央の見開き安全幅として算出する。
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

公開classはfacadeとして維持し、`kindle_controller/`配下で`models`、`window`、
`library`、`reader`へ責務分割する。

- `uiautomation` を使い、検索欄とASIN固有のAutomationIdを限定探索する。
- 検索欄はUI Automationでフォーカスだけを設定し、通常のキーボード入力後に
  `ValuePattern`を読み戻してASINが完全一致した場合だけ候補探索へ進む。
  表示倍率が異なるマルチモニター環境でも検索欄の矩形クリックには依存しない。
- `library-more-menu-<ASIN>` が一意に見つかった場合だけ対象カードを操作する。
- 読書画面の `backButton` は本人照合済みcontrolへフォーカスを設定し、
  通常のEnterキーでライブラリへ戻る。現行版では座標クリックを受け付けない
  実機差があるため、固定座標や無検証のクリックへ切り替えない。
- 未ダウンロード時は `download-button-<ASIN>` を開始し、ボタン消失と正式コンテンツフォルダの安定を待つ。
- `go_to_start(source, direction)` は `moreMenuButton` → Name
  `ページへ移動する`（旧版は `位置に移動`）の
  メニュー項目 → `go-to-page-input` へページまたはロケーション `1` を入力 →
  `modal-confirm` の直接経路だけを使用する。実機では小説・漫画とも約0.2秒以内に
  先頭付近へ移動できた。
- 高速経路も UI Automation の `SetValue` / `Click` は使わず、
  controlの限定探索とフォーカス設定、通常のキーボード・マウス操作を用いる。
  `attach_running_app()`はWindowsのforeground threadへ一時的にinput queueを接続して
  Kindleを前面化し、`GetForegroundWindow()`が対象handleと一致したことを確認する。
  一致しない場合はcontrol中心をクリックせず`kindle_ui_unavailable`で停止する。
  小説は `FooterLabelText=Location 1 ...・0%` を表紙とする。直接遷移後が
  `ページ1/N・0%` の場合は表紙の次の画面であるため、`ReadingArea` へ
  フォーカスを戻してから逆方向へ1回だけ送り、
  `Location 1 ...・0%` を再確認する。ページ本体よりフッター属性の更新が遅れる
  場合は追加のページ送りをせず、同じ control の更新だけを有界回数待つ。
  2ページ表示の漫画はロケーション `1`を
  指定しても実測上 `Location 2 ...・0%` となるため、source別に検証する。
  経路の要素、入力値、移動結果または補正後の表紙を検証できない場合は
  `positioning_failed` とし、連続ページ送りによる先頭探索は行わない。
  popoverがKindle本体と別のUI Automation rootに公開される場合はデスクトップから
  NameとAutomationIdを限定探索し、control中心がKindleウィンドウ内にあることも
  検証してからクリックする。
- `set_page_layout(source)` は読書領域中央をクリックしてツールバーを表示し、
  `aaMenuButton` から `comic=aaOption-Split` を選ぶ。`novel` は
  `aaOption-Single` が存在すれば選択し、リフロー型書籍でページ数 option が
  存在しない場合は `フォント-item` の存在を確認して単ページ表示として扱う。
  ページ数 option の `ToggleToggleStateProperty` が On にならない場合は
  `positioning_failed` とし、`CloseSideMenuHeaderButton` と読書領域中央の
  クリックで設定 UI を閉じる。
- `capture_area_bounds(source)` は最大化後の撮影矩形を返す。`comic` は
  `ReadingArea` 全体、`novel` は `ReadingArea` の左右端と
  `TopChrome.bottom` / `Footer.top` を合成し、書名とページ・進捗表示を除外する。
  各矩形の包含関係を検証できない場合は撮影を開始しない。
- Kindleの起動、ログイン、画面ロック解除は行わない。
- 候補なし・複数・UI取得不能・ダウンロード期限超過・先頭移動不能は工程別エラーとして終了し、capturerを起動しない。

### 1.8. `capture_agent.py`（ジョブ実行）

バックエンドから1件ずつjobをclaimし、`KindleAppController`による準備、source別ページレイアウトの明示選択、既存capturerによる全ページ撮影、Samba上の論理専用inboxへの原子的公開、完了APIを直列実行する。既存環境では `pic2pdf-input/.kindle-capture-inbox` を利用し、同人誌監視は隠しディレクトリを除外する。処理中は独立threadでheartbeatを定期送信し、状態を `locating_book → downloading（必要時）→ positioning → capturing → awaiting_files` として通知する。

`capture_agent_transport.py`は設定・API・heartbeat、`capture_package.py`はmanifestと
`.partial → .ready`公開、`capture_agent.py`は工程制御とエラー変換を担当する。

- Sambaの一時的な共有違反・アクセス拒否により`.partial → .ready`の同一共有内renameが
  失敗した場合は、コピーやmanifest生成をやり直さず、renameだけを短いバックオフ付きで
  有界回数再試行する。恒常的に失敗する場合は`.partial`を削除して`transfer_failed`とする。
- active job中はcapture agentだけがKindleウィンドウとUI Automationを操作する。
  診断用controllerも接続時にウィンドウ復元・前面化を行うため、読み取り目的でも併用しない。
  監視はcapture job APIとheartbeatに限定し、画像の目視確認はjob完了後に行う。
- controllerの工程別例外コードをjobへそのまま記録し、その他の例外は `capture_failed` / `transfer_failed` / `registration_failed` へ境界別に変換する。
- agent再起動時は途中状態を暗黙再開しない。`awaiting_files` の完了APIだけを冪等再試行し、それ以前の途中jobは失敗として新規job作成を要求する。
- heartbeat送信失敗は停止要求として保持し、次の安全な工程境界または撮影進捗callbackで処理を中断する。
- 読書画面の安定判定と先頭移動は `ReadingArea` の矩形と縮小グレースケール画像の
  差分を用いる。次ページ方向が `left` なら右キー、`right` なら左キーを押し、
  読書領域が変化しない状態を3回連続で確認した位置を先頭境界とする。漫画では
  ツールバー非表示時に `FooterLabelText` を取得できない。ツールバー表示後に
  取得できる場合もあるが、常時存在しないためフッター文字列を必須条件にしない。
- 先頭移動は `set_page_layout(source)` を先に実行し、ロケーション `1` 指定、
  source別の開始位置検証、小説で必要な場合だけ1回の表紙補正の順序とする。
- 撮影は `left` / `right` の矢印キーでページを送る。新Kindleの端部クリックは、
  実測した64pxのchevron領域と既存120px insetが一致せず、ページを送らずに
  hover表示だけを変化させるため利用しない。
- ページ安定判定は完全一致ではなく、画素の平均絶対差が1.0未満のフレームを同一と
  みなす。実機では本文ページ遷移6.82、chevron表示だけの変化0.38で分離できた。
- ライブラリから読書画面へ遷移中、UI Automation が一時的な `COMError` を返す場合は
  対象control未検出として次のpollで再取得する。単発のCOMエラーをジョブ全体の
  `capture_failed` へ昇格させない。
- Kindle 1.0.18632.0 はUI Automationの `SetValue` / `Click` と同時刻に
  `ucrtbase.dll / 0xc0000409` でクラッシュする実測がある。そのためUI Automationは
  controlの識別・矩形取得・検索欄のフォーカス設定だけに使う。検索文字の設定、
  戻る、ダウンロード、書籍オープンは通常のpyautogui操作で実行し、検索値は
  `ValuePattern`による読取専用確認を行う。ウィンドウ前面化は取得済みのネイティブ
  ウィンドウハンドルをWin32 APIへ渡す。固定の画面絶対座標は使わない。

### 1.9. `scripts/capture_kindle_series.py`（シリーズ直列実行）

購入カタログAPIを使い、シリーズの未撮影書籍を安全に1冊ずつcapture agentへ渡す
運用補助スクリプトである。KindleウィンドウやUI Automationには接続しない。

- 既定はdry-runとし、対象タイトル、ASIN、`source`、巻順、撮影状態だけを表示する。
- 実行時はシリーズ検索結果、所有状態、レーベル別`source`、期待総冊数を検証する。
- カタログの誤った`book_type`を使わず、利用者が確定したレーベル対応
  （`ビーズログ文庫=novel`、`プリンセス・コミックス=comic`）を使う。
- `captured`は再撮影せず、`capture_pending`、`multiple_links`、別の未完了jobが
  ある場合は開始しない。
- 小説、漫画の順に巻番号で並べ、1冊分のjobだけを作成する。
- jobの`succeeded`後に対象ASINの`capture_state=captured`を再確認できた場合だけ
  次のjobを作成する。
- `failed`、監視タイムアウト、API不整合、割り込み時は次のjobを作成しない。
  監視側の停止は実行中job自体を中断しない。

---

## 2. 処理フロー

### 漫画（`run_comic.bat`）

```
起動 → Kindle ウィンドウ検索 → agent はページ設定を「2 ページ」へ固定
    → 新 Kindle は最大化 / 旧 Kindle は F11
    → ダイアログでタイトル確認
    → ReadingArea上下境界 + 見開き安全幅を検出 → CROP 座標確定
    → キャプチャループ（確定済みの左右矢印キーを使用。安定画像だけ保存）
    → ツールが変更した最大化/F11状態だけ復元（起動時フルスクリーンは維持）
    → PNG → PDF 結合（backend/data/comic/pdfs/<書籍名>.pdf）
```

### 小説（`run_novel.bat`）

```
起動 → Kindle ウィンドウ検索 → agent はページ設定を「1 ページ」へ固定
    → 新 Kindle は最大化 / 旧 Kindle は F11
    → ダイアログでタイトル確認
    → 白背景スキャン → CROP 座標確定
    → 任意で期待撮影画面数を指定（通常は空欄。紙面ページ総数とは別の値）
    → キャプチャループ（確定済みの左右矢印キーを使用。安定画像だけ保存）
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
| `NEW_KINDLE_CROP_TOP` / `NEW_KINDLE_CROP_BOTTOM_MARGIN` | 漫画・小説 | controller provider を使わない手動・互換経路の上下フォールバック |
| `NEW_KINDLE_SIDE_IGNORE_PX` | 漫画・小説 | Microsoft Store 版の左右 UI 除外幅 |
| `SIDE_IGNORE_PX` | 漫画 | ページ送り矢印位置が変わった場合に調整 |
| `COMIC_WHITE_THRESHOLD` / `COMIC_MIN_PAGE_ASPECT_RATIO` | 漫画 | 見開き安全幅のページ境界・最小幅を調整 |
| `WHITE_THRESHOLD` | 小説 | 背景がオフホワイトの場合に調整 |
| `MIN_CROP_WIDTH_RATIO` | 小説 | ページ内容に依存した過剰クロップを防ぐ最小幅を調整 |
| `DETECTION_PADDING_PX` | 小説 | 検出した本文領域の左右余白を調整 |

## 4. Microsoft Store版 Kindle 実機基準（2026-07-19）

- **検証環境**: Windows、3840×2160モニター、新Kindle本文ウィンドウ（タイトルは厳密に `Kindle`）。旧固定クロップの保存画像は1918px高だったが、実際の `ReadingArea` は最大化ウィンドウ相対で上端56pxから最下端まであり、下105px固定除外が本文を切ることを2026-07-26に確認した。
- **source別レイアウト**: `aaMenuButton` 配下の漫画用 `aaOption-Split` と ToggleState を実機確認した。固定レイアウト小説で `aaOption-Single` が存在する場合は明示選択する。リフロー型小説ではページ数 option が表示されず、`フォント-item`、フォントサイズ、余白、間隔が表示されることを確認したため、この構成を単ページ表示として受け入れる。
- **再撮影受入（2026-07-26）**: 小説2冊を91枚・92枚、全画像3516×1940で正式登録し、本文サンプルの最上部・最下部を残しながら上部書名と下部ページ進捗を除外できたことを確認した。漫画1冊を85見開き、全画像2936×2064で正式登録し、通常見開きの外側余白中央値が左15px・右17px、単ページの表紙と奥付は中央配置となることを確認した。3冊とも連番欠落、SHA-256完全重複、全面白画像は0件だった。
- **F11を使わない理由**: F11中にページ送りすると、本文描画が全面白のまま復帰しない事象を実測した。最大化ウィンドウでは同じページが正常描画される。
- **入力方式**: 当初は左右端から120pxのクリックを使ったが、実際のchevron領域は64pxで
  hover表示だけが変化する場合があった。現在は確定済みの `left` / `right` 矢印キーを使う。
- **描画確定**: ページ送り直後の白い中間フレームを保存しないよう、同一画像が0.75秒継続してから保存する。無変化時はページ送りを1回再試行し、再度無変化なら末尾とする。
- **ページ数の意味**: Kindleの `ページX/265` は紙面ページ番号であり、画面送り回数ではない。検証書籍では表紙から最終画面まで97画像だった。連番対応は `001=表紙`、`002=紙面ページ1`、`097=紙面ページ265の末尾ロゴ画面`。
- **完走実測**: 同じ開始位置から2回取得し、同番号画像のpHash差は中央値0・最大2/64。正式結果は連番97件、SHA-256重複0件、全面白0件、最終UI表示 `ページ265/265・100%`。
- **運用上の排他**: 自動取得中はKindle・マウス・キーボードを操作しない。操作が入った可能性のある結果は正式フォルダと分離して再取得する。
