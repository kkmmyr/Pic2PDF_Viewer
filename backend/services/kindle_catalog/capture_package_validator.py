"""Windows agentが公開したready packageの安全検証。"""

import hashlib
import json
import re
from pathlib import Path

from PIL import Image

import config

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_CAPTURE_NAME = re.compile(r"^(?P<number>\d{3,})\.png$", re.IGNORECASE)
_TERMINATION_REASONS = {
    "visual_no_change_after_retries",
    "expected_screen_count_confirmed",
}


def safe_title(title: str) -> str:
    import re

    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip().rstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("書籍タイトルを安全な保存名へ変換できません")
    return cleaned[:180]


def _load_manifest(ready_dir: Path) -> dict:
    if not ready_dir.is_dir() or ready_dir.is_symlink():
        raise ValueError("完了済み capture package が見つかりません")
    manifest_path = ready_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("manifest.json がありません")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in (
        "manifest_version",
        "job_id",
        "asin",
        "source",
        "capture",
        "quality",
        "files",
    ):
        if key not in manifest:
            raise ValueError(f"manifest の必須項目がありません: {key}")
    if manifest["manifest_version"] != 2:
        raise ValueError("manifest version 2 が必要です")
    return manifest


def _validate_file_item(item: dict, image_dir: Path) -> tuple[Path, tuple[int, int], int]:
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
    expected_hash = item.get("sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("画像ファイルの SHA-256 が不正です")
    if hashlib.sha256(file_path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError("画像ファイルの SHA-256 が一致しません")
    try:
        with Image.open(file_path) as image:
            image.load()
            dimensions = image.size
    except Exception as exc:
        raise ValueError(f"画像ファイルを復号できません: {name}") from exc
    if item.get("width") != dimensions[0] or item.get("height") != dimensions[1] or item.get("size") != size:
        raise ValueError("manifest の画像寸法またはサイズが一致しません")
    return file_path, dimensions, size


def _validate_files(manifest: dict, ready_dir: Path) -> tuple[list[Path], tuple[int, int]]:
    declared = manifest["files"]
    if not isinstance(declared, list) or not 1 <= len(declared) <= config.ZIP_MAX_ENTRIES:
        raise ValueError("manifest のファイル件数が不正です")
    image_dir = ready_dir / "images"
    if not image_dir.is_dir() or image_dir.is_symlink():
        raise ValueError("images ディレクトリがありません")
    files: list[Path] = []
    actual_dimensions: set[tuple[int, int]] = set()
    total_size = 0
    declared_names: set[str] = set()
    for item in declared:
        file_path, dimensions, size = _validate_file_item(item, image_dir)
        total_size += size
        if total_size > config.ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError("capture package の合計サイズ上限を超えています")
        actual_dimensions.add(dimensions)
        declared_names.add(item["name"])
        files.append(file_path)
    actual_names = {
        path.name for path in image_dir.iterdir() if path.is_file() and path.suffix.casefold() in ALLOWED_EXTENSIONS
    }
    if actual_names != declared_names:
        raise ValueError("manifest と images のファイル一覧が一致しません")
    if len(actual_dimensions) != 1:
        raise ValueError("撮影画像の寸法が統一されていません")
    numbers = [
        int(match.group("number")) for item in declared if (match := _CAPTURE_NAME.fullmatch(item["name"])) is not None
    ]
    if len(numbers) != len(declared):
        raise ValueError("撮影画像のファイル名が連番PNGではありません")
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("撮影画像が001からの連番ではありません")
    return files, next(iter(actual_dimensions))


def _validate_completion(job: dict, capture: dict, count: int, last_name: str) -> None:
    if job.get("captured_screens") is not None and job["captured_screens"] != count:
        raise ValueError("キャプチャジョブと画像件数が一致しません")
    if capture.get("policy_version") != "kindle-completeness-v1":
        raise ValueError("撮影完了ポリシーが不正です")
    if capture.get("captured_screens") != count:
        raise ValueError("撮影証跡と画像件数が一致しません")
    if capture.get("termination_reason") not in _TERMINATION_REASONS:
        raise ValueError("撮影終了理由が不正です")
    if capture.get("end_of_book_proven") is not True:
        raise ValueError("最終ページ到達が証明されていません")
    if capture.get("last_saved_file") != last_name:
        raise ValueError("撮影証跡の最終画像が一致しません")
    retry_limit = capture.get("retry_limit")
    unchanged_windows = capture.get("unchanged_observation_windows")
    termination_windows = capture.get("termination_unchanged_windows")
    if (
        not isinstance(retry_limit, int)
        or retry_limit < 0
        or not isinstance(unchanged_windows, int)
        or unchanged_windows < retry_limit + 1
        or not isinstance(termination_windows, int)
        or termination_windows < retry_limit + 1
    ):
        raise ValueError("終端の無変化確認回数が不足しています")
    if capture.get("successful_transitions") != max(0, count - 1):
        raise ValueError("撮影証跡のページ遷移数が一致しません")


def _validate_geometry(capture: dict, dimensions: tuple[int, int]) -> list[int]:
    crop = capture.get("crop_bounds")
    image_size = capture.get("image_size")
    if (
        not isinstance(crop, list)
        or len(crop) != 4
        or not all(isinstance(value, int) for value in crop)
        or crop[0] >= crop[2]
        or crop[1] >= crop[3]
        or not isinstance(image_size, list)
        or len(image_size) != 2
        or tuple(image_size) != dimensions
        or crop[2] - crop[0] != image_size[0]
        or crop[3] - crop[1] != image_size[1]
    ):
        raise ValueError("撮影矩形または画像寸法の証跡が不正です")
    return crop


def _validate_quality(quality: dict, count: int, dimensions: tuple[int, int]) -> None:
    if (
        quality.get("schema_version") != 1
        or quality.get("policy_version") != "kindle-image-qa-v1"
        or quality.get("warning_policy_version") != "kindle-image-warning-v1"
        or quality.get("outcome") != "passed"
        or quality.get("page_count") != count
        or tuple(quality.get("dimensions") or ()) != dimensions
        or not isinstance(quality.get("findings"), list)
    ):
        raise ValueError("登録前画像QAの証跡が不正です")
    overlay = quality.get("overlay_detector")
    if (
        not isinstance(overlay, dict)
        or overlay.get("policy_version") != "kindle-repeated-overlay-v1"
        or overlay.get("passed") is not True
        or not isinstance(overlay.get("sampled_page_count"), int)
        or not 1 <= overlay["sampled_page_count"] <= count
        or not isinstance(overlay.get("candidate_count"), int)
        or overlay["candidate_count"] < 0
        or overlay.get("blocking_candidate_count") != 0
    ):
        raise ValueError("capture overlay detector evidence is invalid")


def _validate_canary(capture: dict, crop: list[int], dimensions: tuple[int, int]) -> None:
    canary = capture.get("canary")
    if (
        not isinstance(canary, dict)
        or canary.get("policy_version") != "kindle-capture-canary-v1"
        or canary.get("passed") is not True
        or tuple(canary.get("dimensions") or ()) != dimensions
        or canary.get("crop_bounds") != crop
        or not isinstance(canary.get("first_sha256"), str)
        or len(canary["first_sha256"]) != 64
        or not isinstance(canary.get("second_sha256"), str)
        or len(canary["second_sha256"]) != 64
        or canary["first_sha256"] == canary["second_sha256"]
        or not isinstance(canary.get("mean_difference"), (int, float))
        or not isinstance(canary.get("changed_ratio"), (int, float))
        or (canary["mean_difference"] <= 0 and canary["changed_ratio"] <= 0)
    ):
        raise ValueError("撮影前カナリアの証跡が不正です")


def validate_ready_dir(job: dict, ready_dir: Path) -> tuple[dict, list[Path]]:
    manifest = _load_manifest(ready_dir)
    if manifest["job_id"] != job["id"] or manifest["asin"] != job["asin"] or manifest["source"] != job["source"]:
        raise ValueError("manifest とキャプチャジョブが一致しません")
    files, dimensions = _validate_files(manifest, ready_dir)

    capture = manifest["capture"]
    quality = manifest["quality"]
    if not isinstance(capture, dict) or not isinstance(quality, dict):
        raise ValueError("撮影証跡または画像QAの形式が不正です")
    count = len(files)
    _validate_completion(job, capture, count, manifest["files"][-1]["name"])
    crop = _validate_geometry(capture, dimensions)
    _validate_quality(quality, count, dimensions)
    _validate_canary(capture, crop, dimensions)
    return manifest, files
