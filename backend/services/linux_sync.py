"""Linux サーバーへのファイル同期サービス。

Windows バックエンドで生成した画像・サムネイルを
SSH + Python tarfile を使って Linux サーバーへ転送する。
meta.db はサーバー側が正のため全体は送信しないが、
新規書籍の初期エントリ（genre=オリジナル）のみ SSH 経由で INSERT する。

設定 (環境変数):
  LINUX_SYNC_ENABLED  - "true" の場合のみ同期を実行（デフォルト: false）
  LINUX_SYNC_HOST     - Linux サーバーのホスト名（デフォルト: medaroserver）
  LINUX_SYNC_USER     - SSH ユーザー（デフォルト: amashio）
  LINUX_SYNC_DEST_DIR - Linux 側のデータルートパス（デフォルト: /opt/pic2pdf-viewer/data）
"""
import io
import json
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


def _init_meta_on_linux(book_names: list[str]) -> None:
    """Linux の meta.db に新規書籍の初期エントリ（genre=オリジナル）を INSERT する。

    既存エントリは変更しない（INSERT OR IGNORE）。
    Python スクリプトを SSH 経由で stdin に流し込むことでシェルクォート問題を回避する。
    """
    db_path = f"{_LINUX_DEST}/meta.db"
    books_json = json.dumps(book_names, ensure_ascii=False)
    py_script = (
        "import sqlite3, json\n"
        f"books = json.loads({books_json!r})\n"
        f"conn = sqlite3.connect({db_path!r})\n"
        "for b in books:\n"
        "    conn.execute(\n"
        "        'INSERT OR IGNORE INTO books_meta'\n"
        "        ' (source, book_id, authors, genre)'\n"
        "        \" VALUES ('doujin', ?, '[]', '\\u30aa\\u30ea\\u30b8\\u30ca\\u30eb')\",\n"
        "        (b,),\n"
        "    )\n"
        "conn.commit()\n"
        "conn.close()\n"
    )
    result = subprocess.run(
        ["ssh", f"{_LINUX_USER}@{_LINUX_HOST}", "python3"],
        input=py_script.encode("utf-8"),
        capture_output=True,
        timeout=_SSH_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    logger.info("linux_sync: meta init done for %d book(s)", len(book_names))


def sync_after_generate(
    book_names: list[str],
    images_dir: str,
    thumbnails_dir: str,
) -> None:
    """生成完了後に新規書籍の画像・サムネイルを Linux へ同期し、meta の初期エントリを書き込む。

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
        _init_meta_on_linux(book_names)
    except Exception as exc:
        logger.error("linux_sync: meta init failed: %s", exc)

    logger.info("linux_sync: sync complete")
