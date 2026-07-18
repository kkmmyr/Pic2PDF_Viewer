---
name: "source-command-cleanup"
description: "月次のリポジトリ新陳代謝チェック。未使用 skill / 古い docs / 肥大化箇所を可視化する（判断は人間に任せる）"
---

# source-command-cleanup

Use this skill when the user asks to run the migrated source command `cleanup`.

## Command Template

リポジトリの「汚れ」を可視化するための定期点検。**判断はしない、リストするだけ** が原則。
ユーザーが目視で「これは消す」「これは更新」を即決できるよう、4 つの問いに答える形で報告する。

月 1 回程度の運用を想定。

## 進め方

以下 4 つの問いに、それぞれ箇条書きで答える。**勝手に削除・書き換えはしない**。

### 問い 1: 直近 1 ヶ月で保守されていない skill / agent / hook はないか？

1. `.agents/skills/`、`.codex/agents/`、`.codex/hooks/` 配下のファイル一覧を取得
2. `git log --since="1 month ago" --name-only` で同期間に「触れられた」ファイルを取得
3. 現在の環境で skill の発動履歴を確認できる場合だけ、その履歴と突き合わせる。確認できなければ「発動実績は判定不能」と明記する
4. 「最後の git 更新が古く、発動実績も確認できない」ものを候補として列挙

### 問い 2: 半年以上更新されていない docs / memory ファイルはないか？

1. `docs/` 配下と、利用可能なら `~/.codex/memories/` の md ファイル一覧を取得
2. 各ファイルの最終 `git log` 日付（Codex memories は mtime）を取得
3. 6 ヶ月以上経過しているものを列挙。ストック系（`docs/design/` 配下の要件定義・基本設計・詳細設計・環境構築）は **現実とズレている可能性が高い** 警告対象。フロー系（`docs/archive/リファクタリング履歴.md` の完了済み Phase 詳細）は古くて当然なので除外

### 問い 3: Codex の応答が重くなりそうな肥大箇所はないか？

1. `AGENTS.md` の行数（目安: 200 行を超えると注意）
2. `.agents/skills/*/SKILL.md` で 150 行超のもの（references/ に逃がす候補）
3. `.codex/agents/*.toml` で 200 行超のもの
4. 利用可能なら `~/.codex/memories/` のファイル数（生成状態なので手動整理はしない）

### 問い 4: Codex 設定のドリフト（実在しないパス参照）はないか？

以下を読み取り専用で確認する:

- `AGENTS.md`、`.agents/skills/`、`.codex/agents/`、`.codex/hooks/` 内のプロジェクト相対パスが実在するか
- `.agents/skills/*/SKILL.md` の frontmatter と参照ファイルが有効か
- `.codex/hooks.json` が valid JSON で、登録されたスクリプトが実在するか
- `.codex/hooks/tests/run_hook_tests.sh` が全件成功するか
- 検出があれば「ファイル:行 → 参照先」の一覧を記録する（**削除・書き換えはしない。判断はユーザー**）

## 報告フォーマット

```markdown
## 月次お掃除レポート（YYYY-MM-DD）

### 1. 保守・利用状況を確認したい skill / agent / hook
- `.agents/skills/<name>/SKILL.md` — 最終更新 YYYY-MM-DD、発動実績は確認不能
- `.codex/agents/<name>.toml` — 同上

### 2. 鮮度切れ候補の docs / memory（半年以上未更新）
- `docs/design/詳細設計/<file>.md` — 最終更新 YYYY-MM-DD
- `memory/<file>.md` — 最終更新 YYYY-MM-DD

### 3. 肥大化候補
- `AGENTS.md`: NNN 行（目安 200 行）
- `.agents/skills/<name>/SKILL.md`: NNN 行（references/ に逃がす検討余地）
- `.codex/agents/<name>.toml`: NNN 行

### 4. Codex 設定ドリフト（実在しないパス参照）
- ドリフトなし（0 件） / または以下の一覧
  - `.agents/skills/<name>/SKILL.md:NN` -> `path/to/missing`

### 異常なし
- <該当項目があれば各セクションに記載、問題なければこの行で完了>
```

## 注意

- **このコマンドは可視化のみ**。削除・書き換えはユーザー承認後に別途実施
- 「半年以上未更新 = 即削除」ではない。安定して動いているコードに対応する docs は更新が少なくて当然
- フロー系（リファクタ計画の完了 Phase 詳細）が古いのは正常。ストック系（要件・設計・環境構築の事実メモ）が古いと害になる
- 報告が長くなりそうなら、各セクション最大 10 件で打ち切り、件数だけ「他 N 件」と添える

## 関連

- 永続メモリとの突合 → `/sync-memory`（git log との一致確認）
- 大きいソースファイル → `/big-files`（リファクタ対象探索）
