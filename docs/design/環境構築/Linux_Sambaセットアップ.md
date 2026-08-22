# Linux サーバー Samba セットアップ

> status: living | last-verified: 2026-08-02

同人誌の画像ファイル（WebP / ZIP）を Windows からネットワークドライブ経由でサーバーに置けるようにする。
配置後、ブラウザの「PDF 生成」ページからワンクリックで変換できる。

---

## 構成

| 役割 | パス |
|------|------|
| Linux 側の共有フォルダ | `/opt/pic2pdf-viewer/data/doujin/input/` |
| Samba 共有名 | `pic2pdf-input` |
| Windows からのアクセス | `\\medaroserver\pic2pdf-input`（Tailscale 経由） |

Kindle キャプチャ成果物は同人誌入力と混在させず、専用の論理受信箱を使用する。
既存環境では Samba 設定の追加を不要にするため、`pic2pdf-input` 共有直下の
隠しディレクトリ `.kindle-capture-inbox` を受信箱とする。`DoujinWatcher` は
`.` で始まるトップレベルディレクトリをスキャン対象外とするため、同人誌の
自動生成には渡らない。

| 役割 | パス |
|------|------|
| Linux 側の Kindle 受信箱 | `/opt/pic2pdf-viewer/data/doujin/input/.kindle-capture-inbox/` |
| Samba 共有名 | `pic2pdf-input`（既存共有を再利用） |
| Windows からのアクセス | `\\medaroserver\pic2pdf-input\.kindle-capture-inbox` |

Amazon の `Kindle.zip` / `Your Orders.zip` から展開した CSV / JSON は、
同じ共有直下の隠しディレクトリ `.kindle-import` へ配置する。
Linux 側の `AMAZON_DATA_DIR` は従来パスを維持し、そのパスをこの実ディレクトリへ
向けるシンボリックリンクとする。
先頭が `.` のトップレベルディレクトリは `DoujinWatcher` の対象外なので、
Amazon CSV が同人誌入力として処理されることはない。

| 役割 | パス |
|------|------|
| Linux 側の Amazon データ入力 | `/opt/pic2pdf-viewer/data/doujin/input/.kindle-import/` |
| Samba 共有名 | `pic2pdf-input`（既存共有を再利用） |
| Windows からのアクセス | `\\medaroserver\pic2pdf-input\.kindle-import` |
| Linux 環境変数 | `AMAZON_DATA_DIR=/opt/pic2pdf-viewer/import/kindle/files` |
| Linux 側の参照リンク | `/opt/pic2pdf-viewer/import/kindle/files` → `/opt/pic2pdf-viewer/data/doujin/input/.kindle-import` |

ZIP 自体はバックエンドの取込対象ではない。Windows 側で ZIP を展開し、
次の手順で CSV / JSON を配置してから、Web UI の
`Kindle` → `取込・管理` → `すべて差分取込` を実行する。

