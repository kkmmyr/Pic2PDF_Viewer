#!/usr/bin/env python3
"""Recover an NDLOCR PARSeq Tiny state dict from its distributed ONNX model.

This is an isolated audit utility. It never replaces the source ONNX and only
writes a checkpoint after the recovered PyTorch model passes ONNX Runtime
equivalence checks on a deterministic input and caller-supplied line images.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


class RecoveryError(RuntimeError):
    """Raised when recovery cannot prove a complete, compatible state dict."""


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


def merge_attention_projection(
    query_weight: np.ndarray,
    key_value_weight: np.ndarray,
    query_bias: np.ndarray,
    key_value_bias: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Undo PyTorch MultiheadAttention's ONNX q / kv projection split."""
    if query_weight.ndim != 2 or key_value_weight.ndim != 2:
        raise RecoveryError("attention projection weights must be rank 2")
    if query_weight.shape[0] != key_value_weight.shape[0]:
        raise RecoveryError("attention q and kv input dimensions differ")
    if query_bias.ndim != 1 or key_value_bias.ndim != 1:
        raise RecoveryError("attention projection biases must be rank 1")
    if query_weight.shape[1] != query_bias.shape[0]:
        raise RecoveryError("attention q weight and bias dimensions differ")
    if key_value_weight.shape[1] != key_value_bias.shape[0]:
        raise RecoveryError("attention kv weight and bias dimensions differ")
    weight = np.concatenate([query_weight.T, key_value_weight.T], axis=0)
    bias = np.concatenate([query_bias, key_value_bias], axis=0)
    return np.ascontiguousarray(weight), np.ascontiguousarray(bias)


def validate_recovered_arrays(
    recovered: dict[str, np.ndarray], expected_shapes: dict[str, tuple[int, ...]]
) -> None:
    missing = sorted(set(expected_shapes) - set(recovered))
    extra = sorted(set(recovered) - set(expected_shapes))
    if missing or extra:
        raise RecoveryError(f"state dict keys differ: missing={missing}, extra={extra}")
    shape_errors = {
        key: {"actual": tuple(recovered[key].shape), "expected": shape}
        for key, shape in expected_shapes.items()
        if tuple(recovered[key].shape) != shape
    }
    if shape_errors:
        raise RecoveryError(f"state dict shapes differ: {shape_errors}")
    non_finite = [
        key for key, value in recovered.items() if not np.isfinite(value).all()
    ]
    if non_finite:
        raise RecoveryError(f"state dict contains non-finite values: {non_finite}")


def calculate_equivalence(
    name: str,
    onnx_logits: np.ndarray,
    torch_logits: np.ndarray,
    max_abs_threshold: float,
    mean_abs_threshold: float,
) -> EquivalenceMetrics:
    if onnx_logits.shape != torch_logits.shape:
        raise RecoveryError(
            f"{name}: output shapes differ: ONNX={onnx_logits.shape}, PyTorch={torch_logits.shape}"
        )
    difference = np.abs(
        onnx_logits.astype(np.float64) - torch_logits.astype(np.float64)
    )
    onnx_top1 = onnx_logits.argmax(axis=-1)
    torch_top1 = torch_logits.argmax(axis=-1)
    mismatch_count = int(np.count_nonzero(onnx_top1 != torch_top1))
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
        top1_token_count=int(onnx_top1.size),
        passed=passed,
    )


def _find_unique_node(model: Any, name: str, op_type: str | None = None) -> Any:
    matches = [
        node
        for node in model.graph.node
        if node.name == name and (op_type is None or node.op_type == op_type)
    ]
    if len(matches) != 1:
        raise RecoveryError(f"expected one ONNX node {name!r}, found {len(matches)}")
    return matches[0]


def _initializer_input(node: Any, initializers: dict[str, np.ndarray]) -> str:
    matches = [name for name in node.input if name in initializers]
    if len(matches) != 1:
        raise RecoveryError(
            f"node {node.name!r} must reference exactly one initializer, found {matches}"
        )
    return matches[0]


def _array_from_node_initializer(
    model: Any,
    initializers: dict[str, np.ndarray],
    node_name: str,
    op_type: str,
) -> np.ndarray:
    node = _find_unique_node(model, node_name, op_type)
    return initializers[_initializer_input(node, initializers)]


