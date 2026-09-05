# Kindle キャプチャツール 基本設計書

> status: living | last-verified: 2026-09-05

実機依存の観測値、障害切り分け、再撮影後の品質確認は
[Kindle 自動撮影 実機知見](../../docs/log/技術知見/Kindle自動撮影_実機知見.md)を参照する。
Linux backendを含むjob状態、heartbeat、正式登録、シリーズ停止・再開条件は
[Kindle自動撮影ジョブ契約](../../docs/design/詳細設計/機能別/Kindle自動撮影ジョブ契約.md)を正本とする。本書はWindows側の撮影moduleと入出力境界だけを扱う。

## 1. システム概要

Windows 版「Kindle for Windows」（Microsoft Store 版）で購入書籍を検索・照合し、必要ならダウンロードして先頭から最終画面まで撮影し、Pic2PDFViewerへ登録する自動化ツール群。通常運用は `scripts/run_capture_agent.bat` を使い、漫画用（`run_comic.bat`）と小説用（`run_novel.bat`）は診断・互換経路として残す。

- **漫画（comic ソース）**: 自動agentはPNGをLinuxへ送り正式画像として登録する。手動互換経路だけは従来どおりPDFも生成できる。
- **小説（novel ソース）**: 自動agentはPNGをLinuxへ送り正式画像として登録する。OCR・novel.db格納・RAG インデックス構築は backend の job queue（`/novel/manage`）で実施する。

## 2. 動作環境

- **OS**: Windows 10/11
- **対象アプリ**: Kindle for Windows（Microsoft Store 版。旧 Kindle for PC もウィンドウ検出互換あり）
- **言語**: Python 3.x（`uv` で管理。`pyproject.toml` / `uv.lock`）
- **主な外部ライブラリ**:
    - `pyautogui`: キーボード・マウス操作
    - `uiautomation`: Kindle control の識別・属性・矩形取得
    - `pillow` (PIL): スクリーンショット取得
    - `opencv-python` (cv2): 画像保存・解析
    - `numpy`: 画像データ処理

## 3. 起動方法

```
scripts\run_capture_agent.bat  # 通常運用（購入カタログのjobを1冊ずつ処理）
kindle-pdf\run_comic.bat   # 漫画キャプチャ（main_auto.py を起動）
kindle-pdf\run_novel.bat   # 小説キャプチャ（main_novel.py を起動）
```

## 4. 機能概要

### 4.1. 漫画キャプチャ（自動検出モード）

- Microsoft Store 版 Kindle は、F11 でページ送り後の本文が白くなる実機挙動を避けるため、ウィンドウを最大化して撮影。旧 Kindle for PC は F11 フルスクリーンを継続利用する。
- 起動時点ですでにフルスクリーンならその状態を維持し、ツール自身が切り替えた場合だけ終了時に元へ戻す。
- ページ送りは利用者がjobまたは手動ダイアログで確定した `left` / `right` の矢印キーを利用する。
- ページ画像は変化直後に保存せず、同一画像が一定時間続いて描画が安定したことを確認してから保存する。
- 自動agentは撮影前にページ設定の「2 ページ」を選択し、ToggleState が On であることを確認する。
- 最大化後の `ReadingArea` を上下境界とし、先頭ページから推定した 1 ページ幅の
  2 倍を見開き安全幅として確保する。表紙だけが単ページ表示でも後続見開きを切らず、
  白い閲覧キャンバスの外側余白は保存しない。
- 手動互換経路は撮影後に画像をまとめて PDF 化する。自動agentはPDFを生成せず、PNG packageをSamba受信箱へ送る。

### 4.2. 小説キャプチャ（白背景検出モード）

