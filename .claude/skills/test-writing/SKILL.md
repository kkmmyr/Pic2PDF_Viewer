---
name: test-writing
description: pytest（バックエンド）/ vitest（フロントエンド）のテストコードを新規追加・修正する際に発動。何をテストすべきか、副作用ロジック追加時のチェックリスト、テスト実行方法を含む。詳細なパターン例は references/ を参照。
---

# テスト方針

## 何をテストするか

**必須テスト対象** — 副作用があり、かつ壊れると気づきにくいロジック。

| 領域 | 対象 | テスト済み箇所 |
|---|---|---|
| meta.json 更新 | `update_meta_locked` の lambda、view_count / authors のマージ規則 | `tests/test_meta.py` |
| ファイル操作 | `FileManager.move_with_assets` / `rename_with_assets` のロールバック | `tests/test_file_manager.py` |
| パスバリデーション | `validate_safe_path` / `validate_safe_name`（セキュリティ）| `tests/test_path_utils.py` |
| PDF 生成フロー | `_collect_images` の natsort、`scan_and_generate` の ZIP/Folder 分岐、`batch_compress` のスキップ判定 | `tests/test_pdf_generator.py` |
| ジョブ管理 | `JobStore.get_active_current_item()` の状態遷移 | 未実装（追加候補）|
| auto-fill | mode 別ターゲット選別、view_count 保持 | `tests/test_meta.py` |
| ライブラリフィルタ | searchText / authorFilter / currentPath の組み合わせ | `test/useLibraryFilter.test.ts` |
| ソート | `useSortedPdfs` の各ソート種別 | `test/useSortedPdfs.test.ts` |
| ナビゲーション | `useReaderNavigation` の見開き計算 | `test/useReaderNavigation.test.ts` |

**やらないこと**:
- UI スナップショットテスト（メンテコスト過大）
- 統合 E2E テスト（このプロジェクト規模では過剰）
- 機械的なカバレッジ追求（数値ではなく「壊れやすい箇所の網羅」で評価）
- 単純な getter / プロパティ取得のテスト

## 副作用のあるロジック追加時のチェックリスト

新しいロジックを追加するときは以下を考慮:
1. 副作用があるか？（ファイル I/O・meta.json 更新・ジョブ起動）→ あればテスト必須
2. 既存の副作用ロジックを変更したか？→ 既存テストが通るか確認 + 新パスのテスト追加
3. 失敗時のロールバックがあるか？→ ロールバックパスもテスト

## テスト実行

- `/test` コマンドで backend pytest + frontend vitest を順次実行できる
- 個別実行: backend は `cd backend && uv run pytest tests/test_xxx.py -v`、frontend は `cd frontend && npx vitest run src/test/xxx.test.ts`
- バグ修正コミットには **必ず再現テストを含める**（Phase 15-4 が好例）

## 詳細なテストパターン

書こうとしているテストの種類に応じて以下を参照:

- **バックエンド (pytest)** → `references/backend-patterns.md`
  TestClient + tmp_path + monkeypatch のフィクスチャパターン、モック方針、命名規則
- **フロントエンド (vitest)** → `references/frontend-patterns.md`
  renderHook によるフック単体テスト、コンポーネントテストを書かない方針