def _weight_for_named_bias(
    model: Any, initializers: dict[str, np.ndarray], bias_name: str
) -> np.ndarray:
    producers = {output: node for node in model.graph.node for output in node.output}
    add_nodes = [
        node
        for node in model.graph.node
        if node.op_type == "Add" and bias_name in node.input
    ]
    if len(add_nodes) != 1:
        raise RecoveryError(
            f"bias {bias_name!r} must have one Add consumer, found {len(add_nodes)}"
        )
    other_inputs = [name for name in add_nodes[0].input if name != bias_name]
    if len(other_inputs) != 1 or other_inputs[0] not in producers:
        raise RecoveryError(f"cannot trace MatMul producer for bias {bias_name!r}")
    matmul = producers[other_inputs[0]]
    if matmul.op_type != "MatMul":
        raise RecoveryError(
            f"bias {bias_name!r} producer is {matmul.op_type}, expected MatMul"
        )
    return np.ascontiguousarray(
        initializers[_initializer_input(matmul, initializers)].T
    )


def recover_arrays(
    onnx_model: Any, expected_shapes: dict[str, tuple[int, ...]]
) -> dict[str, np.ndarray]:
    from onnx import numpy_helper

    initializers = {
        item.name: np.array(numpy_helper.to_array(item), copy=True)
        for item in onnx_model.graph.initializer
    }
    recovered: dict[str, np.ndarray] = {}

    for key in expected_shapes:
        onnx_name = f"model.{key}"
        if onnx_name in initializers:
            recovered[key] = np.ascontiguousarray(initializers[onnx_name])

    for block_index in range(12):
        for stem in ("attn.qkv", "attn.proj", "mlp.fc1", "mlp.fc2"):
            key = f"encoder.blocks.{block_index}.{stem}.weight"
            bias_name = f"model.encoder.blocks.{block_index}.{stem}.bias"
            recovered[key] = _weight_for_named_bias(onnx_model, initializers, bias_name)

    for kind in ("self_attn", "cross_attn"):
        prefix = f"/decoder/layers.0/{kind}"
        query_weight = _array_from_node_initializer(
            onnx_model, initializers, f"{prefix}/MatMul", "MatMul"
        )
        key_value_weight = _array_from_node_initializer(
            onnx_model, initializers, f"{prefix}/MatMul_1", "MatMul"
        )
        query_bias = _array_from_node_initializer(
            onnx_model, initializers, f"{prefix}/Add", "Add"
        )
        key_value_bias = _array_from_node_initializer(
            onnx_model, initializers, f"{prefix}/Add_1", "Add"
        )
        weight, bias = merge_attention_projection(
            query_weight, key_value_weight, query_bias, key_value_bias
        )
        recovered[f"decoder.layers.0.{kind}.in_proj_weight"] = weight
        recovered[f"decoder.layers.0.{kind}.in_proj_bias"] = bias

    recovered["decoder.layers.0.linear1.weight"] = np.ascontiguousarray(
        _array_from_node_initializer(
            onnx_model, initializers, "/decoder/layers.0/linear1/MatMul", "MatMul"
        ).T
    )
    recovered["decoder.layers.0.linear2.weight"] = np.ascontiguousarray(
        _array_from_node_initializer(
            onnx_model, initializers, "/decoder/layers.0/linear2/MatMul", "MatMul"
        ).T
    )
    recovered["head.weight"] = np.ascontiguousarray(
        _array_from_node_initializer(
            onnx_model, initializers, "/head/MatMul", "MatMul"
        ).T
    )

    expand = _find_unique_node(onnx_model, "/Expand", "Expand")
    pos_name = _initializer_input(expand, initializers)
    recovered["pos_queries"] = np.ascontiguousarray(initializers[pos_name])

    validate_recovered_arrays(recovered, expected_shapes)
    return recovered


def _read_model_configuration(
    parseq_root: Path, charset_config: Path
) -> dict[str, Any]:
    import yaml

    with (parseq_root / "configs/model/parseq.yaml").open(encoding="utf-8") as stream:
        base = yaml.safe_load(stream)
    with (parseq_root / "configs/experiment/parseq-tiny.yaml").open(
        encoding="utf-8"
    ) as stream:
        experiment = yaml.safe_load(stream)["model"]
    with charset_config.open(encoding="utf-8") as stream:
        charset = yaml.safe_load(stream)["model"]
    return {**base, **experiment, **charset}


