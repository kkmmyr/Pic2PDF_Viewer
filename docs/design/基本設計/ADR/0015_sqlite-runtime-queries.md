# ADR-0015: SQLite実行時クエリとSQLModelスキーマ定義を分離

- **Status**: Accepted
- **Date**: 2026-07-19
- **決定者**: 開発者
- **関連**: [ADR-0012](0012_sqlmodel-orm.md)、[小説RAG データ設計](../../詳細設計/機能別/小説RAG_データ.md)

## コンテキスト

ADR-0012 は `novel.db` の全クエリを SQLModel ORM へ移行するとしたが、FTS5、LanceDBとの
結合、既存の行形式を扱う実行時コードは生 `sqlite3` のまま運用されている。一方、SQLModel
定義と Alembic はスキーマ差分検出に利用され、詳細設計もこの実態を記録している。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. 全クエリをSQLModelへ再移行 | ADR-0012を完遂 | FTS5・大量バッチ・LanceDB連携で生SQLを包むコストに対する利得が小さい |
| **B. スキーマと実行時アクセスを分離** | Alembic/SQLModelをスキーマ、sqlite3を実行時アクセスに使用 | （採用）現行実装を正確に表し、責務を明確化できる |
| C. SQLModelを撤去 | Alembicを手書きDDLだけで管理 | autogenerateの型定義を失う |

## 決定

`novel.db` は Alembic migration をスキーマの唯一の真実の源とし、SQLModel定義を
autogenerate補助に使う。実行時クエリは生 `sqlite3` を許可する。`meta2.db` も小規模な
専用ストアとして `sqlite3` を使う。接続はcloseを保証する短命context managerで扱い、
書き込みはtransaction内で行う。

## 根拠

- FTS5仮想テーブルとLanceDB融合処理はSQLを明示した方が挙動と性能を追いやすい
- 個人向け単一プロセス構成ではconnection poolの複雑さが不要
- スキーマ定義とmigration運用はSQLModel/Alembicで維持できる

## 結果（Consequences）

### ポジティブ

- 実装と設計の矛盾を解消し、不要なORM再調査を防ぐ
- 接続寿命とtransaction境界を共通context managerで統一できる

### ネガティブ・受容したコスト

- Rowからアプリ型への変換とSQL文字列は引き続き手動管理する
- カラム変更時はSQLModel、migration、該当SQLの3点確認が必要になる

### 影響範囲

- `backend/services/meta_db.py`
- `backend/services/meta_store.py`
- `backend/services/novel_db/connection.py` と各クエリサービス

## 将来の再評価条件

- 複数プロセス・複数ユーザー化でconnection poolが必要になった場合
- SQLModelでFTS5を含む現行クエリを簡潔かつ型安全に表現できるようになった場合
