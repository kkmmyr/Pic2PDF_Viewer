---
description: 月次のリポジトリ新陳代謝チェック。未使用 skill / 古い docs / 肥大化箇所を可視化する（判断は人間に任せる）
---

リポジトリの「汚れ」を可視化するための定期点検。**判断はしない、リストするだけ** が原則。
ユーザーが目視で「これは消す」「これは更新」を即決できるよう、4 つの問いに答える形で報告する。

月 1 回程度の運用を想定。

## 進め方

以下 4 つの問いに、それぞれ箇条書きで答える。**勝手に削除・書き換えはしない**。

### 問い 1: 直近 1 ヶ月で発動していない skill / command はないか？

1. `.claude/skills/` `.claude/commands/` 配下のファイル一覧を取得
2. `git log --since="1 month ago" --name-only` で同期間に「触れられた」ファイルを取得
3. プロジェクトの memory（`C:\Users\amashio\.claude\projects\d--61-tool-Pic2PDF-Viewer\memory\`）に skill 名 / コマンド名で grep し、1 ヶ月以内に呼び出された痕跡があるか確認
4. 「最後の git 更新が古く、かつ memory にも出てこない」ものを候補として列挙

### 問い 2: 半年以上更新されていない docs / memory ファイルはないか？

1. `docs/` 配下と memory の md ファイル一覧を取得
2. 各ファイルの最終 `git log` 日付（memory は mtime）を取得
3. 6 ヶ月以上経過しているものを列挙。ストック系（`docs/design/` 配下の要件定義・基本設計・詳細設計・環境構築）は **現実とズレている可能性が高い** 警告対象。フロー系（`docs/archive/リファクタリング履歴.md` の完了済み Phase 詳細）は古くて当然なので除外

### 問い 3: Claude の応答が重くなりそうな肥大箇所はないか？

1. `.claude/CLAUDE.md` の行数（目安: 200 行を超えると注意）
2. `.claude/skills/*/SKILL.md` で 150 行超のもの（references/ に逃がす候補）
3. `MEMORY.md` の行数（目安: 200 行を超えると後ろが切り捨てられる）
4. 個別 memory ファイル数（数十件を超えると意味的な整理が必要）

### 問い 4: .claude のドリフト（実在しないパス参照）はないか？

以下を実行して列挙する:

```bash
cd backend && uv run python ../scripts/maintenance/check_claude_drift.py
```

- 検出 0 件なら「ドリフトなし」と記録する
- 検出があれば「ファイル:行 → 参照先」の一覧を記録する（**削除・書き換えはしない。判断はユーザー**）
- パス参照の他に、`.claude/README.md` のスキル一覧表・コマンド一覧表と実体（`.claude/skills/` / `.claude/commands/`）とのドリフト（未掲載 / 記載だが実体なし）も同スクリプトが `[.claude/README.md registry]` セクションで報告する

## 報告フォーマット

```markdown
## 月次お掃除レポート（YYYY-MM-DD）

### 1. 未使用候補の skill / command
- `.claude/skills/<name>/SKILL.md` — 最終更新 YYYY-MM-DD、直近 1 ヶ月で呼び出し痕跡なし
- `.claude/commands/<name>.md` — 同上

### 2. 鮮度切れ候補の docs / memory（半年以上未更新）
- `docs/design/詳細設計/<file>.md` — 最終更新 YYYY-MM-DD
- `memory/<file>.md` — 最終更新 YYYY-MM-DD

### 3. 肥大化候補
- `.claude/CLAUDE.md`: NNN 行（目安 200 行）
- `MEMORY.md`: NNN 行（200 行超は末尾が切り捨てられます）
- `.claude/skills/<name>/SKILL.md`: NNN 行（references/ に逃がす検討余地）

### 4. .claude ドリフト（実在しないパス参照）
- `check_claude_drift.py` 実行結果: ドリフトなし（0 件） / または以下の一覧
  - `.claude/skills/<name>/SKILL.md:NN` -> `path/to/missing`

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
