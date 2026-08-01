"""Isolated PP-OCRv5 worker for the ground-truth benchmark."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def order_segments(
    texts: list[str], polygons: list[list[list[float]]], scores: list[float]
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for text, polygon, score in zip(texts, polygons, scores, strict=True):
        if not text.strip() or not polygon:
            continue
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        segments.append(
            {
                "text": text.strip(),
                "bbox": polygon,
                "confidence": float(score),
                "is_vertical": height > width * 1.5,
                "center_x": (min(xs) + max(xs)) / 2,
                "center_y": (min(ys) + max(ys)) / 2,
            }
        )
    vertical_count = sum(segment["is_vertical"] for segment in segments)
    predominantly_vertical = vertical_count >= max(1, len(segments) - vertical_count)
    if predominantly_vertical:
        segments.sort(key=lambda segment: (-segment["center_x"], segment["center_y"]))
    else:
        segments.sort(key=lambda segment: (segment["center_y"], segment["center_x"]))
    for segment in segments:
        segment.pop("center_x")
        segment.pop("center_y")
    return segments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--det-limit-side-len", type=int, default=960)
    args = parser.parse_args(argv)

    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv5_server_det",
        text_recognition_model_name="PP-OCRv5_server_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
        lang="japan",
        device=args.device,
        enable_mkldnn=False,
    )
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    for task in manifest["tasks"]:
        started_at = time.perf_counter()
        results = list(
            ocr.predict(
                input=str(task["image_path"]),
                text_det_limit_side_len=args.det_limit_side_len,
            )
        )
        if len(results) != 1:
            raise RuntimeError(
                f"PaddleOCR produced {len(results)} results for entry {task['entry_id']}"
            )
        payload = results[0].json["res"]
        texts = [str(text) for text in payload.get("rec_texts", [])]
        polygons = payload.get("rec_polys", [])
        scores = [float(score) for score in payload.get("rec_scores", [])]
        segments = order_segments(texts, polygons, scores)
        print(
            json.dumps(
                {
                    "entry_id": int(task["entry_id"]),
                    "text": "\n".join(segment["text"] for segment in segments),
                    "segments": segments,
                    "elapsed_seconds": time.perf_counter() - started_at,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
