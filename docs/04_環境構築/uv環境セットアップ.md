# uv 環境セットアップ

本プロジェクトの Python 環境は [uv](https://docs.astral.sh/uv/) で管理しています。

## uv のインストール

PowerShell（管理者権限不要）：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

または winget：

```powershell
winget install --id=astral-sh.uv -e
```

インストール確認：

```bash
uv --version
```

## プロジェクト構成

| ディレクトリ | pyproject.toml | 用途 |
|---|---|---|
| `backend/` | あり | FastAPI バックエンド |
| `kindle-pdf/` | あり | Kindle キャプチャ・OCR バッチ |
| `D:\61.tool\common\ocr\` | なし（共有 venv） | yomitoku OCR 実行環境（kindle-pdf から参照） |

## 初回セットアップ

### backend

```bash
cd backend
uv sync --group dev
```

`.venv/` と `uv.lock` が生成されます。`uv.lock` は git 管理対象です（再現性を保つため）。

### kindle-pdf

```bash
cd kindle-pdf
uv sync                  # 通常の Kindle キャプチャ用
uv sync --group gpu      # OCR / GPU 利用時（CUDA版 PyTorch を取得・約 2.5GB）
```

GPU グループは CUDA 12.1 版 PyTorch を `https://download.pytorch.org/whl/cu121` から取得します。

## 起動方法

```bash
# バックエンド（依存解決と起動を同時に実行）
cd backend
uv run uvicorn main:app --reload --port 8766

# テスト
uv run pytest
```

仮想環境を `activate` する必要はありません。`uv run` が `.venv/` を自動検出します。

## よく使うコマンド

| コマンド | 用途 |
|---|---|
| `uv sync` | `pyproject.toml` から `.venv/` を再構築 |
| `uv sync --group <name>` | 特定の依存グループを含めて同期 |
| `uv add <pkg>` | パッケージを追加（`pyproject.toml` と `uv.lock` を更新） |
| `uv remove <pkg>` | パッケージを削除 |
| `uv lock --upgrade` | ロックファイルを再生成（バージョン更新） |
| `uv run <cmd>` | `.venv/` 内で任意コマンドを実行 |
| `uv tree` | 依存ツリーを表示 |

## 旧 venv からの移行（既に完了済み）

過去に `requirements.txt` ベースで `venv/` を作成していた場合：

1. `venv/` ディレクトリを削除
2. `uv sync` を実行
3. 起動コマンドを `python -m uvicorn ...` から `uv run uvicorn ...` に変更
