# ADR-0012: novel.db クエリを SQLModel ORM に移行

- **Status**: Accepted
- **Date**: 2026-06-11
- **決定者**: 開発者
- **関連**: Phase 1-2（Alembic 一本化）/ Phase 1-3 / commit `eb04fc0`

## コンテキスト

`novel.db` へのアクセスが全クエリ生 SQL 文字列 + タプルパラメータで実装されており、以下の問題があった：

- `sqlite3.Row → dict` の手書き変換が多数存在し、カラム追加・リネーム時に複数箇所を修正する必要があった
- `meta.db`（threading.Lock）と `novel.db`（DB トランザクション任せ）でロック方式が非対称
- `save_meta` が `DELETE → 全行 INSERT` の非効率なパターンで実装されていた

Pydantic v2 が既に導入済みで、SQLModel（Pydantic v2 + SQLAlchemy ベース）は FastAPI と親和性が高い。また Phase 1-2 で Alembic をスキーマの唯一の真実の源に一本化済みで、SQLModel の `MetaData` を Alembic に渡せる状態になっていた。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. 生 SQL 継続 | 変更なし | カラム追加ごとに Row→dict 手書きが増え続ける |
| B. SQLAlchemy Core のみ | 型安全な式ベース SQL | FastAPI との Pydantic 統合が手動になる |
| **C. SQLModel** | Pydantic v2 + SQLAlchemy を統合した ORM | （採用）FastAPI/Pydantic v2 と同一エコシステム |

## 決定

`novel.db` の全クエリを SQLModel で書き換える。`SQLModel.metadata` を Alembic の `target_metadata` に渡しスキーマを一元管理する。`save_meta` を `INSERT … ON CONFLICT DO UPDATE` の差分更新 + 明示トランザクションに変更する。

## 根拠

- FastAPI のルータが既に Pydantic モデルを使っており、SQLModel のテーブルクラスとレスポンスモデルを共有できる
- Row→dict 変換が消え、カラム追加時の変更箇所が Model 定義の 1 箇所に集約される
- `INSERT … ON CONFLICT DO UPDATE` により save_meta が冪等になり、トランザクション内での並行書き込みリスクが低下する

## 結果（Consequences）

### ポジティブ
- カラム追加・リネームの変更箇所が 1 箇所（Model クラス）に集約
- Alembic `autogenerate` が SQLModel のメタデータを参照できるようになり、マイグレーション生成が自動化
- `save_meta` の DELETE → 全 INSERT パターンが消え、性能と安全性が向上

### ネガティブ・受容したコスト
- SQLModel は SQLAlchemy 2.x の上に構築されており、バージョン依存が発生する
- 既存の生 SQL テストを SQLModel ベースに書き直すコスト（pytest 914 件を通すまでの修正作業）

### 影響範囲
- `backend/services/novel_db/models.py`（SQLModel テーブル定義に全面移行）
- `backend/services/novel_db/` 配下の全クエリファイル
- `backend/alembic/env.py`（target_metadata を SQLModel.metadata に変更）

## 将来の再評価条件

- SQLModel が SQLAlchemy 3.x に追従しない場合は SQLAlchemy Core + TypedDict の手書き変換に戻す可能性がある
- LanceDB（ベクトル DB）は対象外。本 ADR は SQLite（novel.db / meta2.db）のみを扱う
