# uv 環境セットアップ

> status: living | last-verified: 2026-07-27

本プロジェクトの Python 環境は [uv](https://docs.astral.sh/uv/) の
workspace として管理する。

## uv のインストール

### Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

または:

```powershell
winget install --id=astral-sh.uv -e
```

### Mac

```bash
brew install uv
```

確認:

```bash
uv --version
```

## workspace 構成

ルート `pyproject.toml` が次の 3 member を管理する。

| member | 用途 |
|---|---|
| `backend/` | FastAPI バックエンド |
| `kindle-pdf/` | Kindle キャプチャツール |
| `common/llm/` | 共有 LLM クライアント |

- ロックファイル: ルート `uv.lock`
- 仮想環境: ルート `.venv/`
- 初回同期: リポジトリルートで 1 回

`backend/.venv` や `kindle-pdf/.venv` を新規作成しない。
過去の端末に残っている member 直下の `.venv` は互換残骸であり、
標準環境として扱わない。

Linux productionだけはsystemdの既存`ExecStart=/opt/pic2pdf-viewer/backend/.venv/bin/uvicorn`
を保つ互換境界として、`backend`自体を`backend-<generation>`へのsymlinkにする。各backend世代が
自身の`.venv`を所有し、対応する`common/llm-<generation>`も固定する。deploy時はルート`uv.lock`と
workspace memberをstagingへ配置し、`UV_PROJECT_ENVIRONMENT=<新backend世代>/.venv` +
`uv sync --locked --package pic2pdf-viewer-backend --no-dev`でactive世代とは別に構築する。
import smoke後にbackend / common symlinkを切り替えてserviceをrestartし、失敗時はsourceとvenvを
一体で直前世代へ戻す。

`scripts/setup_service.bat` もルート `.venv\Scripts\python.exe` を参照する。
既存 Windows サービスが旧 `backend/.venv` を登録している場合は、
ルートで `uv sync` 後に setup script でサービスを再登録してから旧環境を削除する。

外部の `D:\61.tool\common\ocr\` は workspace member ではない。
これは yomitoku 独立照合を含む OCR 専用環境であり、
`OCR_PYTHON` / `OCR_PACKAGE_PATH` から参照する。

## 初回セットアップ

```bash
# リポジトリルート
uv sync
```

開発用依存も含める場合:

```bash
uv sync --group dev
```

`uv.lock` は再現性のため git 管理する。仮想環境を activate する必要はない。

## GPU 補助依存

`kindle-pdf` の `gpu` group は yomitoku + CUDA 12.1 版 PyTorch を含む。
主系の Surya OCR 2 は llama-server を使うため、この group を必要としない。

```bash
uv sync --package pic2pdf-viewer-kindle --group gpu
```

詳細は [OCR・Embedding GPU 環境セットアップ](GPU環境セットアップ.md) を参照。

## 起動・テスト

```bash
# バックエンド
cd backend
uv run uvicorn main:app --reload --port 8766

# バックエンドテスト
uv run pytest -q

# Kindle ツールのテスト（リポジトリルートから）
uv run --package pic2pdf-viewer-kindle pytest kindle-pdf/tests -q
```

member ディレクトリから `uv run` しても workspace のルート `.venv` と
`uv.lock` が自動検出される。

## よく使うコマンド

| コマンド | 用途 |
|---|---|
| `uv sync` | workspace 全体をルート `.venv` へ同期 |
| `uv sync --group <name>` | dependency group を含めて同期 |
| `uv add --package <member> <pkg>` | 指定 member へ直接依存を追加 |
| `uv remove --package <member> <pkg>` | 指定 member から直接依存を削除 |
| `uv lock --upgrade` | ルート lock を更新 |
| `uv run <cmd>` | workspace 環境でコマンドを実行 |
| `uv tree` | workspace の依存ツリーを表示 |

## 旧環境からの移行

`backend/.venv` / `kindle-pdf/.venv` や member ごとの lock を使う旧環境では、
リポジトリルートで `uv sync` し、ルート `.venv` を正とする。
member 直下の環境を削除する場合は、サービス・タスクスケジューラ・
ローカルスクリプトが古い Python パスを参照していないことを先に確認する。

設計判断は [ADR-0010](../基本設計/ADR/0010_uv-workspace-monorepo.md) を参照。
