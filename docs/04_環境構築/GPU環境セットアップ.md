# OCR GPU環境セットアップガイド

最終更新: 2026-05-07

Novel機能のOCR処理 (`yomitoku`) を高速化するために、NVIDIA GPU (CUDA) を利用可能な環境を構築する手順。

> **重要**: OCR ツール群は `kindle-pdf/` 配下に独立した uv プロジェクト ([kindle-pdf/pyproject.toml](../../kindle-pdf/pyproject.toml)) として構成されている。本体バックエンド (`backend/`) とは別の `.venv` を持つ。これは PyTorch 等の重量級 ML 依存をバックエンド側に持ち込まないための意図的な分離（[ADR-0005: Python パッケージ管理を `uv` に移行](../02_基本設計/ADR/0005_uv-python-package-manager.md) 参照）。

## 前提条件

- NVIDIA GPU 搭載マシン
- NVIDIA ドライバがインストール済み
- Python **3.12+**（kindle-pdf の `pyproject.toml` で要件定義）
- uv インストール済み（[uv環境セットアップ.md](uv環境セットアップ.md) 参照）

## セットアップ手順

### 1. 依存マニフェストの確認

`kindle-pdf/pyproject.toml` で GPU 依存は `[dependency-groups.gpu]` に分離されている:

```toml
[dependency-groups]
gpu = [
    "yomitoku",
    "torch==2.5.1",
    "torchvision==0.20.1",
    "torchaudio==2.5.1",
]

[[tool.uv.index]]
name = "pytorch-cu121"
url = "https://download.pytorch.org/whl/cu121"
explicit = true

[tool.uv.sources]
torch = { index = "pytorch-cu121" }
torchvision = { index = "pytorch-cu121" }
torchaudio = { index = "pytorch-cu121" }
```

CUDA 12.1 ビルドの PyTorch を専用 index から取得する設定。

### 2. GPU 依存のインストール

```powershell
cd kindle-pdf
uv sync --group gpu
```

`uv sync --group gpu` で通常依存 + `gpu` グループ依存（yomitoku + PyTorch CUDA 版）が `kindle-pdf/.venv` にインストールされる。
ファイルサイズが大きい（PyTorch CUDA 版は 2GB 超）ため、初回は時間を要する。

### 3. インストール確認

以下のコマンドで `True` が返れば成功:

```powershell
cd kindle-pdf
uv run python -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}')"
```

## 実行方法

GPU 環境での OCR は管理画面（`/novel/manage`）の「OCR」タブから実行する。
`batch_ocr.py` / `start_batch_ocr.bat` は Phase 5 で削除済み。
OCR は `services/novel_db/extractor.py` → `D:\61.tool\common\ocr\` の独立 venv 経由で動作する。

## トラブルシューティング

### `False` が返る / "CUDA is not available" と出る

- NVIDIA ドライバを最新版に更新する
- インストールされた `torch` バージョンを確認:
  ```powershell
  cd kindle-pdf
  uv run python -c "import torch; print(torch.__version__)"
  ```
  バージョン名に `+cu121` が含まれている必要がある。`+cpu` の場合は `[tool.uv.sources]` 設定が読まれていない可能性があるため、`uv.lock` を一度削除して `uv sync --group gpu` を再実行する

### CUDA 12.x との互換性

`pyproject.toml` で固定している `cu121` は CUDA 12.1。マシン側の CUDA バージョン（`nvidia-smi` で確認）と PyTorch のビルドが一致している必要がある。CUDA 12.4 等を使いたい場合は `[[tool.uv.index]]` の URL を `cu124` 等に変更する。

## 関連ドキュメント

- [uv環境セットアップ.md](uv環境セットアップ.md) — uv 自体のインストール
- [OCR設計書.md](../03_詳細設計/OCR設計書.md) — yomitoku を用いた Searchable PDF 生成設計
- [ADR-0005: uv 採用](../02_基本設計/ADR/0005_uv-python-package-manager.md)
