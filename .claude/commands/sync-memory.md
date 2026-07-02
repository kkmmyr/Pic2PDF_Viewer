---
description: memory/ の内容を git log・リファクタリング計画書・pending_tasks と突き合わせ、ズレを修正する
---

`C:\Users\amashio\.claude\projects\d--61-tool-Pic2PDF-Viewer\memory\` 配下の永続メモリと
プロジェクトの実態（git log / 計画書 / 完了済みタスク）を照合し、ズレた箇所だけ更新する。

メモリは手動更新する設計だが、頻度が落ちると古い情報を返してしまう（過去事例:
「Phase 18 まで完了」と書いてあるのに実態は Phase 22 まで完了済みだった）。
週次〜月次で叩いて鮮度を保つ運用を想定する。

## 進め方

1. **メモリの全エントリを Read**
    - `MEMORY.md` から index を取得
    - 各 `.md` ファイルを Read（`pending_tasks.md` / `project_refactoring.md` 等）

2. **git の最新状態を取得**
    - `git log --oneline -20` で直近 20 コミット
    - `git log --all --oneline -5 --grep="Phase"` で Phase 系コミットの最新

3. **計画書と突き合わせ**
    - `docs/log/計画/リファクタリング計画書.md` を Read
    - 計画書の「Phase N まで完了」とメモリの記述が一致するか確認

4. **pending_tasks を突き合わせ**
    - `pending_tasks.md` に書かれた候補が、git log や計画書ですでに完了していないか確認
    - 完了済みなら削除候補としてマーク

5. **ズレを報告 → ユーザー承認後に Edit で更新**
    - 「これとこれを更新します。OK？」と提示
    - 承認後だけ Write/Edit する（勝手に書き換えない）

## 報告フォーマット

```markdown
## メモリ同期チェック結果

### ✅ 一致
- project_refactoring.md: 「Phase NN まで完了」 ↔ 計画書最終 Phase: NN

### ⚠️ ズレ（要更新）
- pending_tasks.md A: 「DLsite 直接クエリ動作確認」 → コミット xxxxx で完了済み。削除候補
- project_refactoring.md: 「Phase 18 完了」 → 実態は Phase 22 完了。本文を Phase 22 ベースに書き換え

### 📝 新規追加候補（任意）
- 直近で新ロジック追加 → memory/<新エントリ名>.md として記録するか?
```

## 注意

- **更新前に必ず承認を取る**。memory は次回以降のセッションに影響するため
- ズレが無ければ「ズレなし」と一行で報告して終了（無理に何かを足さない）
- `MEMORY.md` の index 行も忘れず追従させる（ファイル削除時に index も削除）
- `originSessionId` フィールドは触らない（既存値を保持）
