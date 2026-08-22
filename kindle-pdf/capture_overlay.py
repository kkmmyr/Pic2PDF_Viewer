"""複数ページに繰り返し現れる画面オーバーレイを検出する。"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from capture_transient_overlay import audit_transient_bottom_right_overlays

_MAX_WORKERS = 4
_SAMPLE_LIMIT = 32
_NORMALIZED_WIDTH = 1024
_TILE_SIZE = 64
_TILE_STRIDE = 32
_EDGE_BAND_RATIO = 0.30
_MIN_TILE_STDDEV = 8.0
_MIN_EDGE_RATIO = 0.015
_WARNING_REPEAT_RATIO = 0.20
_BLOCKING_REPEAT_RATIO = 0.50
_MIN_DISTINCT_PAGES = 3
_BLOCKING_MIN_ADJACENT_TILES = 2


def _even_sample_indices(page_count: int) -> tuple[int, ...]:
    sample_count = min(page_count, _SAMPLE_LIMIT)
    if sample_count == page_count:
        return tuple(range(page_count))
    return tuple(
        sorted(
            {
                round(position * (page_count - 1) / (sample_count - 1))
                for position in range(sample_count)
            }
        )
    )


def _load_thumbnail(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with Image.open(path) as image:
        gray = image.convert("L")
        width, height = gray.size
        normalized_height = max(1, round(height * _NORMALIZED_WIDTH / width))
        normalized = np.asarray(
            gray.resize(
                (_NORMALIZED_WIDTH, normalized_height),
                Image.Resampling.LANCZOS,
            ),
            dtype=np.uint8,
        )
    return normalized, cv2.Canny(normalized, 50, 150) > 0


def _tile_is_in_edge_band(x: int, y: int, width: int, height: int) -> bool:
    return (
        x < width * _EDGE_BAND_RATIO
        or x + _TILE_SIZE > width * (1 - _EDGE_BAND_RATIO)
        or y < height * _EDGE_BAND_RATIO
        or y + _TILE_SIZE > height * (1 - _EDGE_BAND_RATIO)
    )


def _candidate_tiles(
    thumbnails: list[np.ndarray],
    edges: list[np.ndarray],
    page_names: list[str],
    page_hashes: list[str],
) -> list[dict]:
    height, width = thumbnails[0].shape
    warning_count = max(
        _MIN_DISTINCT_PAGES,
        math.ceil(len(thumbnails) * _WARNING_REPEAT_RATIO),
    )
    candidates: list[dict] = []
    for y in range(0, height - _TILE_SIZE + 1, _TILE_STRIDE):
        for x in range(0, width - _TILE_SIZE + 1, _TILE_STRIDE):
            if not _tile_is_in_edge_band(x, y, width, height):
                continue
            groups: dict[bytes, list[int]] = defaultdict(list)
            for index, (thumbnail, edge_map) in enumerate(
                zip(thumbnails, edges, strict=True)
            ):
                tile = thumbnail[y : y + _TILE_SIZE, x : x + _TILE_SIZE]
                edge_ratio = float(
                    edge_map[y : y + _TILE_SIZE, x : x + _TILE_SIZE].mean()
                )
                if (
                    float(tile.std()) >= _MIN_TILE_STDDEV
                    and edge_ratio >= _MIN_EDGE_RATIO
                ):
                    groups[hashlib.sha256(tile.tobytes()).digest()].append(index)
            if groups:
                _append_repeated_tile(
                    candidates,
                    max(groups.values(), key=len),
                    page_names,
                    page_hashes,
                    x,
                    y,
                    warning_count,
                )
    return candidates


def _append_repeated_tile(
    candidates: list[dict],
    matched_indices: list[int],
    page_names: list[str],
    page_hashes: list[str],
    x: int,
    y: int,
    warning_count: int,
) -> None:
    distinct_by_hash: dict[str, int] = {}
    for index in matched_indices:
        distinct_by_hash.setdefault(page_hashes[index], index)
    matched = sorted(distinct_by_hash.values())
    if len(matched) < warning_count:
        return
    candidates.append(
        {
            "tile_bounds": [x, y, x + _TILE_SIZE, y + _TILE_SIZE],
            "matched_indices": matched,
            "files": [page_names[index] for index in matched],
            "repeated_page_count": len(matched),
            "sampled_page_count": len(page_names),
            "repeat_ratio": round(len(matched) / len(page_names), 6),
        }
    )


def _tiles_are_adjacent(left: dict, right: dict) -> bool:
    lx1, ly1, _lx2, _ly2 = left["tile_bounds"]
    rx1, ry1, _rx2, _ry2 = right["tile_bounds"]
    return (
        (lx1 != rx1 or ly1 != ry1)
        and abs(lx1 - rx1) <= _TILE_STRIDE
        and abs(ly1 - ry1) <= _TILE_STRIDE
    )


def _cluster_candidates(candidates: list[dict]) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    common_pages: list[set[int]] = []
    ordered = sorted(
        candidates, key=lambda item: item["repeated_page_count"], reverse=True
    )
    for candidate in ordered:
        candidate_pages = set(candidate["matched_indices"])
        minimum_common = max(
            _MIN_DISTINCT_PAGES,
            math.ceil(candidate["sampled_page_count"] * _WARNING_REPEAT_RATIO),
        )
        for index, cluster in enumerate(clusters):
            shared_pages = common_pages[index] & candidate_pages
            if len(shared_pages) >= minimum_common and any(
                _tiles_are_adjacent(member, candidate) for member in cluster
            ):
                cluster.append(candidate)
                common_pages[index] = shared_pages
                break
        else:
            clusters.append([candidate])
            common_pages.append(candidate_pages)
    return [
        cluster
        for cluster, shared_pages in zip(clusters, common_pages, strict=True)
        if len(cluster) >= _BLOCKING_MIN_ADJACENT_TILES and shared_pages
    ]


def _cluster_finding(cluster: list[dict]) -> dict:
    bounds = [candidate["tile_bounds"] for candidate in cluster]
    matched_files = sorted(set.intersection(*(set(item["files"]) for item in cluster)))
    sampled_count = cluster[0]["sampled_page_count"]
    return {
        "code": "repeated_screen_overlay_candidate",
        "severity": "warning",
        "files": matched_files,
        "metrics": {
            "normalized_bounds": [
                min(bound[0] for bound in bounds),
                min(bound[1] for bound in bounds),
                max(bound[2] for bound in bounds),
                max(bound[3] for bound in bounds),
            ],
            "matched_tile_count": len(cluster),
            "repeated_page_count": len(matched_files),
            "sampled_page_count": sampled_count,
            "repeat_ratio": round(len(matched_files) / sampled_count, 6),
        },
    }


def audit_repeated_overlays(
    numbered: list[tuple[int, Path]],
    pages: list[dict],
    *,
    max_workers: int,
) -> tuple[dict, list[dict]]:
    sample_indices = _even_sample_indices(len(numbered))
    sampled_paths = [numbered[index][1] for index in sample_indices]
    workers = max(1, min(max_workers, _MAX_WORKERS, len(sampled_paths)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        inspected = list(executor.map(_load_thumbnail, sampled_paths))
    candidates = _candidate_tiles(
        [thumbnail for thumbnail, _edges in inspected],
        [edges for _thumbnail, edges in inspected],
        [pages[index]["name"] for index in sample_indices],
        [pages[index]["sha256"] for index in sample_indices],
    )
    clusters = _cluster_candidates(candidates)
    repeated_findings = [_cluster_finding(cluster) for cluster in clusters]
    blocking_count = max(
        _MIN_DISTINCT_PAGES,
        math.ceil(len(sample_indices) * _BLOCKING_REPEAT_RATIO),
    )
    blocking = [
        finding
        for finding in repeated_findings
        if finding["metrics"]["repeated_page_count"] >= blocking_count
    ]
    transient_findings = audit_transient_bottom_right_overlays(
        numbered,
        pages,
        load_thumbnail=_load_thumbnail,
    )
    return {
        "policy_version": "kindle-repeated-overlay-v2",
        "passed": not blocking,
        "sampled_page_count": len(sample_indices),
        "candidate_count": len(repeated_findings),
        "blocking_candidate_count": len(blocking),
        "transient_scanned_page_count": len(numbered),
        "transient_candidate_count": len(transient_findings),
    }, [*repeated_findings, *transient_findings]
