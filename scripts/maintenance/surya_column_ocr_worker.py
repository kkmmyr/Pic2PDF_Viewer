"""Run Surya OCR 2 on small groups of NDLOCR-detected vertical columns."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PIL import Image

_NOVEL_DB_PATH = (
    Path(__file__).resolve().parents[2] / "backend" / "services" / "novel_db"
)
if str(_NOVEL_DB_PATH) not in sys.path:
    sys.path.insert(0, str(_NOVEL_DB_PATH))

from surya_parsing import (  # noqa: E402
    CODE_FENCE_RE,
    SURYA_BLOCK_PROMPT,
    parse_surya_html,
)
from surya_runtime import SuryaClient, SuryaServer  # noqa: E402

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def group_segments(
    segments: list[dict[str, Any]], group_size: int
) -> list[list[dict[str, Any]]]:
    if group_size < 1:
        raise ValueError("group_size must be positive")
    vertical = [segment for segment in segments if segment.get("is_vertical")]
    return [
        vertical[index : index + group_size]
        for index in range(0, len(vertical), group_size)
    ]


def group_bbox(
    segments: list[dict[str, Any]], image_size: tuple[int, int], margin: int
) -> tuple[int, int, int, int]:
    points = [point for segment in segments for point in segment["bbox"]]
    width, height = image_size
    left = max(0, int(min(float(point[0]) for point in points)) - margin)
    top = max(0, int(min(float(point[1]) for point in points)) - margin)
    right = min(width, int(max(float(point[0]) for point in points)) + margin + 1)
    bottom = min(height, int(max(float(point[1]) for point in points)) + margin + 1)
    if right <= left or bottom <= top:
        raise ValueError("invalid grouped column bbox")
    return left, top, right, bottom


def extract_surya_text(raw_output: str) -> str:
    blocks = parse_surya_html(raw_output)
    if blocks:
        return "\n".join(block.text for block in blocks if block.text).strip()
    cleaned = CODE_FENCE_RE.sub("", raw_output.strip())
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    return cleaned.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--mmproj-path", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8769/v1")
    parser.add_argument("--model", default="surya-ocr-2")
    parser.add_argument("--group-size", type=int, default=4)
    parser.add_argument("--margin", type=int, default=12)
    parser.add_argument("--timeout-sec", type=float, default=600)
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    with SuryaServer(
        args.base_url,
        executable=args.server,
        model_path=args.model_path,
        mmproj_path=args.mmproj_path,
    ):
        client = SuryaClient(
            args.base_url,
            model=args.model,
            timeout_sec=args.timeout_sec,
            min_ink_coverage=0.0,
        )
        for task in manifest["tasks"]:
            image = Image.open(task["image_path"]).convert("RGB")
            output_segments = []
            for group_index, segment_group in enumerate(
                group_segments(task["segments"], args.group_size)
            ):
                bbox = group_bbox(segment_group, image.size, args.margin)
                crop = image.crop(bbox)
                expected_chars = sum(
                    len(str(segment.get("text", ""))) for segment in segment_group
                )
                raw_output = client._recognize(
                    crop,
                    prompt=SURYA_BLOCK_PROMPT,
                    max_tokens=min(4096, max(256, expected_chars * 4)),
                )
                text = extract_surya_text(raw_output)
                output_segments.append(
                    {
                        "group_index": group_index,
                        "bbox": list(bbox),
                        "text": text,
                        "source_segment_count": len(segment_group),
                        "source_text": "\n".join(
                            str(segment.get("text", "")) for segment in segment_group
                        ),
                    }
                )
            print(
                json.dumps(
                    {
                        "entry_id": int(task["entry_id"]),
                        "text": "\n".join(
                            segment["text"]
                            for segment in output_segments
                            if segment["text"]
                        ),
                        "segments": output_segments,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
