# ADR-0016: Kindle 購入カタログの初期データストアに SQLite を採用

- **Status**: Accepted（実行時アクセス方式はADR-0017で追補）
- **Date**: 2026-07-25
- **決定者**: 開発者
- **関連**: [Kindle 購入カタログ設計](../../詳細設計/機能別/Kindle購入カタログ設計.md)、[完了記録](../../../archive/Kindle購入カタログ統合_実装計画.md)、[ADR-0017](0017_kindle-catalog-runtime-sqlite3.md)

## コンテキスト

`kindle購入履歴` の購入書籍 11,419 件、購入履歴 11,415 件、シリーズ 1,796 件を Pic2PDF_Viewer の Linux サーバーへ移し、検索・差分取り込み・既存画像との紐付け・キャプチャジョブを管理する。

PostgreSQL は同時書き込みと複数プロセス運用に強い一方、専用サービス、資格情報、dump/restore、バージョン更新の運用が増える。現行システムは個人 LAN の単一ユーザー用で、書き込みは Amazon データ取り込み、手動紐付け、キャプチャ状態更新に限られる。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| **A. 専用 SQLite DB** | `META_DB_DIR/kindle_catalog.db`、WAL + foreign keys + busy timeout | —（採用） |
| B. PostgreSQL | Linux ローカルの専用 DB と非 superuser role | 現時点の件数・同時利用数に対して運用負担が上回る |
| C. `meta2.db` へ同居 | 既存メタデータ DB にカタログテーブルを追加 | バックアップ、移行、障害範囲、将来の PostgreSQL 移行を分離できない |

## 決定

Kindle 購入カタログは専用 SQLite DB `kindle_catalog.db` で開始する。SQLModel でスキーマを定義し、実行時クエリは短命な transaction で行う。接続時に WAL、foreign keys、busy timeout を有効化する。

実装後の実行時アクセス方式は[ADR-0017](0017_kindle-catalog-runtime-sqlite3.md)で追補する。
現行はSQLModel/Alembicをschema管理に、`sqlite3`を実行時queryに使用する。
PostgreSQL移行は接続URLの差し替えだけでは行わず、移行条件成立時にrepository境界を含む
独立ADRを作成する。

## 根拠

- 実測 11,419 冊は SQLite の検索・索引処理に対して小規模である。
- 利用者は 1 人、FastAPI も単一管理サーバーであり、競合する書き込みは短時間かつ低頻度である。
- 既存運用には SQLite のバックアップ・復元試験があり、同じ保守経路へ追加できる。
- カタログを `meta2.db` から分離するため、後日の PostgreSQL 移行で閲覧メタデータへ影響しない。

## 結果（Consequences）

### ポジティブ

- PostgreSQL サービスを新設せず Linux へ導入できる。
- レガシー SQLite DB から transaction 単位で移行しやすい。
- DB ファイル単位でバックアップ、整合性検査、復元試験ができる。

### ネガティブ・受容したコスト

- 長時間の書き込み transaction を避け、取り込みをファイル単位で分割する必要がある。
- 複数 worker/process から高頻度に状態更新する運用には向かない。

### 影響範囲

- `backend/services/kindle_catalog/`
- `backend/routers/kindle_catalog.py`
- Linux バックアップ・復元試験
- Kindle 購入カタログの環境変数と運用手順

## 将来の再評価条件

次のいずれかが成立したら PostgreSQL 移行 ADR を作る。

- FastAPI を複数 worker で常用する。
- 複数ユーザーまたは複数 Windows エージェントが同時更新する。
- `database is locked` が通常運用で反復する。
- 取り込み中の API 書き込み p95 が 500 ms を継続して超える。
- 1 回の差分取り込みが 5 分を超え、transaction 分割でも改善しない。
