---
name: worktree-workflow
description: git worktree を使った並列作業（大型リファクタ・機能開発）を始める際に発動。ブランチ命名規則、worktree 作成・削除手順、.venv が残存する問題の注意書きを含む。
---

# Worktree 運用ルール

大きな作業（Phase 単位のリファクタ・新機能開発など）は `git worktree` で隔離ブランチを作り、メインブランチに影響を与えずに進める。

## ブランチ・ディレクトリ命名

```
ブランチ名  : worktree-<作業識別子>   例: worktree-phase-80-novel-search
worktree パス: .claude/worktrees/<作業識別子>/
```

- `<作業識別子>` はケバブケース。Phase 番号がある場合は含める。
- `.claude/worktrees/` は `.gitignore` 対象なのでリモートには上がらない。

## 作成手順

```powershell
# 1. ブランチ + worktree を同時に作成
git worktree add .claude/worktrees/<作業識別子> -b worktree-<作業識別子>

# 2. worktree 内で依存をインストール（backend を使う場合）
Set-Location .claude/worktrees/<作業識別子>/backend
uv sync
```

## 削除手順

```powershell
# 作業完了・マージ後に削除
git worktree remove .claude/worktrees/<作業識別子>
git branch -d worktree-<作業識別子>
```

## 注意: backend/.venv の残存

worktree 内で `uv sync` を実行すると `backend/.venv/` が作られる。  
`git worktree remove` は追跡外ファイルを削除しないため、`.venv/` が残り続ける。  
不要になったら手動で削除する:

```powershell
Remove-Item -Recurse -Force .claude/worktrees/<作業識別子>/backend/.venv
git worktree remove .claude/worktrees/<作業識別子>
```

## マージ後の後始末チェックリスト

1. `git worktree list` で不要な worktree が残っていないか確認
2. `.claude/worktrees/` に古いディレクトリが残っていれば削除
3. worktree ブランチ（`worktree-*`）を削除
