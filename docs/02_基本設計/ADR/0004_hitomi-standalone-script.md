# ADR-0004: hitomi.la 新着監視を FastAPI 内蔵せず独立スクリプト + Task Scheduler で実行

- **Status**: Accepted
- **Date**: 2026-04-29
- **決定者**: プロジェクトオーナー
- **関連**: [hitomi新着監視設計書.md §2](../../03_詳細設計/機能別/hitomi新着監視設計書.md)（本 ADR の元情報）

## コンテキスト

hitomi.la の特定作者の新着ギャラリーを定期チェックして UI で既読／未読管理する機能を追加するにあたり、「監視ループをどこで動かすか」の選択が必要になった。

監視は:
- 1 日数回（デフォルト 0:00 / 12:00 / 18:00）程度の頻度で十分
- 1 回の処理は 10 秒〜数分（作者数 × NOZOMI 取得 + ID 比較）
- 失敗してもリトライは次回スケジュールで自動的にカバーされる

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| FastAPI バックグラウンドタスク | プロセス内でスケジュール実行 | バックエンド再起動で失われる、FastAPI 本来の責務外 |
| APScheduler を FastAPI に組み込み | プロセス内 cron 風スケジューラ | バックエンド停止中は走らない、依存追加 |
| Celery + Redis | 本格的なジョブキュー | 個人 LAN ツールに対し過剰、Redis 運用コスト |
| **独立スクリプト + Windows Task Scheduler** | OS のスケジューラに任せる | （採用） |

## 決定

hitomi 監視は **`backend/scripts/hitomi_monitor.py` 等の独立スクリプト**として実装し、**Windows Task Scheduler** から起動する。FastAPI 側は監視結果（`state.json` / 新着リスト）を読み取って UI に提供する API のみを持つ。

「今すぐ取得」UI から FastAPI 経由で同期実行する経路 (`POST /api/hitomi/run-now`) も用意し、subprocess 起動で同じスクリプトを呼ぶ。

## 根拠

- **バックエンドの稼働状況に依存しない**: FastAPI を停止していても監視は走る。Pic2PDF_Viewer は LAN 個人ツールでバックエンドを常時起動していない時間帯がある。
- **責務分離**: FastAPI は HTTP API、監視はバッチ処理、と種類の異なる仕事を別プロセスに分けた方が見通しが良い。
- **OS の Task Scheduler は枯れた基盤**: クラッシュ時の再起動・ログ・実行履歴を OS が管理してくれる（Discord 通知連携も別途構成済み）。
- **依存最小**: Celery / Redis 等の外部依存を導入しない。Python スクリプトと標準ライブラリで完結。

検討して採用しなかった他案の補足は特になし（本 ADR 起票時点のヒアリング）。

## 結果

### ポジティブ
- バックエンドのライフサイクルから完全に独立
- スクリプト単体で `python hitomi_monitor.py` 実行可能（デバッグ容易）
- Task Scheduler の設定変更だけで頻度・時刻を調整できる

### ネガティブ・受容したコスト
- Task Scheduler の設定が手動セットアップ手順として残る（[RemoteControl_Discord通知設定.md](../../04_環境構築/RemoteControl_Discord通知設定.md) 等で補完）
- 「同じスクリプトを subprocess 起動」の経路と「Task Scheduler 起動」の経路で 2 経路あり、ロック制御 (`state.json` 競合防止) が両方で効く必要がある
- Linux/Mac へポートする場合 cron / launchd への置き換えが必要

### 影響範囲
- `backend/scripts/hitomi_*.py` 関連スクリプト
- `backend/services/hitomi_*.py` の状態管理
- `backend/routers/hitomi.py` の API
- Windows Task Scheduler 設定（環境構築手順）

## 将来の再評価条件

- バックエンド常時稼働が前提になったとき（→ APScheduler 等プロセス内化を検討）
- 監視対象作者数が大幅増で 1 ジョブが長時間化し、複数並列実行が必要になったとき
- マルチプラットフォーム対応が必要になったとき（OS スケジューラ依存の見直し）
