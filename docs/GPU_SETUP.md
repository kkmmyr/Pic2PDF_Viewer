# OCR GPU環境セットアップガイド

Novel機能のOCR処理 (`yomitoku`) を高速化するために、NVIDIA GPU (CUDA) を利用可能な環境を構築する手順です。

## 前提条件
- NVIDIA GPU搭載マシンであること
- NVIDIAドライバがインストールされていること
- Python 3.10+ がインストールされていること

## セットアップ手順 (新規環境推奨)

既存のCPU版環境と混ざらないよう、新しい仮想環境を作成することを推奨します。

### 1. 仮想環境の作成
プロジェクトルート (`Pic2PDF_Viewer`) にて以下のコマンドを実行します。

```powershell
# 仮想環境 'venv-gpu' を作成
python -m venv venv-gpu

# 仮想環境のアクティベート
.\venv-gpu\Scripts\activate
```

### 2. GPU版パッケージのインストール
`kindle-pdf` ディレクトリにある `requirements-gpu.txt` を使用してインストールします。

```powershell
# CUDA 12.1 対応の PyTorch をインストール
# ファイルサイズが大きいため(約2.5GB)、タイムアウト時間を延ばして実行することを推奨します
pip install --default-timeout=1000 -r kindle-pdf/requirements-gpu.txt
```

**補足**: `requirements-gpu.txt` には `--index-url` が含まれており、自動的にGPU版のPyTorchがダウンロードされます。

### 3. インストール確認
以下のコマンドで `True` が返れば成功です。

```powershell
python -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}')"
```

## 実行方法

GPU環境でOCRを実行する場合は、必ず `venv-gpu` をアクティベートしてからスクリプトを実行してください。

```powershell
# アクティベート
.\venv-gpu\Scripts\activate

# バッチOCRの実行 (GPUが自動的に使用されます)
python kindle-pdf/batch_ocr.py
```

## トラブルシューティング

**Q. `False` が返る / "CUDA is not available" と出る**
- NVIDIAドライバを最新版に更新してください。
- インストールされた `torch` のバージョンを確認してください (`pip list`)。バージョン名に `+cu121` 等が含まれている必要があります。もし `+cpu` となっている場合は、一度アンインストールしてから再度手順2を実行してください。
