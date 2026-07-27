# Windows サービス化セットアップ

> status: living | last-verified: 2026-07-27

Pic2PDF Viewer のリリースサーバー（uvicorn on :8090）を **NSSM (Non-Sucking Service Manager)** で Windows サービスとして登録する手順。
他環境への移植時はこの手順を上から順に実施。

> **現行スクリプトの制約**: `scripts/setup_service.bat` は旧
> `backend/.venv` を参照する。標準の uv workspace はルート `.venv` を正とするため、
> 新規端末へこの手順を適用する前にスクリプト側のパス修正が必要。
> 既存端末の `backend/.venv` はサービス移行が完了するまで削除しない。
> 詳細は [既知の問題](../../log/既知の問題.md) を参照。

## 概要

| 項目 | 内容 |
|---|---|
| サービス名 | `Pic2PDFViewer` |
| 表示名 | `Pic2PDF Viewer` |
| 実行コマンド | `backend\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8090` |
| 起動種別 | 自動（遅延開始） |
| 実行アカウント | ローカルユーザー（OneDrive 配下のデータアクセスに必要） |
| crash 時挙動 | 5 秒待機して自動再起動（ただし 10 秒以内連続失敗時は throttle） |
| ログ出力 | `backend/data/logs/service-stdout.log` / `service-stderr.log`（10MB / 24h でローテーション） |

## 前提条件

1. backend の venv が存在すること
   - `backend\.venv\Scripts\python.exe` が存在
   - 未作成の新規 workspace ではこの文書の手順を中断し、setup script の
     ルート `.venv` 対応後に登録する
2. frontend の dist が build 済みであること
   - `frontend\dist\index.html` が存在
   - 未作成なら `scripts\build_release.bat` を実行
3. 管理者権限の PowerShell or コマンドプロンプトが使えること

## セットアップ手順

### Step 1. NSSM のインストール

PowerShell（管理者権限不要）で:

```powershell
winget install NSSM.NSSM
```

`nssm` コマンドが PATH に追加される。新しい PowerShell を開けば `nssm --version` で確認可能。

代替手段（winget が使えない / nssm.cc が落ちている場合）:
- Chocolatey: `choco install nssm`
- 公式 zip ダウンロード: https://nssm.cc/download

### Step 2. サービス登録

`scripts\setup_service.bat` を**管理者として実行**（エクスプローラで右クリック → 管理者として実行）。

実行内容:
- 既存サービスがあれば停止 + 削除
- `nssm install Pic2PDFViewer` で新規登録
- 各種パラメータを設定（auto-start delayed / 再起動ポリシー / log rotation / kill tree / `PYTHONIOENCODING=utf-8`）
- 最後に NSSM の GUI が開く

> **重要**: 初回環境では `setup_service.bat` 内の `NSSM` 変数を環境に合わせて確認すること。winget 経由のインストール時は通常以下のパス:
> `C:\Users\<ユーザー名>\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe`
> バージョンが上がるとパスのバージョン文字列が変わる可能性あり。

GUI が開いたら**何もせず**閉じて構わない（Log On 設定は Step 4 で services.msc から行う方が確実）。

### Step 3. "Log on as a service" 権限の付与

NSSM / services.msc は自動付与を試みるが Windows 11 では失敗することがあるため、明示的に付与する。

`scripts\grant_logon_right.bat` を**管理者として実行**。

内部で `grant_logon_right.ps1` が LSA API (`LsaAddAccountRights`) を直接呼んで `SeServiceLogonRight` をユーザーに付与する。

実行結果:
```
Target: amashio          # 環境のユーザー名
SID   : S-1-5-21-...
Right : SeServiceLogonRight

[OK] Granted SeServiceLogonRight to amashio via LsaAddAccountRights.
```

`[ERROR] LsaAddAccountRights failed: Win32 error XXX` が出る場合:
- `5` (Access denied): 管理者で実行していない
- `1332` (No mapping): ユーザー名のスペルミス / アカウントが存在しない

### Step 4. サービスのログオンアカウント設定

`Win + R` → `services.msc` → Enter

1. リストから「**Pic2PDF Viewer**」を探す
2. 右クリック → **プロパティ**
3. 「**ログオン**」タブ
4. 「**アカウント**」を選択
5. ユーザー名: `.\<ローカルユーザー名>`（例: `.\amashio`）
6. パスワード: Windows ログインパスワードを 2 回入力
7. **適用** → **OK**

`LocalSystem` のままだと OneDrive 配下のデータにアクセスできず、書籍リストが空になる。

### Step 5. サービス起動

services.msc で「Pic2PDF Viewer」を右クリック → **開始**。

数秒後に状態が「**実行中**」になれば成功。

### Step 6. 動作確認

PowerShell から:

