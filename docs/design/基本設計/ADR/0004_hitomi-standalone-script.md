# ADR-0004: hitomi.la 新着監視を独立バッチ + OS schedulerで実行

- **Status**: Accepted（Linux systemd運用へ更新 2026-08-22）
- **Date**: 2026-04-29
- **決定者**: プロジェクトオーナー
- **関連**: [hitomi新着監視設計書](../../詳細設計/機能別/hitomi新着監視設計書.md)

## コンテキスト

hitomi.laの特定作者を低頻度で監視する処理は、FastAPIが停止している時間帯にも実行できる必要がある。
処理はwatchlist読込、外部NOZOMI取得、差分検出、metadata取得、ローカル永続化を行う単発batchであり、
HTTP requestのライフサイクルや常駐workerを必要としない。

初期実装はWindows Task Schedulerを使用したが、本番配置はLinuxへ移行した。変更前の判断とpathは
[初期Windows運用記録](../../../archive/検証/ADR0004_hitomi監視_初期Windows運用.md)へ凍結する。

## 決定

- 監視処理は`backend/tools/hitomi_monitor.py`の単発CLIとして保つ。
- 定期実行はOS schedulerへ委譲し、現行Linux本番では`deploy/hitomi-monitor.service`と
  `deploy/hitomi-monitor.timer`を正本とする。
- FastAPIは一覧・既読・watchlist・ヘルスAPIを提供し、定期schedulerを内蔵しない。
- `POST /api/hitomi/run-now`は同じapplication entryである`hitomi_monitor.main()`を同期呼出しする。
- Celery、Redis、APScheduler等の常駐依存を追加しない。

## 理由

- FastAPIの起動状態と監視頻度を分離できる。
- oneshot serviceの終了状態とログをsystemdで確認できる。
- 個人LAN・低頻度用途に対してbrokerや常駐workerは過剰である。
- CLIとAPIが同じ処理を使うため、取得・差分・永続化のロジックを複製しない。

## 影響

### 利点

- backend停止中もtimer監視を継続できる。
- CLI単体で診断でき、schedulerの時刻変更がapplication codeへ波及しない。
- 監視処理を短命processとしてfail closedに終了できる。

### 受容するコスト

- systemd unitと`.env`の配置・更新・ログ確認が必要である。
- data directoryの`monitor.lock`を全入口で非blocking取得するため、API／CLI／systemd間の重複実行は拒否される。
- 個別metadata取得失敗は`pending_gallery_ids`へ保持し、成功してDB保存されるまで後続runで再試行する。

## 不採用案

| 案 | 不採用理由 |
|---|---|
| FastAPI background task | backend停止中に実行できず、再起動時の継続契約が複雑になる |
| APScheduler内蔵 | application processとschedulerの責務・可用性が結合する |
| Celery + Redis | 個人用途の低頻度batchに対して運用コストが大きい |

## 再評価条件

- backend常時稼働が前提となり、OS schedulerを廃止する価値が生じた。
- 監視対象や処理時間が増え、直列oneshotでは実行間隔を守れなくなった。
- 複数hostまたは複数userから同時実行する要件が生じた。
- 外部仕様変更によりretry queueや永続job管理が中心責務になった。
