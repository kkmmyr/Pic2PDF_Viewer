---
description: フロントエンドの TypeScript 型チェックを実行する
---

`cd frontend && npx tsc --noEmit` を実行して型エラーの有無を報告してください。

- エラーなし: 「型エラーなし」と一行で報告
- エラーあり: ファイルパス・行番号・エラー内容を整形して報告。ファイルは `[path:line](path#L<line>)` 形式の clickable リンクで示す
