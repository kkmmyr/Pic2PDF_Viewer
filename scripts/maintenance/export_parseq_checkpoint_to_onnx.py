#!/usr/bin/env python3
"""Export a trained PARSeq checkpoint to ONNX and verify numerical equivalence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


class ExportError(RuntimeError):
    """Raised when a PARSeq export cannot be verified safely."""


@dataclass(frozen=True)
class EquivalenceMetrics:
    name: str
    shape: tuple[int, ...]
    max_abs_error: float
    mean_abs_error: float
    top1_mismatch_count: int
    top1_token_count: int
    passed: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def calculate_equivalence(
    *,
    name: str,
    onnx_logits: np.ndarray,
    torch_logits: np.ndarray,
    max_abs_threshold: float,
    mean_abs_threshold: float,
) -> EquivalenceMetrics:
    if onnx_logits.shape != torch_logits.shape:
        raise ExportError(
            f"{name}: output shapes differ: "
            f"ONNX={onnx_logits.shape}, PyTorch={torch_logits.shape}"
        )
    difference = np.abs(
        onnx_logits.astype(np.float64) - torch_logits.astype(np.float64)
    )
    mismatch_count = int(
        np.count_nonzero(onnx_logits.argmax(axis=-1) != torch_logits.argmax(axis=-1))
    )
    max_abs_error = float(difference.max(initial=0.0))
    mean_abs_error = float(difference.mean()) if difference.size else 0.0
    passed = (
        mismatch_count == 0
        and max_abs_error <= max_abs_threshold
        and mean_abs_error <= mean_abs_threshold
    )
    return EquivalenceMetrics(
        name=name,
        shape=tuple(onnx_logits.shape),
        max_abs_error=max_abs_error,
        mean_abs_error=mean_abs_error,
        top1_mismatch_count=mismatch_count,
        top1_token_count=int(onnx_logits[..., 0].size),
        passed=passed,
    )


def preprocess_image(path: Path, width: int = 768, height: int = 24) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        if rgb.height > rgb.width:
            rgb = rgb.transpose(Image.Transpose.ROTATE_90)
        resized = rgb.resize((width, height), Image.Resampling.BILINEAR)
        array = np.asarray(resized, dtype=np.float32)
    array = array / 127.5 - 1.0
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None, ...])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parseq-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output-onnx", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--sample-image", type=Path, action="append", required=True)
    parser.add_argument("--max-abs-threshold", type=float, default=0.025)
    parser.add_argument("--mean-abs-threshold", type=float, default=0.00125)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    parseq_root = args.parseq_root.resolve()
    checkpoint = args.checkpoint.resolve()
    output_onnx = args.output_onnx.resolve()
    report_output = args.report_output.resolve()
    sample_images = [path.resolve() for path in args.sample_image]
    for required in (parseq_root, checkpoint, *sample_images):
        if not required.exists():
            raise ExportError(f"required path does not exist: {required}")
    if output_onnx.exists() or report_output.exists():
        raise ExportError("export outputs already exist")
    if args.max_abs_threshold <= 0 or args.mean_abs_threshold <= 0:
        raise ExportError("equivalence thresholds must be positive")
    system_path = parseq_root / "strhub" / "models" / "parseq" / "system.py"
    if not system_path.is_file():
        raise ExportError(f"PARSeq source tree is invalid: {parseq_root}")

    import onnx
    import onnxruntime as ort
    import torch

    sys.path.insert(0, os.fspath(parseq_root))
    from strhub.models.parseq.system import PARSeq

    torch.manual_seed(20260801)
    model = PARSeq.load_from_checkpoint(os.fspath(checkpoint), map_location="cpu")
    model.eval()
    model.decode_ar = True
    model.refine_iters = 1

    class FixedLengthExport(torch.nn.Module):
        def __init__(self, parseq: PARSeq) -> None:
            super().__init__()
            self.parseq = parseq

        def forward(self, images: torch.Tensor) -> torch.Tensor:
            return self.parseq(images, max_length=100)

    export_model = FixedLengthExport(model).eval()
    dummy = torch.randn(1, 3, 24, 768)
    output_onnx.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        export_model,
        dummy,
        os.fspath(output_onnx),
        input_names=["input"],
        output_names=["output"],
        opset_version=17,
        do_constant_folding=True,
        dynamo=False,
    )
    onnx_model = onnx.load(os.fspath(output_onnx))
    onnx.checker.check_model(onnx_model)
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    session = ort.InferenceSession(
        os.fspath(output_onnx), options, providers=["CPUExecutionProvider"]
    )
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name

    samples: list[tuple[str, np.ndarray]] = [("deterministic-random", dummy.numpy())]
    samples.extend((os.fspath(path), preprocess_image(path)) for path in sample_images)
    metrics: list[EquivalenceMetrics] = []
    with torch.inference_mode():
        for name, array in samples:
            torch_logits = export_model(torch.from_numpy(array)).cpu().numpy()
            onnx_logits = session.run([output_name], {input_name: array})[0]
            metrics.append(
                calculate_equivalence(
                    name=name,
                    onnx_logits=onnx_logits,
                    torch_logits=torch_logits,
                    max_abs_threshold=args.max_abs_threshold,
                    mean_abs_threshold=args.mean_abs_threshold,
                )
            )

    passed = all(item.passed for item in metrics)
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "checkpoint": {
            "path": os.fspath(checkpoint),
            "sha256": sha256_file(checkpoint),
        },
        "onnx": {
            "path": os.fspath(output_onnx),
            "sha256": sha256_file(output_onnx),
            "input_shape": [1, 3, 24, 768],
        },
        "thresholds": {
            "max_abs_error": args.max_abs_threshold,
            "mean_abs_error": args.mean_abs_threshold,
            "top1_mismatch_count": 0,
        },
        "samples": [asdict(item) for item in metrics],
        "runtime": {
            "python": sys.version,
            "torch": torch.__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
            "onnxruntime_graph_optimization": "disabled",
        },
        "safety": {
            "production_onnx_modified": False,
            "final_holdout_opened": False,
        },
    }
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExportError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