1. 注文・借用・返品など従来名のファイルは、名前を変えずに上書きする。
2. `Kindle.UnifiedLibraryIndex` のバージョン付きファイルは、
   [Kindle 購入カタログ設計 §4.1](../詳細設計/機能別/Kindle購入カタログ設計.md#kindle-amazon-export)
   に従って完全な版を選び、バックエンド用の正規名へコピーする。
3. `1.1` / `2.2` などの旧版や未知のデータセットを一緒に配置しない。
4. 新しいエクスポートに `kindle-series-autobuy.json` がない場合は、共有上の既存版を削除・置換しない。

---

## インストール・設定手順（Linux サーバーで実行）

```bash
# 1. インストール
sudo apt install -y samba

# 2. 入力ディレクトリを作成
sudo mkdir -p /opt/pic2pdf-viewer/data/doujin/input
sudo chown amashio:amashio /opt/pic2pdf-viewer/data/doujin/input

# 3. Samba ユーザーパスワードを設定（amashio の Samba パスワード）
sudo smbpasswd -a amashio

# 4. /etc/samba/smb.conf の末尾に追記
sudo tee -a /etc/samba/smb.conf <<'EOF'

[pic2pdf-input]
   path = /opt/pic2pdf-viewer/data/doujin/input
   browseable = yes
   read only = no
   valid users = amashio
   create mask = 0644
   directory mask = 0755
EOF

# Kindle キャプチャ専用の論理受信箱（正式な画像領域は共有しない）
mkdir -p /opt/pic2pdf-viewer/data/doujin/input/.kindle-capture-inbox

# Amazon CSV / JSON の Windows 配置先
mkdir -p /opt/pic2pdf-viewer/data/doujin/input/.kindle-import

# AMAZON_DATA_DIR の従来パスから共有内の実ディレクトリを参照する
ln -s /opt/pic2pdf-viewer/data/doujin/input/.kindle-import \
  /opt/pic2pdf-viewer/import/kindle/files

# 5. 設定確認
testparm

# 6. 再起動
sudo systemctl restart smbd nmbd
sudo systemctl enable smbd nmbd
```

---

## Windows 側の設定

1. エクスプローラーを開き、アドレスバーに `\\medaroserver\pic2pdf-input` を入力
2. 認証を求められたら Samba パスワードを入力
3. 「ネットワークドライブの割り当て」で `Z:` などに固定すると便利

Amazon データを更新するときは、アドレスバーへ
`\\medaroserver\pic2pdf-input\.kindle-import` を直接入力する。
隠しディレクトリのため、通常の一覧に表示されない場合がある。

> **前提**: Tailscale が起動していること、`medaroserver` の名前解決ができること。
> 解決しない場合は `\\100.76.210.48\pic2pdf-input` などの IP で試す。

Kindle キャプチャエージェントでは `.env` に次を設定する。

```dotenv
PIC2PDF_API_URL=http://medaroserver:8090
KINDLE_CAPTURE_AGENT_TOKEN=<Linux 側と同じ十分に長いランダム値>
KINDLE_CAPTURE_AGENT_ID=kindle-windows-1
KINDLE_CAPTURE_INBOX_DIR=\\medaroserver\pic2pdf-input\.kindle-capture-inbox
```

Linux 側にも `KINDLE_CAPTURE_AGENT_TOKEN` と
`KINDLE_CAPTURE_INBOX_DIR=/opt/pic2pdf-viewer/data/doujin/input/.kindle-capture-inbox`
を設定する。
エージェントは `scripts\run_capture_agent.bat` から起動する。

OCRをWindows GPUへ委譲する場合は、Linux側で`OCR_AGENT_ENABLED=true`、
双方で同じ`KINDLE_CAPTURE_AGENT_TOKEN`を設定する。Windows側は必要に応じて
`OCR_AGENT_ID`、`OCR_AGENT_POLL_SECONDS`、`OCR_AGENT_HEARTBEAT_SECONDS`を設定し、
`scripts\run_ocr_agent.bat`を起動する。OCR agentは画像を一時ディレクトリへ取得し、
`novel.db`や正式画像を直接更新しない。

---

## 使い方（新刊追加フロー）

1. エクスプローラーで `Z:\`（共有フォルダ）を開く
2. WebP 画像フォルダ または ZIP ファイルをコピー
3. ブラウザで `http://100.76.210.48:8090/doujin` → 左メニュー「PDF 生成」
4. 「スキャン & 生成」ボタンをクリック
5. 生成が完了したら入力フォルダのファイルを削除してよい

---

## トラブルシューティング

| 症状 | 確認事項 |
|------|----------|
| 接続できない | `sudo systemctl status smbd` でサービス確認 |
| 認証エラー | `sudo smbpasswd -a amashio` でパスワード再設定 |
| 生成ページが 503 を返す | 入力ディレクトリが存在するか確認: `ls /opt/pic2pdf-viewer/data/doujin/input/` |
| Amazon データが取り込まれない | ZIP が展開済みか、`AMAZON_DATA_DIR` と `.kindle-import` が一致するか、対象 CSV / JSON のファイル名が変更されていないか確認 |
