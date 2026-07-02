# Claude Code Remote Control + Discord通知 設定書

## 概要

Claude Code の Remote Control セッションを起動した際に、接続URLをDiscordへ自動通知するスクリプトの設定。  
外出先や別デバイスからセッションURLをすぐに確認できる。

---

## ファイル構成

| ファイル | 説明 |
|---|---|
| `D:\61.tool\remote-control-discord.sh` | Remote Control起動 + Discord通知スクリプト（Git Bash用） |

---

## 前提条件

- Claude Code v2.1.51以降（`claude --version` で確認）
- claude.ai サブスクリプション（Pro / Max / Team / Enterprise）
- Git Bash インストール済み
- Discord Webhook URL 取得済み

---

## 初期設定

### 1. Discord Webhook URLの取得

1. 通知を受け取りたいDiscordチャンネルを右クリック → **チャンネルの編集**
2. **連携サービス** → **ウェブフック** → **新しいウェブフック**
3. **ウェブフックURLをコピー**

> **注意**: Webhook URLは秘密情報。公開リポジトリにコミットしないこと。

### 2. 環境変数の設定（Git Bash）

Git Bashで実行：

```bash
printf "export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'\n" > ~/.bashrc
source ~/.bashrc
```

### 3. エイリアスの設定（Git Bash）

```bash
echo "alias claude-rc='cd /d/61.tool/Pic2PDF_Viewer && /d/61.tool/remote-control-discord.sh'" >> ~/.bashrc
source ~/.bashrc
```

### 4. PowerShell対応（任意）

`$PROFILE`（`C:\Users\<user>\OneDrive\ドキュメント\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`）に追記：

```powershell
function claude-rc {
    & "C:\Program Files\Git\bin\bash.exe" -l -c "source ~/.bashrc && /d/61.tool/remote-control-discord.sh"
}
```

反映：

```powershell
. $PROFILE
```

---

## 使い方

Git Bash または PowerShell で：

```bash
claude-rc
```

- Claude Code Remote Control がサーバーモードで起動する
- セッションURLが表示されると同時にDiscordへ通知が届く
- `Ctrl+C` でサーバーを停止

---

## スクリプト仕様

**ファイル**: `D:\61.tool\remote-control-discord.sh`

| 項目 | 内容 |
|---|---|
| 起動ディレクトリ | `D:\61.tool\Pic2PDF_Viewer` |
| 起動コマンド | `claude remote-control`（サーバーモード） |
| URL検出 | `grep -oE 'https://[^ ]+'` でURLを抽出 |
| 通知タイミング | セッションURL検出時に1回のみ送信 |
| Discord Webhook | 環境変数 `DISCORD_WEBHOOK_URL` から取得 |

**Discord通知メッセージ形式:**

```
Claude Code Remote Control started
https://claude.ai/code?environment=env_XXXXX
```

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `claude-rc` が認識されない | プロファイル未反映 | `. $PROFILE`（PS）または `source ~/.bashrc`（Git Bash）を実行 |
| Workspace not trusted エラー | ワークスペース未承認 | `cd /d/61.tool/Pic2PDF_Viewer && claude` で一度起動して承認 |
| Discord通知が届かない | Webhook URL未設定または無効 | `echo $DISCORD_WEBHOOK_URL` で確認、無効な場合は再作成 |
| 日本語を含むメッセージが届かない | Git BashのUTF-8エンコード問題 | メッセージ本文をASCIIのみにする |
