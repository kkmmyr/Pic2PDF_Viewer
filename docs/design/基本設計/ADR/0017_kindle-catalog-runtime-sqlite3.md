# ADR-0017: Kindleカタログの実行時アクセスにsqlite3を使用

- **Status**: Accepted
- **Date**: 2026-07-26
- **決定者**: 開発者
- **関連**: [ADR-0015](0015_sqlite-runtime-queries.md)、[ADR-0016](0016_kindle-catalog-sqlite.md)、[Kindle購入カタログ設計](../../詳細設計/機能別/Kindle購入カタログ設計.md)

## コンテキスト

ADR-0016ではKindle購入カタログを専用SQLite DBで開始し、SQLAlchemy URLから
接続する方針を記載した。一方、実装は次のように責務を分けて通常運用へ移行している。

- SQLModel: table構造とAlembic autogenerate用metadata。
- Alembic: schema変更の正本。
- `services/kindle_catalog/connection.py`: 短命な`sqlite3.Connection`。
- 各service: FTSではない単純query、明示transaction、`sqlite3.Row`。

利用者1人、FastAPI単一process、Windows agent 1台の現行運用ではconnection poolや
ORM sessionを導入する利得が小さい。既存の`meta2.db` / `novel.db`も
[ADR-0015](0015_sqlite-runtime-queries.md)により、schema定義と実行時queryを分離している。

## 検討した選択肢

| 選択肢 | 内容 | 判断 |
|---|---|---|
| A. SQLAlchemy ORMへ移行 | 全queryをSessionとmodelへ置換 | 現行規模では移行コストと抽象化が上回る |
| B. SQLAlchemy Coreへ移行 | queryをCore式へ置換 | PostgreSQL互換は高まるが、現在必要な機能ではない |
| **C. sqlite3を継続** | schemaはSQLModel/Alembic、実行時は短命sqlite3 | 採用 |

## 決定

Kindle購入カタログの実行時アクセスは`sqlite3`を使用する。

- 接続は`connection.open_db()` / `with_db()`だけで作成する。
- 接続時にforeign keys、WAL、busy timeoutを有効化する。
- `with_db()`がcommit、rollback、closeを保証する。
- 書き込みは短いtransactionに限定する。
- SQLModel classを実行時ORM modelとして使用しない。
- Alembic migrationをschema変更の正本とする。

PostgreSQLへの移行可能性は、現在のqueryをSQLAlchemy風に見せることで担保しない。
ADR-0016の再評価条件が成立した場合に、repository interface、data migration、
transaction・locking、backupを含む別計画とADRを作成する。

## 根拠

- 現行queryはSQLite固有のWALと`BEGIN IMMEDIATE`を含み、DB差し替えだけでは移行できない。
- 短命接続によりcommit / rollback / closeの境界を追跡しやすい。
- ORMへ移しても、capture package公開と`meta2.db`更新を跨ぐ補償処理は単純化されない。
- novel / meta DBと同じ「schema定義とruntime queryの分離」方針になる。

## 結果

### ポジティブ

- 実装と設計書の不一致がなくなる。
- transactionとSQLite pragmaの責務が`connection.py`に集約される。
- ORM移行を前提とした不要な抽象化を避けられる。

### ネガティブ

- SQL文字列とRow変換は手動管理する。
- PostgreSQL移行時はrepositoryとqueryの書き換えが必要になる。
- schema変更時はSQLModel、migration、該当SQLの3点を確認する必要がある。

## 将来の再評価条件

ADR-0016の条件に加え、次の場合に再評価する。

- 複数agentまたは複数FastAPI workerが同じDBへ常時書き込む。
- SQLite固有queryがservice全体へ拡散し、connection層だけで隔離できなくなる。
- DB engine差し替えが承認済み機能要件になる。
