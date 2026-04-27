---
description: バックエンド・フロントエンドの行数が多いファイル上位 10 件を表示する（次のリファクタ対象探索用）
---

以下のコマンドを実行して、肥大化候補ファイルを報告してください。

**バックエンド** (Python):
```bash
find backend -type f -name "*.py" ! -path "*/.venv/*" ! -path "*/__pycache__/*" ! -path "*/tests/*" -exec wc -l {} + | sort -rn | head -11
```

**フロントエンド** (TypeScript):
```bash
find frontend/src -type f \( -name "*.ts" -o -name "*.tsx" \) ! -path "*/test/*" -exec wc -l {} + | sort -rn | head -11
```

報告フォーマット：
- 各カテゴリで上位 10 件を Markdown 表で（行数 / ファイルパス[clickable]）
- 200 行超のファイルには「⚠️ 分割候補」のマークを付ける
- 各カテゴリの末尾に「目立つ肥大化なし」または「N 件が分割検討対象」のサマリ

最後に、もし 200 行超があれば「リファクタ計画書に Phase XX として追記する候補」を 1 行で提案。
