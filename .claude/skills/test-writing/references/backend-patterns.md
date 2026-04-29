# バックエンドテストパターン (pytest)

## 推奨: `TestClient` + `tmp_path` + `monkeypatch`

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

## モックは最小限

- 外部 API（Web 検索 / Gemma）など決定論的でないものは `monkeypatch` でモック
- ファイル I/O はモックせず `tmp_path` に実書き込みする
- 「DB をモックして単体テスト」よりも「実 I/O を tmp_path に流す」を優先

## テスト命名規則

- クラス名: `TestXxx`（対象メソッド・機能）
- メソッド名: `test_<挙動>` を平文で（例: `test_overwrite_all_preserves_view_count`）
- assert は **最小限**。1 テスト = 1 シナリオ。
