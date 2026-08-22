"""撮影済み画像に対する登録前の決定的な品質監査。"""

from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageStat

from capture_overlay import audit_repeated_overlays

_CAPTURE_NAME = re.compile(r"^(?P<number>\d{3,})\.png$", re.IGNORECASE)
_MAX_WORKERS = 4
_NEAR_DUPLICATE_DHASH_DISTANCE = 3
_NOVEL_EDGE_DARK_RATIO = 0.08


class CaptureQualityError(RuntimeError):
    """登録を拒否すべき構造・画像品質エラー。"""


@dataclass(frozen=True)
class CaptureQualityResult:
    page_count: int
    dimensions: tuple[int, int]
    files: tuple[dict, ...]
    findings: tuple[dict, ...]
    overlay_detector: dict

    def to_manifest(self) -> dict:
        return {
            "schema_version": 1,
            "policy_version": "kindle-image-qa-v1",
            "warning_policy_version": "kindle-image-warning-v2",
            "outcome": "passed",
            "page_count": self.page_count,
            "dimensions": list(self.dimensions),
            "findings": list(self.findings),
            "overlay_detector": self.overlay_detector,
        }


def _inspect_image(path: Path) -> dict:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    with Image.open(path) as image:
        image.load()
        width, height = image.size
        mode = image.mode
        sample = image.convert("L")
        gray = sample.copy()
        sample.thumbnail((64, 64))
        stats = ImageStat.Stat(sample)
        mean_luma = float(stats.mean[0])
        stddev_luma = float(stats.stddev[0])
        dhash_image = gray.resize((9, 8))
        dhash_pixels = list(dhash_image.get_flattened_data())
        dhash = 0
        for row in range(8):
            for column in range(8):
                left = dhash_pixels[row * 9 + column]
                right = dhash_pixels[row * 9 + column + 1]
                dhash = (dhash << 1) | int(left > right)
        band_height = max(1, height // 50)

        def dark_ratio(box: tuple[int, int, int, int]) -> float:
            histogram = gray.crop(box).histogram()
            dark = sum(histogram[:220])
            total = sum(histogram)
            return dark / total if total else 0.0

        top_dark_ratio = dark_ratio((0, 0, width, band_height))
        bottom_dark_ratio = dark_ratio((0, height - band_height, width, height))
    if width <= 0 or height <= 0:
        raise CaptureQualityError(f"画像寸法が不正です: {path.name}")
    return {
        "name": path.name,
        "sha256": digest,
        "size": len(data),
        "width": width,
        "height": height,
        "mode": mode,
        "mean_luma": round(mean_luma, 3),
        "stddev_luma": round(stddev_luma, 3),
        "dhash": f"{dhash:016x}",
        "top_dark_ratio": round(top_dark_ratio, 6),
        "bottom_dark_ratio": round(bottom_dark_ratio, 6),
    }


def _numbered_images(image_dir: Path, expected_count: int) -> list[tuple[int, Path]]:
    numbered: list[tuple[int, Path]] = []
    unexpected: list[str] = []
    for path in image_dir.iterdir():
        match = _CAPTURE_NAME.fullmatch(path.name) if path.is_file() else None
        if path.is_symlink() or match is None:
            unexpected.append(path.name)
        else:
            numbered.append((int(match.group("number")), path))
    if unexpected:
        raise CaptureQualityError(
            "撮影画像以外の項目があります: " + ", ".join(sorted(unexpected))
        )
    numbered.sort(key=lambda item: item[0])
    if [number for number, _path in numbered] != list(range(1, len(numbered) + 1)):
        raise CaptureQualityError("撮影画像の連番が001から連続していません")
    if len(numbered) != expected_count:
        raise CaptureQualityError(
            f"撮影証跡と画像件数が一致しません: {len(numbered)}/{expected_count}"
        )
    if not numbered:
        raise CaptureQualityError("撮影画像がありません")
    return numbered


def _inspect_pages(
    numbered: list[tuple[int, Path]], max_workers: int
) -> tuple[list[dict], int]:
    workers = max(1, min(max_workers, _MAX_WORKERS, len(numbered), os.cpu_count() or 1))
    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            pages = list(executor.map(_inspect_image, [path for _n, path in numbered]))
    except CaptureQualityError:
        raise
    except Exception as exc:
        raise CaptureQualityError(f"撮影画像を復号できません: {exc}") from exc
    return pages, workers


def _validate_uniform_pages(pages: list[dict]) -> tuple[int, int]:
    dimensions = {(page["width"], page["height"]) for page in pages}
    if len(dimensions) != 1:
        raise CaptureQualityError("撮影画像の寸法が統一されていません")
    if len({page["mode"] for page in pages}) != 1:
        raise CaptureQualityError("撮影画像のカラーモードが統一されていません")
    return next(iter(dimensions))


def _content_findings(pages: list[dict], source: str | None) -> list[dict]:
    findings: list[dict] = []
    digest_names: dict[str, list[str]] = {}
    for page in pages:
        digest_names.setdefault(page["sha256"], []).append(page["name"])
        if page["stddev_luma"] < 3 and (
            page["mean_luma"] > 248 or page["mean_luma"] < 7
        ):
            findings.append(
                {
                    "code": "blank_or_sparse_candidate",
                    "severity": "warning",
                    "files": [page["name"]],
                    "metrics": {
                        "mean_luma": page["mean_luma"],
                        "stddev_luma": page["stddev_luma"],
                    },
                }
            )
    findings.extend(
        {
            "code": "exact_duplicate_candidate",
            "severity": "warning",
            "files": names,
        }
        for names in digest_names.values()
        if len(names) > 1
    )
    findings.extend(_near_duplicate_findings(pages))
    if source == "novel":
        findings.extend(_novel_edge_findings(pages))
    findings.extend(_low_size_findings(pages))
    return findings


def _near_duplicate_findings(pages: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for previous, current in zip(pages, pages[1:], strict=False):
        if previous["sha256"] == current["sha256"]:
            continue
        distance = (int(previous["dhash"], 16) ^ int(current["dhash"], 16)).bit_count()
        if distance <= _NEAR_DUPLICATE_DHASH_DISTANCE:
            findings.append(
                {
                    "code": "adjacent_near_duplicate_candidate",
                    "severity": "warning",
                    "files": [previous["name"], current["name"]],
                    "metrics": {"dhash_distance": distance},
                }
            )
    return findings


def _novel_edge_findings(pages: list[dict]) -> list[dict]:
    return [
        {
            "code": "novel_edge_content_candidate",
            "severity": "warning",
            "files": [page["name"]],
            "metrics": {
                "top_dark_ratio": page["top_dark_ratio"],
                "bottom_dark_ratio": page["bottom_dark_ratio"],
            },
        }
        for page in pages
        if page["top_dark_ratio"] >= _NOVEL_EDGE_DARK_RATIO
        or page["bottom_dark_ratio"] >= _NOVEL_EDGE_DARK_RATIO
    ]


def _low_size_findings(pages: list[dict]) -> list[dict]:
    sizes = sorted(page["size"] for page in pages)
    threshold = max(50_000, int(sizes[len(sizes) // 2] * 0.12))
    return [
        {
            "code": "low_size_candidate",
            "severity": "warning",
            "files": [page["name"]],
            "metrics": {"size": page["size"], "threshold": threshold},
        }
        for page in pages
        if page["size"] < threshold
    ]


def audit_capture_images(
    image_dir: Path,
    *,
    expected_count: int,
    source: str | None = None,
    max_workers: int = _MAX_WORKERS,
) -> CaptureQualityResult:
    """全画像を独立復号し、厳格違反は例外、曖昧な候補はfindingで返す。"""
    if not image_dir.is_dir() or image_dir.is_symlink():
        raise CaptureQualityError("撮影画像ディレクトリがありません")
    if source not in {None, "comic", "novel"}:
        raise CaptureQualityError(f"撮影sourceが不正です: {source}")

    numbered = _numbered_images(image_dir, expected_count)
    pages, workers = _inspect_pages(numbered, max_workers)
    dimensions = _validate_uniform_pages(pages)

    overlay_detector, overlay_findings = audit_repeated_overlays(
        numbered,
        pages,
        max_workers=workers,
    )
    if not overlay_detector["passed"]:
        first = overlay_findings[0]
        raise CaptureQualityError(
            "repeated_screen_overlay_detected: "
            f"files={','.join(first['files'][:8])}, "
            f"bounds={first['metrics']['normalized_bounds']}"
        )
    findings = [*overlay_findings, *_content_findings(pages, source)]

    public_files = tuple(
        {
            "name": page["name"],
            "sha256": page["sha256"],
            "width": page["width"],
            "height": page["height"],
            "size": page["size"],
        }
        for page in pages
    )
    return CaptureQualityResult(
        page_count=len(pages),
        dimensions=dimensions,
        files=public_files,
        findings=tuple(findings),
        overlay_detector=overlay_detector,
    )
