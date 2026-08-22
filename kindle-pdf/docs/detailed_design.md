# Kindle キャプチャツール 詳細設計書

実機依存の観測値、障害切り分け、再撮影後の品質確認は
[Kindle 自動撮影 実機知見](../../docs/log/技術知見/Kindle自動撮影_実機知見.md)を参照する。

## 1. モジュール構成・クラス設計

### 1.1. 撮影クラス群

`capturer.py`は既存import用facadeとし、実装を次へ分割する。

- `capture_base.py`: `Config`、window操作、手動タイトル確認、PDF作成。
- `capture_loop.py`: 撮影workflow、描画安定待機、ページ送りの実行。
- `capture_loop_policy.py`: retry順、最初の遷移だけの反対方向試行、期待枚数判定。
- `capture_loop_models.py`: `CaptureReport` / `CaptureResult` とmanifest終了証跡の構築。
- `capture_loop_io.py`: 画面取得、出力directory作成、PNG encode・保存。
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
- **`capture_loop(title)`**: メインキャプチャループ（安定画像取得→保存→ページめくり→変化・再安定待ち）。`CaptureResult`へ画面数、保存先、終了理由、無変化観測回数、遷移集計、撮影矩形を記録する。期待枚数へ達した場合も追加のページ送りで無変化を確認し、次画面が存在すれば期待値不一致として失敗する。表紙から2画面目へ進む最初の遷移に限り、選択済みキーで無変化なら反対キーを1回だけ試し、本文開始後と終端では方向を切り替えない。保存候補が2画面前と連続2回一致する `A → B → A → B` を検出した場合、最低撮影数（漫画10・小説50）より前なら誤方向として失敗する。最低撮影数を満たした後はKindle末尾の往復と判定し、最初の重複画像を一時領域から破棄して直前の一意な画面を終端とする。期待枚数指定時は、その枚数より前の周期を末尾扱いしない。単発の2画面前一致だけでは停止しない。
- **`_next_page()`**: Kindle の世代にかかわらず、利用者が確定した方向の矢印キーを送る。
- **`_wait_for_stable_page()`**: 直前ページとの平均画素差を検出した後、同等画像が `PAGE_STABLE_SEC` 継続するまで待ち、白い遷移フレームやhover表示等を保存対象から除外する。
- **`create_pdf(title, image_dir)`**: 連番 PNG から PDF を生成。

`capture_loop.py`は純粋policyが返すretry列を順に実行し、各観測結果を
`CaptureProgress`へ記録する。PNG encode失敗、期待枚数前の停止、期待枚数後に次画面が
存在する場合は成功reportを生成しない。`CaptureReport`のpolicy version、field、
終了理由、manifest変換は`capture_loop_models.py`を正本とする。

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

公開classはfacadeとして維持し、`kindle_controller/`配下で次の責務へ分割する。

- `models.py`: 書誌同定、開始フッター判定、設定・例外・値object。
- `window.py` / `library.py`: Window/UIA基盤とライブラリ検索・download・open。
- `reader.py`: 読書画面の開始位置・レイアウトworkflow。
- `reader_policy.py`: source別レイアウトと表紙補正・逆方向keyの純粋判断。
- `reader_ui.py`: page settings、location dialog、`SetValue` readback、確認・cleanupの
  UIA/キーボードadapter。controllerの限定control探索へ委譲し、独自の全画面探索は行わない。

旧 `KindleAppController` のclass名、constructor、公開methodと既存protected methodは
移行期間中維持する。`reader.py` はpolicyとadapterを順に呼ぶworkflowのみを所有し、
adapterからcapture agentやHTTP transportを参照しない。