```powershell
# サービス状態
Get-Service Pic2PDFViewer
# Status: Running, StartType: Automatic

# HTTP 応答
Invoke-WebRequest http://localhost:8090/ -UseBasicParsing | Select-Object StatusCode
# 200

# API（書籍が返ってくれば OneDrive アクセスも OK）
(Invoke-WebRequest http://localhost:8090/api/novel_db/books -UseBasicParsing).Content | ConvertFrom-Json | Measure-Object | Select-Object Count
```

ブラウザで http://localhost:8090 を開いて Viewer が表示されれば完成。

### Step 7. 旧 auto-start の無効化

タスクスケジューラ等で同等の起動を別途設定している場合、それを無効化しないと boot 時に衝突する。

```powershell
# 確認
Get-ScheduledTask | Where-Object { $_.Actions.Execute -match "Pic2PDF|start_release|start\.bat" }

# 該当タスクを Disable
Disable-ScheduledTask -TaskName "Pic2PDF_Viewer"
```

### Step 8. PC 再起動による最終確認

PC 再起動 → ログイン直後（または遅延 auto-start のため 2 分ほど）に http://localhost:8090 が応答すれば完成。

## 日常運用

| やりたいこと | コマンド / 操作 |
|---|---|
| サービス状態確認 | `Get-Service Pic2PDFViewer` |
| 起動 | services.msc から「開始」 or `Start-Service Pic2PDFViewer`（要管理者） |
| 停止 | services.msc から「停止」 or `Stop-Service Pic2PDFViewer`（要管理者） |
| **rebuild 後の再起動** | `scripts\build_release.bat` → `scripts\restart_service.bat`（管理者で実行） |
| ログ tail | `Get-Content "D:\61.tool\Pic2PDF_Viewer\backend\data\logs\service-stdout.log" -Tail 50 -Wait` |
| ブラウザを開くだけ | `scripts\open_viewer.bat` |

## トラブルシューティング

### サービスが起動しない

```powershell
# stderr ログを確認
Get-Content "D:\61.tool\Pic2PDF_Viewer\backend\data\logs\service-stderr.log" -Tail 50
```

よくある原因:
- `frontend\dist\index.html` が存在しない → `scripts\build_release.bat` 実行
- `backend\.venv` が壊れている／存在しない → 現行 setup script の旧パス依存。
  ルート `.venv` 対応を行ってからサービスを再登録する
- alembic migration の失敗 → DB ファイルの権限 / WAL ロックを確認

### 書籍リストが 0 件 / OneDrive データが見えない

→ Step 4 のログオンアカウントが `LocalSystem` のままになっている可能性。services.msc で確認 → `.\amashio` に変更。

### 「サービスは応答しませんでした」「エラー 1067」

uvicorn が起動直後にクラッシュしている。stderr ログで Python 例外を確認。
パスワードを変えた直後ならログオンアカウントの再設定が必要（services.msc → プロパティ → ログオンタブ → パスワード再入力）。

### NSSM GUI で「Couldn't set startup parameters for the service!」

Step 3 (`grant_logon_right.bat`) の実行漏れ。LSA 権限を付与してから services.msc を経由する方法に切り替える。

### サービスのクラッシュループ

stdout/stderr に直近のエラーが残る。10 秒以内に死ぬとサービス自体が **throttle** されて再起動を停止する（NSSM の `AppThrottle 10000` 設定）。
Throttle 発動時は services.msc から手動で「開始」を再実行可能。

## サービスのアンインストール

別環境への移行 / 再セットアップ時:

```powershell
# 管理者 PowerShell
Stop-Service Pic2PDFViewer
nssm remove Pic2PDFViewer confirm
```

設定ファイルは NSSM が Windows サービスデータベース内に保持しているため、`nssm remove` で完全に消える。`backend/data/logs/service-*.log` は手動で削除して構わない。

## 参考: 設計判断

- **なぜサービス化したか**: bat ファイル + タスクスケジューラ運用ではターミナル多重起動 → port 8090 を巡る kill 競合 → exit code -1 のクラッシュループが発生した。Windows サービス機構は単一インスタンス保証 + 自動再起動 + 子プロセスツリー管理を OS レベルで提供する。
- **なぜ NSSM か**: 任意の .exe をサービス化する薄いラッパー。`sc.exe` 直接登録に比べて log redirect / rotation / 再起動ポリシー / 子プロセス kill が標準で備わる。
- **なぜ `uv run` を経由しないか**: `uv run uvicorn` だと cmd → uv.exe → uvicorn.exe → venv python → system python の 4 段プロセスチェーンになり、kill / 再起動の挙動が予測しづらい。`.venv\Scripts\python.exe -m uvicorn` 直接呼び出しなら 1 段のみ。
- **なぜ遅延自動開始か**: 通常の Automatic だと boot 初期に OneDrive のマウント前に走る可能性がある。遅延（Delayed Auto-Start）でログイン後 2 分程度の猶予を入れる。
