# バックエンドテストパターン (pytest)

## 推奨: 共有フィクスチャ `tmp_data_dir` / `client`（`tests/conftest.py`）

router テスト・統合テストは conftest の共有フィクスチャを使う。`tmp_data_dir` が `config` のモジュールレベル定数（`DATA_DIR` / `META_DB_DIR` / 各ソースのディレクトリ群）と settings オブジェクトを tmp_path 配下に差し替え、`client` はその適用済み `TestClient(app)` を返す。

```python
def test_xxx(client, tmp_data_dir, make_pdf):
    make_pdf(os.path.join(tmp_data_dir["main"], "book.pdf"))
    res = client.get("/api/...")
```

meta.db だけ差し替えれば足りる単発テストでは、`config.META_DB_DIR` のみを monkeypatch する軽量版でもよい（`tests/test_meta.py` の実例）:

```python
@pytest.fixture
def view_client(tmp_path, monkeypatch):
    """meta_db の META_DB_DIR を tmp_path に差し替えた TestClient を提供する。"""
    import config

    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path))
    from main import app

    return TestClient(app)
```

- `tmp_path` でテストごとにディスクを隔離（cleanup 不要）
- `monkeypatch` は `config` モジュールの属性を差し替える（全モジュールが `import config; config.X` で call-time 参照するため config 本体のみで十分）。文字列パス指定の `"services.meta_store.DATA_DIR"` のような属性は存在しない
- `TestClient` で HTTP 層も含めてエンドツーエンドに近い形でテスト

## モックは最小限

- 外部 API（Web 検索 / Gemma）など決定論的でないものは `monkeypatch` でモック
- ファイル I/O はモックせず `tmp_path` に実書き込みする
- 「DB をモックして単体テスト」よりも「実 I/O を tmp_path に流す」を優先

## テスト命名規則

- クラス名: `TestXxx`（対象メソッド・機能）
- メソッド名: `test_<挙動>` を平文で（例: `test_overwrite_all_preserves_view_count`）
- assert は **最小限**。1 テスト = 1 シナリオ。
