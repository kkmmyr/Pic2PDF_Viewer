"""Windows agentが公開したready packageの安全検証。"""

import hashlib
import json
from pathlib import Path

import config

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def safe_title(title: str) -> str:
    import re

    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip().rstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("書籍タイトルを安全な保存名へ変換できません")
    return cleaned[:180]


def validate_ready_dir(job: dict, ready_dir: Path) -> tuple[dict, list[Path]]:
    if not ready_dir.is_dir() or ready_dir.is_symlink():
        raise ValueError("完了済み capture package が見つかりません")
    manifest_path = ready_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("manifest.json がありません")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("job_id", "asin", "source", "files"):
        if key not in manifest:
            raise ValueError(f"manifest の必須項目がありません: {key}")
    if manifest["job_id"] != job["id"] or manifest["asin"] != job["asin"] or manifest["source"] != job["source"]:
        raise ValueError("manifest とキャプチャジョブが一致しません")
    declared = manifest["files"]
    if not isinstance(declared, list) or not 1 <= len(declared) <= config.ZIP_MAX_ENTRIES:
        raise ValueError("manifest のファイル件数が不正です")
    image_dir = ready_dir / "images"
    if not image_dir.is_dir() or image_dir.is_symlink():
        raise ValueError("images ディレクトリがありません")
    files: list[Path] = []
    total_size = 0
    declared_names: set[str] = set()
    for item in declared:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("manifest files の形式が不正です")
        name = item["name"]
        if Path(name).name != name or Path(name).suffix.casefold() not in ALLOWED_EXTENSIONS:
            raise ValueError("許可されていない画像ファイル名です")
        file_path = image_dir / name
        if not file_path.is_file() or file_path.is_symlink():
            raise ValueError("manifest に記載された画像がありません")
        size = file_path.stat().st_size
        if size > config.ZIP_MAX_PER_FILE_BYTES:
            raise ValueError("画像ファイルのサイズ上限を超えています")
        total_size += size
        if total_size > config.ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError("capture package の合計サイズ上限を超えています")
        expected_hash = item.get("sha256")
        if expected_hash:
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError("画像ファイルの SHA-256 が一致しません")
        declared_names.add(name)
        files.append(file_path)
    actual_names = {
        path.name for path in image_dir.iterdir() if path.is_file() and path.suffix.casefold() in ALLOWED_EXTENSIONS
    }
    if actual_names != declared_names:
        raise ValueError("manifest と images のファイル一覧が一致しません")
    return manifest, files