def _build_model(
    parseq_root: Path,
    config: dict[str, Any],
    input_shape: tuple[int, ...],
    classes: int,
) -> Any:
    sys.path.insert(0, str(parseq_root))
    from strhub.models.parseq.model import PARSeq

    if len(input_shape) != 4 or input_shape[:2] != (1, 3):
        raise RecoveryError(f"unsupported ONNX input shape: {input_shape}")
    if len(config["charset_train"]) + 1 != classes:
        raise RecoveryError(
            "charset size does not match ONNX classes: "
            f"charset={len(config['charset_train'])}, classes={classes}"
        )
    model = PARSeq(
        num_tokens=len(config["charset_train"]) + 3,
        max_label_length=100,
        img_size=input_shape[2:],
        patch_size=config["patch_size"],
        embed_dim=config["embed_dim"],
        enc_num_heads=config["enc_num_heads"],
        enc_mlp_ratio=config["enc_mlp_ratio"],
        enc_depth=config["enc_depth"],
        dec_num_heads=config["dec_num_heads"],
        dec_mlp_ratio=config["dec_mlp_ratio"],
        dec_depth=config["dec_depth"],
        decode_ar=config["decode_ar"],
        refine_iters=config["refine_iters"],
        dropout=config["dropout"],
    )
    return model


def _preprocess_image(path: Path, width: int, height: int) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        if rgb.height > rgb.width:
            rgb = rgb.transpose(Image.Transpose.ROTATE_90)
        resized = rgb.resize((width, height), Image.Resampling.BILINEAR)
        array = np.asarray(resized, dtype=np.float32)
    array = array / 127.5 - 1.0
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None, ...])


