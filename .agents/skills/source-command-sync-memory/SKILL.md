---
name: "source-command-sync-memory"
description: "Codex memories の内容を git log・計画書と突き合わせ、古い記憶と永続化すべき事実を報告する"
---

# source-command-sync-memory

Use this skill when the user asks to run the migrated source command `sync-memory`.

## Command Template

利用可能なら `~/.codex/memories/` 配下の Codex ローカルメモリと、
プロジェクトの実態（git log / 計画書 / 完了済みタスク）を照合し、ズレを報告する。

メモリは手動更新する設計だが、頻度が落ちると古い情報を返してしまう（過去事例:
「Phase 18 まで完了」と書いてあるのに実態は Phase 22 まで完了済みだった）。
Codex memories は生成状態であり、手動編集を正本にしない。永続化が必要な事実は `AGENTS.md` または `docs/` に反映する。

## 進め方

1. **メモリ機能と保存先を確認**
    - `~/.codex/memories/` が存在しなければ「ローカルメモリなし」と報告し、手順 2 以降は必要な場合だけ続ける
    - 存在する場合は関連する生成メモリを読み、古いプロジェクト事実を抽出する

2. **git の最新状態を取得**
    - `git log --oneline -20` で直近 20 コミット
    - `git log --all --oneline -5 --grep="Phase"` で Phase 系コミットの最新

3. **計画書と突き合わせ**
    - `docs/log/計画/リファクタリング計画書.md` を Read
    - 計画書の「Phase N まで完了」とメモリの記述が一致するか確認

4. **古い記憶を突き合わせ**
    - メモリに書かれた候補が、git log や計画書ですでに完了していないか確認
    - 完了済みなら「古い記憶」としてマークする

5. **ズレと永続化先を報告**
    - 生成メモリ自体は編集しない
    - 今後も必須の事実なら `AGENTS.md`、設計・進捗の事実なら `docs/` の更新候補として提示する

## 報告フォーマット

```markdown
## メモリ同期チェック結果

### ✅ 一致
- project_refactoring.md: 「Phase NN まで完了」 ↔ 計画書最終 Phase: NN

### ⚠️ 古い記憶
- 「DLsite 直接クエリ動作確認」 → コミット xxxxx で完了済み
- 「Phase 18 完了」 → 実態は Phase 22 完了

### 📝 正本への反映候補（任意）
- 継続して必要な運用ルール → `AGENTS.md` に追記するか?
- 設計・進捗の事実 → 該当する `docs/` に反映するか?
```

## 注意

- Codex memories は生成状態なので、手動で書き換えない
- ズレが無ければ「ズレなし」と一行で報告して終了（無理に何かを足さない）
- `AGENTS.md` / `docs/` を更新する場合は、通常の docs・git ワークフローに従う
