# Kindle 価格監視設計

> status: living | last-verified: 2026-10-08

## 1. 目的と境界

監視対象として登録した Amazon.co.jp の Kindle 書籍 URL を、Codex の定期実行から
ブラウザで開き、画面に表示された現在価格、付与ポイント、定価（参考価格）を読み取る。Kindle版の定価を確認できない場合は、同一商品ページに明示された紙版定価を比較基準として使う。価格条件を
満たした場合は、Pic2PDFViewer の画面で管理した監視対象と価格履歴を正本として
Discord Webhook へ通知する。

- Kinseli/Kiseppe の API は使用しない。
- Amazon のページへ直接 HTTP リクエストするバックエンド処理は持たない。
- Codex のブラウザ操作で価格が読めない場合は fail closed とし、通知しない。
- Amazon のログイン、CAPTCHA、購入操作、カート操作は自動化しない。
- Amazon ページの構成変更や価格表示の欠落により、監視が失敗する可能性がある。

## 2. 利用者向け機能

`/kindle/price-watch` に価格監視画面を追加する。

- Amazon Kindle URL の追加・削除・有効/無効切替
- 閾値（実質価格 ÷ 定価 × 100）の設定
- 前回観測の実質価格より値下がりした場合の通知設定
- 現在価格、付与ポイント、実質価格、定価、定価種別、判定率、最終確認時刻、最終エラーの表示
- 対象ごとの価格履歴表示
- ブラウザから入力された観測値を手動再登録する導線

Kindle版の定価/参考価格がページ上に存在しない場合は、同一商品ページの紙版定価を
使用する。どちらの定価も確認できない場合は比率による通知を行わない。現在価格と
ポイントだけ取得できた場合も、実質価格の履歴保存と値下がり判定は行う。

画面のカード表示は`PriceWatchCard.tsx`、観測保存・条件判定・通知は`price_observation.py`が担当する。

## 3. データストア

既存の `META_DB_DIR/kindle_catalog.db` に次のテーブルを追加する。既存の購入カタログ
テーブルとは外部キーを持たせず、購入前の本も監視できるようにする。

### 3.1 `kindle_price_watches`

- `id`: integer primary key
- `url`: Amazon.co.jp URL
- `asin`: URLから抽出したASIN
- `title`: 表示タイトル（nullable）
- `threshold_percent`: 定価比の閾値。既定50、1〜100
- `notify_on_drop`: 前回の有効な実質価格より低い場合に通知するか
- `notify_below_threshold`: 閾値未満への遷移を通知するか
- `enabled`: 定期監視対象か
- `created_at`, `updated_at`, `last_checked_at`
- `last_status`, `last_error`
- `last_current_price`, `last_points`, `last_effective_price`
- `last_list_price`, `last_list_price_source`, `last_ratio_percent`

### 3.2 `kindle_price_observations`

- `id`: integer primary key
- `watch_id`: `kindle_price_watches.id` 外部キー
- `observed_at`: 観測時刻（JST）
- `current_price`: 現在価格（nullable）
- `points`: 画面に表示された付与ポイント。付与なしを確認できた場合は0（nullable）
- `effective_price`: `max(current_price - points, 0)`（nullable）
- `list_price`: Kindle版の定価/参考価格、取得不能時は紙版定価（nullable）
- `list_price_source`: `kindle` / `paper`。`list_price` の価格種別（nullable）
- `ratio_percent`: `effective_price / list_price * 100`（nullable）
- `status`: `ok` / `partial` / `failed`
- `error_message`: 読み取り失敗理由（nullable）
- `source`: `codex_browser` / `manual`

価格の比較と通知判定は、同一対象の直前の `effective_price` がある `ok` または `partial`
観測を基準にする。`status=ok` は現在価格、ポイント、定価、定価種別がすべて確認できた
観測に限る。

## 4. Codex ブラウザ実行契約

Codex の定期プロンプトは、監視対象取得後に各URLをブラウザで開き、画面上の表示だけを
読み取る。対象の一覧取得と観測結果の保存はローカルCLI経由で行う。

1. `python -m tools.kindle_price_monitor export-targets` で有効対象を取得する。
2. 各URLをブラウザで開く。
3. Kindle版の販売価格と付与ポイントを確認する。
4. Kindle版の定価・参考価格を確認し、表示がない場合は同一商品ページに明示された紙版定価を取得して `list_price_source=paper` とする。紙版の現在価格や中古価格は使わない。
5. ログイン要求、CAPTCHA、価格不明、商品ページ以外の場合は失敗として記録する。
6. `python -m tools.kindle_price_monitor ingest` にJSON観測結果を渡す。各要素は `current_price`、`points`、`list_price`、`list_price_source` を含む。
7. CLIは実質価格を算出して履歴を保存し、条件成立時だけDiscordへ通知する。

CodexがHTMLの推測値や検索結果の価格を補完してはいけない。表示を確認できない価格は
`null` として扱う。

## 5. 通知

`KINDLE_PRICE_DISCORD_WEBHOOK_URL` が設定されている場合だけ通知する。通知本文には
タイトル、現在価格、付与ポイント、実質価格、定価、定価種別、判定率、前回実質価格、
Amazon URL、通知理由を含める。

- 値下がり通知: 実質価格が直前の有効な実質価格より低い場合
- 閾値通知: 判定率が閾値未満になった場合
- 同一観測の重複通知は行わない。
- Webhook未設定または送信失敗でも価格履歴は保存し、監視全体は失敗させない。

## 6. 障害時挙動

- 一部対象の読み取り失敗は、その対象を `failed` にして他対象の処理を継続する。
- 現在価格またはポイントが読み取れない観測は実質価格を算出せず、価格条件を評価しない。
- Kindle版と紙版のどちらの定価も読み取れない観測は、定価比条件を評価しない。
- HTML構造変更を検知できるよう、Codexの観測結果にエラー理由を必須で残す。
- 価格の正しさは保証せず、購入前にAmazon公式画面で再確認する。

## 7. 受入条件

- 画面からURLを追加・削除・無効化できる。
- URLからASINを抽出できない場合は、Amazonの商品URLとして登録を拒否する。
- 現在価格・ポイント・定価・定価種別がすべてある観測だけ閾値判定される。
- Kindle版定価がない商品は紙版定価を使い、定価種別が画面と履歴で判別できる。
- 付与ポイントを差し引いた実質価格で、値下がりと定価比が判定される。
- 値下がり時にDiscordへ一度だけ通知され、同じ価格の再確認では通知されない。
- 価格取得失敗時に誤った値下がり通知を送らない。
- Codexがブラウザで確認できない状態を、履歴と画面で確認できる。