- Microsoft Store 版 Kindle は最大化ウィンドウ、旧 Kindle for PC は F11 フルスクリーンで撮影。
- 自動agentは撮影前にページ設定の「1 ページ」を選択し、前の漫画ジョブの設定を引き継がない。
- Microsoft Store 版では最大化後の `ReadingArea` 内にある `TopChrome` と
  `Footer` の実矩形を取得し、`TopChrome.bottom` から `Footer.top` までを
  上下境界とする。本文最下部を保持しながら、上部書名と下部ページ・進捗表示を除外する。
- 左右のページ送りボタンはクロップ対象外にする。
- 白背景（`WHITE_THRESHOLD = 240`）をもとにテキスト領域の左右端を自動検出。空白だけのスキャン行は境界判定から除外する。
- 検出幅が安全領域の 90% 未満なら、ページ内容による過剰クロップと判断して安全領域全体へフォールバックする。章扉など本文幅が狭いページから開始しても、後続ページの本文を欠落させない。
- 任意の期待撮影**画面**数を指定できる。ページ番号外の表紙も1画面として数えるが、Kindleの「ページ265/265」のような紙面ページ番号と、現在のフォント・画面サイズで必要な画面送り回数は一致しない。通常は空欄の自動終了を使い、事前に画面数が判明している場合だけ指定する。
- 画像のみ `backend/data/kindle_novel/images/<書籍名>/` に保存する（PDF 化・OCR はしない）。

## 5. ディレクトリ構成

```text
kindle-pdf/
├── capturer.py           # 基底クラス (Config, KindleCapturer, AutoConfig, AutoKindleCapturer)
├── capture_agent.py      # Linuxのcapture jobを自動実行
├── capture_agent_transport.py # agent設定・API client・heartbeat
├── capture_loop.py       # ページ安定待ち・終端証跡付き撮影ループ
├── capture_canary.py     # 正式撮影前の2画面カナリア
├── capture_quality.py    # 連番・復号・寸法・hash・warning候補の登録前QA
├── capture_overlay.py    # 複数ページ間の反復画面オーバーレイ検出
├── capture_transient_overlay.py # 連続3画面の短時間右下通知検出
├── capture_package.py    # version 2 manifestと.partial→.ready公開
├── kindle_app_controller.py # Kindle検索・照合・ダウンロード・先頭移動
├── main_manual.py        # 固定クロップモード（旧 main.py）
├── main_auto.py          # 漫画用フルスクリーン・自動検出モード
├── novel_capturer.py     # 小説用クラス (NovelConfig, NovelKindleCapturer)
├── main_novel.py         # 小説キャプチャ起動スクリプト
├── diagnose_new_kindle.py # Kindle for Windows のウィンドウ・キャプチャ保護診断
├── run_comic.bat         # 漫画キャプチャ起動（main_auto.py を呼び出す）
├── run_novel.bat         # 小説キャプチャ起動（main_novel.py を呼び出す）
├── pyproject.toml        # uv 依存管理
├── uv.lock               # uv ロックファイル
└── docs/
    ├── basic_design.md
    └── detailed_design.md
```

## 6. 入出力

| 系統 | 入力 | 出力 |
|---|---|---|
| 自動漫画 | Kindleカタログのcapture job | Samba受信箱を経由してLinuxの `data/comic/images/<書籍名>/` へ正式配置 |
| 自動小説 | Kindleカタログのcapture job | Samba受信箱を経由してLinuxの `data/kindle_novel/images/<書籍名>/` へ正式配置 |
| 手動互換 | Kindle for Windows（開いた書籍） | 従来のローカル画像／PDF出力 |

## 7. OCR・後処理フロー

自動agentは漫画・小説ともPNGをLinuxへ送り、backendが正式画像領域へ登録する。手動漫画だけはcapturerが直接PDFを生成できる。小説のOCR以降はbackendが担う。

```
[小説キャプチャ完了]
        ↓
backend/data/kindle_novel/images/<書籍名>/001.png ...
        ↓
/novel/manage（管理画面）から OCR ジョブをキュー投入
        ↓
Surya OCR 2 → novel.db（pages / FTS）→ RAG インデックス構築
```
