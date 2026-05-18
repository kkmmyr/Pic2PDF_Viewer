"""Linux サーバーへのファイル同期サービス。

Windows バックエンドで生成した画像・サムネイル・meta.db を
SSH + Python tarfile を使って Linux サーバーへ転送する。

設定 (環境変数):
  LINUX_SYNC_ENABLED  - "true" の場合のみ同期を実行（デフォルト: false）
  LINUX_SYNC_HOST     - Linux サーバーのホスト名（デフォルト: medaroserver）
  LINUX_SYNC_USER     - SSH ユーザー（デフォルト: amashio）
  LINUX_SYNC_DEST_DIR - Linux 側のデータルートパス（デフォルト: /opt/pic2pdf-viewer/data）
"""
import io
import os
import subprocess
import tarfile
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

_SYNC_ENABLED = os.environ.get("LINUX_SYNC_ENABLED", "").lower() == "true"
_LINUX_HOST = os.environ.get("LINUX_SYNC_HOST", "medaroserver")
_LINUX_USER = os.environ.get("LINUX_SYNC_USER", "amashio")
_LINUX_DEST = os.environ.get("LINUX_SYNC_DEST_DIR", "/opt/pic2pdf-viewer/data")
_SSH_TIMEOUT = 180  # seconds per operation


def _tar_and_send(src_path: Path, dest_dir: str) -> None:
    """src_path（ディレクトリ）を tar.gz に圧縮して SSH で dest_dir に展開する。"""
    if not src_path.exists():
        logger.warning("linux_sync: source not found: %s", src_path)
        return

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(src_path, arcname=src_path.name)
    tar_bytes = buf.getvalue()

    ssh_cmd = f"mkdir -p '{dest_dir}' && tar xzf - -C '{dest_dir}'"
    result = subprocess.run(
        ["ssh", f"{_LINUX_USER}@{_LINUX_HOST}", ssh_cmd],
        input=tar_bytes,
        capture_output=True,
        timeout=_SSH_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    logger.info("linux_sync: sent %s → %s:%s", src_path.name, _LINUX_HOST, dest_dir)


def _send_file(src_file: Path, dest_dir: str) -> None:
    """単一ファイルを SSH 経由で転送する。"""
    if not src_file.exists():
        logger.warning("linux_sync: source file not found: %s", src_file)
        return

    data = src_file.read_bytes()
    dest_path = f"{dest_dir}/{src_file.name}"
    ssh_cmd = f"mkdir -p '{dest_dir}' && cat > '{dest_path}'"
    result = subprocess.run(
        ["ssh", f"{_LINUX_USER}@{_LINUX_HOST}", ssh_cmd],
        input=data,
        capture_output=True,
        timeout=_SSH_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    logger.info("linux_sync: sent %s → %s:%s", src_file.name, _LINUX_HOST, dest_path)


def sync_after_generate(
    book_names: list[str],
    images_dir: str,
    thumbnails_dir: str,
    meta_db_path: str,
) -> None:
    """生成完了後に新規書籍と meta.db を Linux へ同期する。

    LINUX_SYNC_ENABLED が true でない場合は即リターン。
    エラーが発生しても例外は握り潰してログに残す（生成ジョブには影響させない）。
    """
    if not _SYNC_ENABLED:
        return

    logger.info("linux_sync: starting sync for %d book(s)", len(book_names))

    images_root = Path(images_dir)
    thumbs_root = Path(thumbnails_dir)
    dest_images = f"{_LINUX_DEST}/doujin/images"
    dest_thumbs = f"{_LINUX_DEST}/doujin/thumbnails"

    for book_name in book_names:
        stem = Path(book_name).stem  # "book.pdf" → "book"
        try:
            _tar_and_send(images_root / stem, dest_images)
        except Exception as exc:
            logger.error("linux_sync: images sync failed [%s]: %s", book_name, exc)

        try:
            _send_file(thumbs_root / f"{stem}.jpg", dest_thumbs)
        except Exception as exc:
            logger.error("linux_sync: thumbnails sync failed [%s]: %s", book_name, exc)

    try:
        _send_file(Path(meta_db_path), _LINUX_DEST)
    except Exception as exc:
        logger.error("linux_sync: meta.db sync failed: %s", exc)

    logger.info("linux_sync: sync complete")
