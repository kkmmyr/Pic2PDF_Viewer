---
description: フロントエンド (npm audit) とバックエンド (uv audit) のセキュリティ脆弱性を確認する
---

以下を順番に実行してセキュリティ監査結果を報告してください。

1. **フロントエンド**: `cd frontend && npm audit`
2. **バックエンド**: `cd backend && uv audit`

## 報告フォーマット

```
## npm audit
- 脆弱性数: N 件 (severity 別内訳)
- 対応方針: `npm audit fix` で解決可能 / 手動対応が必要 / 放置可（dev only）

## uv audit
- 脆弱性数: N 件
- 対応方針: （同上）
```

## 対応方針の判断基準

- **`npm audit fix` で解決可能かつ破壊的変更なし**: 即適用してコミット
- **devDependency 由来で本番バンドルに含まれない**: 放置可だが記録しておく
- **本番依存 or 重大度 high/critical**: ユーザーに確認してから対応
- **`uv audit`** でも同様の基準を適用

## 注意

`npm audit fix --force` は semver メジャーバージョンを強制更新するため、テストが通るか確認してから適用すること。
