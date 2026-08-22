"""連続する撮影画面の右下に短時間表示される通知候補を検出する。"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from pathlib import Path

import numpy as np

_TILE_SIZE = 64
_TILE_STRIDE = 32
_MIN_TILE_STDDEV = 8.0
_MIN_EDGE_RATIO = 0.015
_WINDOW_SIZE = 3
_MAX_TILE_MAD = 6.0
_CORNER_MARGIN = _TILE_STRIDE
_MIN_ADJACENT_TILES = 2

ThumbnailLoader = Callable[[Path], tuple[np.ndarray, np.ndarray]]


def _bottom_right_tile_positions(width: int, height: int) -> list[tuple[int, int]]:
    return [
        (x, y)
        for y in range(0, height - _TILE_SIZE + 1, _TILE_STRIDE)
        for x in range(0, width - _TILE_SIZE + 1, _TILE_STRIDE)
        if x + _TILE_SIZE >= width - _CORNER_MARGIN
        and y + _TILE_SIZE >= height - _CORNER_MARGIN
    ]


def _tile_positions_are_adjacent(
    left: tuple[int, int],
    right: tuple[int, int],
) -> bool:
    lx1, ly1 = left
    rx1, ry1 = right
    return (
        (lx1 != rx1 or ly1 != ry1)
        and abs(lx1 - rx1) <= _TILE_STRIDE
        and abs(ly1 - ry1) <= _TILE_STRIDE
    )


def _connected_tile_positions(
    positions: list[tuple[int, int]],
) -> list[list[tuple[int, int]]]:
    remaining = set(positions)
    clusters: list[list[tuple[int, int]]] = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        cluster = {seed}
        pending = [seed]
        while pending:
            current = pending.pop()
            adjacent = {
                candidate
                for candidate in remaining
                if _tile_positions_are_adjacent(current, candidate)
            }
            remaining.difference_update(adjacent)
            cluster.update(adjacent)
            pending.extend(sorted(adjacent, reverse=True))
        clusters.append(sorted(cluster))
    return clusters


def _transient_tile_mad(
    thumbnails: list[np.ndarray],
    edges: list[np.ndarray],
    x: int,
    y: int,
) -> float | None:
    tiles = [
        thumbnail[y : y + _TILE_SIZE, x : x + _TILE_SIZE] for thumbnail in thumbnails
    ]
    if min(float(tile.std()) for tile in tiles) < _MIN_TILE_STDDEV:
        return None
    if (
        min(
            float(edge_map[y : y + _TILE_SIZE, x : x + _TILE_SIZE].mean())
            for edge_map in edges
        )
        < _MIN_EDGE_RATIO
    ):
        return None
    signed = [tile.astype(np.int16) for tile in tiles]
    comparisons = (
        (left, right)
        for left in range(len(signed))
        for right in range(left + 1, len(signed))
    )
    maximum_mad = max(
        float(np.abs(signed[left] - signed[right]).mean())
        for left, right in comparisons
    )
    return maximum_mad if maximum_mad <= _MAX_TILE_MAD else None


def _transient_window_finding(
    window: list[tuple[np.ndarray, np.ndarray, str, str]],
) -> dict | None:
    if len(window) != _WINDOW_SIZE:
        return None
    page_hashes = [item[3] for item in window]
    if len(set(page_hashes)) != _WINDOW_SIZE:
        return None
    thumbnails = [item[0] for item in window]
    if len({thumbnail.shape for thumbnail in thumbnails}) != 1:
        return None
    edges = [item[1] for item in window]
    height, width = thumbnails[0].shape
    scores = {
        position: score
        for position in _bottom_right_tile_positions(width, height)
        if (
            score := _transient_tile_mad(
                thumbnails,
                edges,
                position[0],
                position[1],
            )
        )
        is not None
    }
    clusters = [
        cluster
        for cluster in _connected_tile_positions(list(scores))
        if len(cluster) >= _MIN_ADJACENT_TILES
    ]
    if not clusters:
        return None
    cluster = min(
        clusters,
        key=lambda item: (-len(item), item),
    )
    return {
        "code": "transient_bottom_right_overlay_candidate",
        "severity": "warning",
        "files": [item[2] for item in window],
        "metrics": {
            "normalized_bounds": [
                min(x for x, _y in cluster),
                min(y for _x, y in cluster),
                max(x for x, _y in cluster) + _TILE_SIZE,
                max(y for _x, y in cluster) + _TILE_SIZE,
            ],
            "matched_tile_count": len(cluster),
            "consecutive_page_count": _WINDOW_SIZE,
            "max_tile_mad": round(max(scores[position] for position in cluster), 6),
        },
    }


def _merge_transient_findings(findings: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for finding in findings:
        if (
            merged
            and merged[-1]["metrics"]["normalized_bounds"]
            == finding["metrics"]["normalized_bounds"]
            and merged[-1]["files"][-2:] == finding["files"][:2]
        ):
            merged[-1]["files"].append(finding["files"][-1])
            merged[-1]["metrics"]["consecutive_page_count"] = len(merged[-1]["files"])
            merged[-1]["metrics"]["matched_tile_count"] = max(
                merged[-1]["metrics"]["matched_tile_count"],
                finding["metrics"]["matched_tile_count"],
            )
            merged[-1]["metrics"]["max_tile_mad"] = max(
                merged[-1]["metrics"]["max_tile_mad"],
                finding["metrics"]["max_tile_mad"],
            )
            continue
        merged.append(
            {
                **finding,
                "files": list(finding["files"]),
                "metrics": dict(finding["metrics"]),
            }
        )
    return merged


def audit_transient_bottom_right_overlays(
    numbered: list[tuple[int, Path]],
    pages: list[dict],
    *,
    load_thumbnail: ThumbnailLoader,
) -> list[dict]:
    """連続3画面の右下に近似した矩形があればwarning候補を返す。"""
    window: deque[tuple[np.ndarray, np.ndarray, str, str]] = deque(maxlen=_WINDOW_SIZE)
    findings: list[dict] = []
    for (_number, path), page in zip(numbered, pages, strict=True):
        thumbnail, edges = load_thumbnail(path)
        window.append((thumbnail, edges, page["name"], page["sha256"]))
        finding = _transient_window_finding(list(window))
        if finding is not None:
            findings.append(finding)
    return _merge_transient_findings(findings)