- `uiautomation` を使い、検索欄とASIN固有のAutomationIdを限定探索する。
- 検索欄は限定取得したcontrolの `ValuePattern.SetValue` で半角ASIN全体を置換し、
  同じpatternから完全一致を読み戻した場合だけ候補探索へ進む。
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
- 高速経路のページ/ロケーション入力は限定取得したcontrolの `ValuePattern.SetValue` と
  読み戻しを使う。UI Automationの `Click` は使わず、buttonは取得矩形中心への
  通常クリックまたはフォーカス後のEnterで操作する。
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
  `aaMenuButton` が直ちに公開されない場合は、最新の `ReadingArea` を再取得して
  ツールバー表示を最大2回試し、各試行を `control_timeout_seconds` の期限内で
  AutomationId限定取得する。試行間はEscapeで一度UIを閉じ、固定座標クリックや
  全descendant探索へはフォールバックしない。期限内に取得できなければ
  `positioning_failed` とする。
  ページ数 option の `ToggleToggleStateProperty` が On にならない場合は
  `positioning_failed` とし、`CloseSideMenuHeaderButton` と読書領域中央の
  クリックで設定 UI を閉じる。
- `capture_area_bounds(source)` は最大化後の撮影矩形を返す。`comic` は
  `ReadingArea` 全体、`novel` は `ReadingArea` の左右端と
  `TopChrome.bottom` / `Footer.top` を合成し、書名とページ・進捗表示を除外する。
  各矩形の包含関係を検証できない場合は撮影を開始しない。
- 通常の単冊経路とcapture agentはKindleの起動、ログイン、画面ロック解除を行わない。
  シリーズ直列実行のオプトイン復旧だけは、撮影開始前の失敗でKindleプロセスの消失を
  確認した場合に限ってStoreアプリを再起動する。プロセスが残るUI不調は強制終了しない。
- 候補なし・複数・UI取得不能・ダウンロード期限超過・先頭移動不能は工程別エラーとして終了し、capturerを起動しない。

### 1.8. `capture_agent.py`（ジョブ実行）

バックエンドから1件ずつjobをclaimし、`KindleAppController`による準備、source別ページレイアウトの明示選択、既存capturerによる全ページ撮影、Samba上の論理専用inboxへの原子的公開、完了APIを直列実行する。既存環境では `pic2pdf-input/.kindle-capture-inbox` を利用し、同人誌監視は隠しディレクトリを除外する。処理中は独立threadでheartbeatを定期送信し、状態を `locating_book → downloading（必要時）→ positioning → capturing → awaiting_files` として通知する。

`capture_agent_transport.py`は設定・API・heartbeat、`capture_quality.py`は連番・復号・
寸法・hash検査と警告候補集計、`capture_overlay.py`は複数ページ間の反復オーバーレイ検出、
`capture_package.py`はversion 2 manifestと`.partial → .ready`公開、`capture_agent.py`は
工程制御とエラー変換を担当する。

- 撮影完了後は、連番、全画像の復号、寸法一貫性、SHA-256、画面数と終了証跡を
  fail-closedで検査する。完全重複、低容量、白紙・疎な画面は閾値校正中のため
  warningとしてmanifestへ残し、自動削除や登録拒否には使わない。
- 警告専用検査として、隣接ページのdHash距離による近似重複候補と、小説ページの
  上下端における暗画素密度による端切れ候補を記録する。閾値はpolicy versionへ固定し、
  未調整の実画像shadow評価が終わるまではblockingへ昇格しない。
- 画面オーバーレイ検出は、最大32ページの外周を同一座標の小タイルで比較する。
  無地タイルを除外し、完全画像hashが異なる3ページ以上に同一の構造化タイルが残り、
  さらに隣接タイル群が標本の50%以上で反復した場合だけ高信頼としてfail closedにする。
  20%以上50%未満は`repeated_screen_overlay_candidate` warningとする。これにより、
  ページ全体の重複や白余白だけでは発火せず、通知文言やOS種類に依存しない。
  標本画像の縮小・エッジ抽出だけを最大4 workerで並列化し、候補集約は決定的な順序で行う。
- ページ単位の復号・寸法・hash・統計計算だけを少数workerで並列化できる。
  Kindle UI操作、ページ送り、package確定、正式登録は常に1件ずつ直列実行する。

