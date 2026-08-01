"""Recognize pre-detected vertical columns with PP-OCRv5 only."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--margin", type=int, default=8)
    parser.add_argument("--scale", type=float, default=2.0)
    args = parser.parse_args(argv)

    import cv2
    from paddleocr import TextRecognition

    recognizer = TextRecognition(
        model_name="PP-OCRv5_server_rec",
        device=args.device,
        enable_mkldnn=False,
    )
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    for task in manifest["tasks"]:
        started_at = time.perf_counter()
        image = cv2.imread(str(task["image_path"]), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"could not decode image: {task['image_path']}")
        image_height, image_width = image.shape[:2]
        crops = []
        retained_segments = []
        for segment in task["segments"]:
            bbox = segment.get("bbox", [])
            if not bbox:
                continue
            xs = [int(round(float(point[0]))) for point in bbox]
            ys = [int(round(float(point[1]))) for point in bbox]
            left = max(0, min(xs) - args.margin)
            right = min(image_width, max(xs) + args.margin + 1)
            top = max(0, min(ys) - args.margin)
            bottom = min(image_height, max(ys) + args.margin + 1)
            if right <= left or bottom <= top:
                continue
            crop = image[top:bottom, left:right]
            if bool(segment.get("is_vertical")):
                crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
            if args.scale != 1:
                crop = cv2.resize(
                    crop,
                    None,
                    fx=args.scale,
                    fy=args.scale,
                    interpolation=cv2.INTER_CUBIC,
                )
            crops.append(crop)
            retained_segments.append(segment)

        results = recognizer.predict(input=crops)
        if len(results) != len(retained_segments):
            raise RuntimeError(
                f"PP-OCRv5 recognized {len(results)} of {len(retained_segments)} "
                f"columns for entry {task['entry_id']}"
            )
        recognized_segments = []
        for source_segment, result in zip(retained_segments, results, strict=True):
            payload = result.json["res"]
            recognized_segments.append(
                {
                    **source_segment,
                    "detector_text": source_segment.get("text", ""),
                    "text": str(payload.get("rec_text", "")),
                    "confidence": float(payload.get("rec_score", 0.0)),
                }
            )
        print(
            json.dumps(
                {
                    "entry_id": int(task["entry_id"]),
                    "text": "\n".join(
                        segment["text"] for segment in recognized_segments
                    ),
                    "segments": recognized_segments,
                    "elapsed_seconds": time.perf_counter() - started_at,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
