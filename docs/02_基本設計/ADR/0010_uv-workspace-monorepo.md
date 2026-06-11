# ADR-0010: uv workspace でモノレポ化（common/llm を repo 内に取り込み）

- **Status**: Accepted
- **Date**: 2026-06-11
- **決定者**: 開発者
- **関連**: ADR-0005（uv 導入）/ Phase 0-1 / commit `c7b85a0`

## コンテキスト

`backend/pyproject.toml` が `qwen-common = { path = "../../common/llm", editable = true }` で **repo 外**の `D:\61.tool\common\llm` を参照していた。この構成では：

- クローン単体でビルド不可（`common/llm` が別ディレクトリに存在することを前提とする）
- Python 環境が `backend/` / `kindle-pdf/` / `common/llm` / `common/ocr` に分散し、`uv lock` が一元化されていない
- CI ランナー（Linux）がクローン単体でテストを実行できない

`uv workspace` を使えば複数の Python パッケージを単一の `.venv` と `uv.lock` で管理でき、editable インストールも `{ workspace = true }` で完結する。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. repo 外参照を維持 | 変更なし | CI 不可・クローン単体ビルド不可のまま |
| B. `common/llm` を git submodule 化 | 共有ライブラリを submodule として管理 | submodule の sync コストが高い。CI での checkout も煩雑 |
| **C. `common/llm` を repo 内にコピー + uv workspace 化** | `common/llm` を `common/llm/` として repo に取り込み、ルート `pyproject.toml` で workspace を定義 | （採用） |

## 決定

`common/llm/` を repo 内（`d:\61.tool\Pic2PDF_Viewer\common\llm\`）にコピーし、ルート `pyproject.toml` を新規作成して `[tool.uv.workspace] members = ["backend", "kindle-pdf", "common/llm"]` を定義する。`backend/pyproject.toml` の依存を `{ workspace = true }` に変更する。

## 根拠

- クローン → `uv sync` 1 コマンドでビルド可能になり、CI ランナー（Linux）でもテストが回る
- 共有ライブラリの変更が即座に backend/kindle-pdf に反映される（editable と同等）
- `common/llm` は novel-game-ocr など他プロジェクトからも参照されているが、コピー後は各プロジェクトが独自に保持する形になり参照切断のリスクが低い

## 結果（Consequences）

### ポジティブ
- クローン単体で `uv sync` → `uv run pytest` が通る
- CI Phase 0-2 の前提が整った
- Python 環境が 1 つの `.venv`（ルート）に統一された

### ネガティブ・受容したコスト
- `common/llm` の変更を他プロジェクト（novel-game-ocr 等）と手動で同期する必要がある
- repo サイズが微増する

### 影響範囲
- ルート `pyproject.toml`（新規）
- `backend/pyproject.toml`（qwen-common 参照を workspace = true に変更）
- `.venv/` がルートに生成される（backend/ 直下からルートへ移動）

## 将来の再評価条件

- `common/llm` が複数プロジェクト間で頻繁に変更される場合は git submodule や別 repo + PyPI 公開を検討