- 警告候補の未調整holdout評価は`capture_quality_holdout.py`を使い、画像directoryと
  確定labelを持つprivate manifestを読み取り専用で評価する。manifestの構築・署名・検証と
  provenance contractは`capture_quality_holdout_contract.py`、監査・指標集計・CLIは
  `capture_quality_holdout.py`が担当する。検出器本体と同じ
  `audit_capture_images()`を呼び、完全重複、低容量、白紙・疎、隣接dHash近似重複、
  小説上下端、反復overlayについてcode別のTP/FP/FN、precision、recallをJSONへ保存する。
  `--build-spec` / `--manifest-output`でspecから画像SHA付きmanifestを原子的に生成し、従来の
  `--manifest` / `--output`で評価する。case ID、source、連番画像、label code、label対象file、
  重複labelをmanifest digest計算前と評価前の両方で検証する。構造監査や画像復号に失敗したcaseを
  予測0件として集計せず、holdout全体をfail closedで終了する。
- manifest digest、画像SHA、検出policy versionをレポートへ固定し、同じ入力で決定的に
  再生成できるようにする。実画像に陽性labelがないcodeはrecallを`null`とし、制御故障による
  recallと実画像の適合率を混ぜない。AI支援labelはreviewer種別と人手確認状態をprivate artifactへ
  明記し、人手確定済みと扱わない。任意の`provenance`は`dataset_role`、`ground_truth_kind`、
  `reviewer_kind`、`human_confirmation`、関連digest、任意の確認日時`reviewed_at`を持ち、manifest
  digestの対象としてreportへそのまま引き継ぐ。制御故障は
  `controlled_corruption / deterministic_corruption`として
  実画像holdoutと別reportに固定する。評価器は画像削除、package生成、登録、警告のblocking昇格を行わない。

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
- 検索欄とページ/ロケーション入力欄は、限定取得したcontrolの
  `ValuePattern.SetValue`で値全体を置換し、同じpatternから完全一致を読み戻す。
  IME依存の通常キー入力や固定画面座標を使わない。ボタン操作は取得したcontrolの
  矩形中心への通常クリックまたはフォーカス後のEnterを使い、UI Automationの
  `Click`と全descendants高頻度走査は行わない。ウィンドウ前面化は取得済みの
  ネイティブハンドルをWin32 APIへ渡す。


### 1.9. シリーズ実行から利用する限定復旧

シリーズ全体のjob順序、停止、session state、再開条件は
[Kindle 購入カタログ設計 §7.2](../../docs/design/詳細設計/機能別/Kindle購入カタログ設計.md#72-シリーズ直列実行)を正本とする。

`kindle_capture_recovery.py` は、rootの `scripts/capture_kindle_series.py` から
明示的に指定された場合だけStore版Kindleを再起動し、ライブラリで同じASINを
`KindleAppController`により再照合するadapterである。

- 撮影開始前、撮影枚数0、Kindle process消失、許可error codeをすべて要求する。
- processが残る場合はkill・restartしない。
- 別の未完了jobがある、ASIN候補が0件または複数、セッションで復旧済みなら停止する。
- 復旧は失敗jobの再開ではなく、同じ書籍の新規job作成を許可する準備だけを行う。
- 対象、旧job、新job、起動結果、再照合結果を監査ログへ残す。

### 1.10. 撮影前カナリア

`positioning`中に正式capturerと同じsource、方向、撮影矩形で先頭2画面をメモリ取得する。
復号済み配列の寸法一致と視覚差分を確認し、SHA-256と差分指標を証跡化する。カナリア後は
`go_to_start()`を再実行し、開始位置の再検証に成功してから`capturing`へ遷移する。
無変化、寸法不一致、撮影矩形不正、先頭復帰失敗は`capture_canary_failed`として停止し、
正式撮影、package公開、登録を行わない。

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


## 4. 実機基準

日付付きの画面寸法、撮影件数、F11不具合、chevron、pHash、完走・再撮影結果は
[Kindle 自動撮影 実機知見](../../docs/log/技術知見/Kindle自動撮影_実機知見.md)を正本とする。
本書にはそれらの実測から採用したmodule契約だけを残す。