def _run_recovery(args: argparse.Namespace) -> dict[str, Any]:
    import onnx
    import onnxruntime as ort
    import torch

    for path in (args.onnx, args.parseq_root, args.charset_config, *args.sample_image):
        if not path.exists():
            raise RecoveryError(f"required path does not exist: {path}")
    if not args.sample_image:
        raise RecoveryError("at least one --sample-image is required")

    checkpoint_path = args.output_dir / "parseq-tiny-ndl-recovered.pt"
    if checkpoint_path.exists():
        raise RecoveryError(
            f"output directory contains an existing checkpoint; use a fresh directory: {checkpoint_path}"
        )

    onnx_model = onnx.load(str(args.onnx))
    onnx.checker.check_model(onnx_model)
    session_options = ort.SessionOptions()
    optimization_levels = {
        "disable": ort.GraphOptimizationLevel.ORT_DISABLE_ALL,
        "basic": ort.GraphOptimizationLevel.ORT_ENABLE_BASIC,
        "extended": ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED,
        "all": ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
    }
    session_options.graph_optimization_level = optimization_levels[args.ort_graph_optimization]
    session = ort.InferenceSession(
        str(args.onnx), session_options, providers=["CPUExecutionProvider"]
    )
    input_meta = session.get_inputs()
    output_meta = session.get_outputs()
    if len(input_meta) != 1 or len(output_meta) != 1:
        raise RecoveryError("expected exactly one ONNX input and output")
    input_shape = tuple(int(value) for value in input_meta[0].shape)
    output_shape = tuple(int(value) for value in output_meta[0].shape)
    if len(output_shape) != 3 or output_shape[0] != 1 or output_shape[1] != 101:
        raise RecoveryError(f"unsupported ONNX output shape: {output_shape}")

    config = _read_model_configuration(args.parseq_root, args.charset_config)
    model = _build_model(args.parseq_root, config, input_shape, output_shape[-1])
    expected_shapes = {
        key: tuple(value.shape) for key, value in model.state_dict().items()
    }
    recovered = recover_arrays(onnx_model, expected_shapes)
    state_dict = {
        key: torch.from_numpy(value.copy()) for key, value in recovered.items()
    }
    model.load_state_dict(state_dict, strict=True)
    model.eval()

    from strhub.data.utils import Tokenizer

    tokenizer = Tokenizer(config["charset_train"])
    rng = np.random.default_rng(args.seed)
    samples = [
        (
            "deterministic-random",
            rng.uniform(-1.0, 1.0, input_shape).astype(np.float32),
        )
    ]
    samples.extend(
        (str(path), _preprocess_image(path, input_shape[3], input_shape[2]))
        for path in args.sample_image
    )
    metrics: list[EquivalenceMetrics] = []
    for name, sample in samples:
        onnx_logits = session.run([output_meta[0].name], {input_meta[0].name: sample})[
            0
        ]
        with torch.inference_mode():
            torch_logits = model(tokenizer, torch.from_numpy(sample)).cpu().numpy()
        metrics.append(
            calculate_equivalence(
                name,
                onnx_logits,
                torch_logits,
                args.max_abs_error,
                args.mean_abs_error,
            )
        )

    source_files = {
        "onnx": args.onnx,
        "parseq_model": args.parseq_root / "strhub/models/parseq/model.py",
        "parseq_modules": args.parseq_root / "strhub/models/parseq/modules.py",
        "parseq_base_config": args.parseq_root / "configs/model/parseq.yaml",
        "parseq_tiny_config": args.parseq_root / "configs/experiment/parseq-tiny.yaml",
        "charset_config": args.charset_config,
    }
    source_hashes = {name: sha256_file(path) for name, path in source_files.items()}
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "passed" if all(item.passed for item in metrics) else "failed",
        "input_onnx": str(args.onnx.resolve()),
        "input_shape": input_shape,
        "output_shape": output_shape,
        "source_hashes": source_hashes,
        "model": {
            "charset_size": len(config["charset_train"]),
            "parameter_tensors": len(state_dict),
            "parameter_count": sum(value.numel() for value in state_dict.values()),
            "embed_dim": config["embed_dim"],
            "enc_num_heads": config["enc_num_heads"],
            "dec_num_heads": config["dec_num_heads"],
            "enc_depth": config["enc_depth"],
            "dec_depth": config["dec_depth"],
        },
        "thresholds": {
            "max_abs_error": args.max_abs_error,
            "mean_abs_error": args.mean_abs_error,
            "top1_mismatch_count": 0,
        },
        "onnxruntime_graph_optimization": args.ort_graph_optimization,
        "runtime_versions": {
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
            "torch": torch.__version__,
            "numpy": np.__version__,
        },
        "samples": [asdict(item) for item in metrics],
        "checkpoint_written": False,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "recovery-report.json"
    if report["status"] == "passed":
        payload = {
            "format_version": 1,
            "state_dict": state_dict,
            "model_config": {
                key: config[key]
                for key in (
                    "patch_size",
                    "embed_dim",
                    "enc_num_heads",
                    "enc_mlp_ratio",
                    "enc_depth",
                    "dec_num_heads",
                    "dec_mlp_ratio",
                    "dec_depth",
                    "decode_ar",
                    "refine_iters",
                    "dropout",
                )
            },
            "charset_train": config["charset_train"],
            "source_hashes": source_hashes,
        }
        temporary = checkpoint_path.with_suffix(".pt.tmp")
        torch.save(payload, temporary)
        os.replace(temporary, checkpoint_path)
        report["checkpoint_written"] = True
        report["checkpoint"] = str(checkpoint_path.resolve())
        report["checkpoint_sha256"] = sha256_file(checkpoint_path)

    temporary_report = report_path.with_suffix(".json.tmp")
    temporary_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary_report, report_path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--parseq-root", type=Path, required=True)
    parser.add_argument("--charset-config", type=Path, required=True)
    parser.add_argument("--sample-image", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--max-abs-error", type=float, default=2.5e-2)
    parser.add_argument("--mean-abs-error", type=float, default=1.25e-3)
    parser.add_argument(
        "--ort-graph-optimization",
        choices=("disable", "basic", "extended", "all"),
        default="disable",
        help="Disable by default so numeric comparison follows the exported graph without runtime fusion.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_abs_error < 0 or args.mean_abs_error < 0:
        raise RecoveryError("equivalence thresholds must be non-negative")
    report = _run_recovery(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
