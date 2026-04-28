## テスト方針

### 何をテストするか

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

### バックエンドテストパターン (pytest)

#### 推奨: `TestClient` + `tmp_path` + `monkeypatch`

```python
@pytest.fixture
def view_client(tmp_path, monkeypatch):
    """meta_store の DATA_DIR を tmp_path に差し替えた TestClient を提供する。"""
    monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
    from main import app
    return TestClient(app)
```

- `tmp_path` でテストごとにディスクを隔離（cleanup 不要）
- `monkeypatch` で外部依存（パス・関数）を差し替え
- `TestClient` で HTTP 層も含めてエンドツーエンドに近い形でテスト

#### モックは最小限

- 外部 API（Web 検索 / Gemma）など決定論的でないものは `monkeypatch` でモック
- ファイル I/O はモックせず `tmp_path` に実書き込みする
- 「DB をモックして単体テスト」よりも「実 I/O を tmp_path に流す」を優先

#### テスト命名規則

- クラス名: `TestXxx`（対象メソッド・機能）
- メソッド名: `test_<挙動>` を平文で（例: `test_overwrite_all_preserves_view_count`）
- assert は **最小限**。1 テスト = 1 シナリオ。

### フロントエンドテストパターン (vitest)

#### フックのテスト: `renderHook`

```ts
import { renderHook } from '@testing-library/react';

const { result } = renderHook(() =>
    useLibraryFilter({ pdfs, directories, searchText: 'beta', ... })
);
expect(result.current.filteredPdfs).toEqual([...]);
```

- フックは `renderHook` で単体テスト
- API 呼び出しは `apiClient` を `vi.fn()` でモック（`useBookMeta.test.ts` 参照）

#### コンポーネントのテストは原則書かない

- React コンポーネントの DOM 検証は工数対効果が悪い
- ロジックはフックに切り出してテストする方針（既存 `useEditMode` / `useSpreadMode` 等）
- ダイアログ等のインタラクションはユーザーが手動確認

### 副作用のあるロジック追加時のチェックリスト

新しいロジックを追加するときは以下を考慮:
1. 副作用があるか？（ファイル I/O・meta.json 更新・ジョブ起動）→ あればテスト必須
2. 既存の副作用ロジックを変更したか？→ 既存テストが通るか確認 + 新パスのテスト追加
3. 失敗時のロールバックがあるか？→ ロールバックパスもテスト

### テスト実行

- `/test` コマンドで backend pytest + frontend vitest を順次実行できる
- 個別実行: backend は `cd backend && uv run pytest tests/test_xxx.py -v`、frontend は `cd frontend && npx vitest run src/test/xxx.test.ts`
- バグ修正コミットには **必ず再現テストを含める**（Phase 15-4 が好例）
