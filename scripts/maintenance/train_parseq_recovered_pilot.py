#!/usr/bin/env python3
"""Fine-tune a recovered NDLOCR PARSeq Tiny checkpoint in an audit sandbox.

The script evaluates the recovered checkpoint before training, trains only on
the caller-supplied pilot LMDB, and compares every epoch with the untouched
baseline validation result. It never reads the reserved final holdout and
never replaces the production ONNX model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class PilotError(RuntimeError):
    """Raised when the recovered-checkpoint pilot cannot run safely."""


@dataclass(frozen=True)
class ValidationMetrics:
    accuracy: float
    ned: float
    loss: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: Path) -> tuple[str, list[dict[str, Any]]]:
    if not root.is_dir():
        raise PilotError(f"LMDB root does not exist: {root}")
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        file_hash = sha256_file(path)
        size = path.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
        files.append({"path": relative, "size": size, "sha256": file_hash})
    if not files:
        raise PilotError(f"LMDB root contains no files: {root}")
    return digest.hexdigest(), files


def validate_recovered_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("format_version") != 1:
        raise PilotError("unsupported recovered checkpoint format")
    state_dict = payload.get("state_dict")
    charset = payload.get("charset_train")
    config = payload.get("model_config")
    if not isinstance(state_dict, dict) or not state_dict:
        raise PilotError("recovered checkpoint has no state_dict")
    if not isinstance(charset, str) or len(charset) != 7141:
        raise PilotError(
            "recovered checkpoint charset is not NDLmoji_ver2 (7141 chars)"
        )
    if not isinstance(config, dict):
        raise PilotError("recovered checkpoint has no model_config")
    expected = {
        "patch_size": [4, 8],
        "embed_dim": 192,
        "enc_num_heads": 3,
        "enc_mlp_ratio": 4,
        "enc_depth": 12,
        "dec_num_heads": 6,
        "dec_mlp_ratio": 4,
        "dec_depth": 1,
        "decode_ar": True,
        "refine_iters": 1,
        "dropout": 0.1,
    }
    differences = {
        key: {"actual": config.get(key), "expected": value}
        for key, value in expected.items()
        if config.get(key) != value
    }
    if differences:
        raise PilotError(
            f"recovered model config differs from PARSeq Tiny: {differences}"
        )
    return config


def parse_validation_metrics(raw: dict[str, Any]) -> ValidationMetrics:
    required = ("val_accuracy", "val_NED", "val_loss")
    missing = [key for key in required if key not in raw]
    if missing:
        raise PilotError(f"validation metrics are missing: {missing}")
    return ValidationMetrics(
        accuracy=float(raw["val_accuracy"]),
        ned=float(raw["val_NED"]),
        loss=float(raw["val_loss"]),
    )


def pilot_passed(
    baseline: ValidationMetrics, best: ValidationMetrics, epsilon: float = 1e-9
) -> bool:
    return (
        best.ned > baseline.ned + epsilon
        and best.accuracy + epsilon >= baseline.accuracy
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parseq-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--no-augment", action="store_true")
    parser.add_argument("--expected-train-count", type=int, default=537)
    parser.add_argument("--expected-validation-count", type=int, default=185)
    parser.add_argument("--early-stopping-patience", type=int, default=-1)
    parser.add_argument("--report-name", default="pilot-report.json")
    return parser.parse_args()


def git_revision(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", os.fspath(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> int:
    args = parse_args()
    if not 1 <= args.epochs <= 5:
        raise PilotError("epochs must be between 1 and 5")
    if args.batch_size <= 0 or args.learning_rate <= 0:
        raise PilotError("batch size and learning rate must be positive")
    if args.expected_train_count <= 0 or args.expected_validation_count <= 0:
        raise PilotError("expected split counts must be positive")
    if args.early_stopping_patience < -1:
        raise PilotError("early stopping patience must be -1 or greater")
    if Path(args.report_name).name != args.report_name:
        raise PilotError("report name must be a file name")

    parseq_root = args.parseq_root.resolve()
    checkpoint = args.checkpoint.resolve()
    data_root = args.data_root.resolve()
    output_dir = args.output_dir.resolve()
    report_path = output_dir / args.report_name
    if not (parseq_root / "strhub" / "models" / "parseq" / "system.py").is_file():
        raise PilotError(f"PARSeq source tree is invalid: {parseq_root}")
    if not checkpoint.is_file():
        raise PilotError(f"recovered checkpoint does not exist: {checkpoint}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise PilotError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, os.fspath(parseq_root))
    import torch
    from pytorch_lightning import Trainer, seed_everything
    from pytorch_lightning.callbacks import Callback, EarlyStopping, ModelCheckpoint

    from strhub.data.module import SceneTextDataModule
    from strhub.models.parseq.system import PARSeq

    random.seed(args.seed)
    seed_everything(args.seed, workers=True)
    torch.use_deterministic_algorithms(True, warn_only=True)

    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    config = validate_recovered_payload(payload)
    data_hash, data_files = sha256_tree(data_root)
    checkpoint_hash = sha256_file(checkpoint)

    def create_model() -> PARSeq:
        model = PARSeq(
            charset_train=payload["charset_train"],
            charset_test=payload["charset_train"],
            max_label_length=100,
            batch_size=args.batch_size,
            lr=args.learning_rate,
            warmup_pct=0.02,
            weight_decay=0.01,
            img_size=[24, 768],
            patch_size=config["patch_size"],
            embed_dim=config["embed_dim"],
            enc_num_heads=config["enc_num_heads"],
            enc_mlp_ratio=config["enc_mlp_ratio"],
            enc_depth=config["enc_depth"],
            dec_num_heads=config["dec_num_heads"],
            dec_mlp_ratio=config["dec_mlp_ratio"],
            dec_depth=config["dec_depth"],
            perm_num=6,
            perm_forward=True,
            perm_mirrored=True,
            decode_ar=config["decode_ar"],
            refine_iters=config["refine_iters"],
            dropout=config["dropout"],
        )
        model.model.load_state_dict(payload["state_dict"], strict=True)
        return model

    data_module = SceneTextDataModule(
        root_dir=os.fspath(data_root),
        train_dir="real",
        img_size=[24, 768],
        max_label_length=100,
        charset_train=payload["charset_train"],
        charset_test=payload["charset_train"],
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        augment=not args.no_augment,
        remove_whitespace=False,
        normalize_unicode=False,
    )
    train_count = len(data_module.train_dataset)
    validation_count = len(data_module.val_dataset)
    expected_counts = (args.expected_train_count, args.expected_validation_count)
    if (train_count, validation_count) != expected_counts:
        raise PilotError(
            "LMDB split differs from the approved split: "
            f"expected={expected_counts}, actual={(train_count, validation_count)}"
        )

    accelerator = "gpu" if torch.cuda.is_available() else "cpu"
    baseline_model = create_model()
    evaluator = Trainer(
        accelerator=accelerator,
        devices=1,
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        deterministic=True,
    )
    baseline_raw = evaluator.validate(
        baseline_model, datamodule=data_module, verbose=False
    )
    if len(baseline_raw) != 1:
        raise PilotError(f"unexpected baseline validation results: {baseline_raw}")
    baseline = parse_validation_metrics(baseline_raw[0])

    class ValidationHistory(Callback):
        def __init__(self) -> None:
            self.metrics: list[dict[str, float | int]] = []

        def on_validation_end(self, trainer: Trainer, _model: PARSeq) -> None:
            raw = trainer.callback_metrics
            if all(key in raw for key in ("val_accuracy", "val_NED", "val_loss")):
                self.metrics.append(
                    {
                        "epoch": trainer.current_epoch,
                        "accuracy": float(raw["val_accuracy"]),
                        "ned": float(raw["val_NED"]),
                        "loss": float(raw["val_loss"]),
                    }
                )

    checkpoint_callback = ModelCheckpoint(
        dirpath=output_dir / "checkpoints",
        filename="epoch-{epoch:02d}-ned-{val_NED:.6f}-acc-{val_accuracy:.6f}",
        monitor="val_NED",
        mode="max",
        save_top_k=1,
        save_weights_only=True,
        auto_insert_metric_name=False,
    )
    history_callback = ValidationHistory()
    callbacks: list[Callback] = [history_callback, checkpoint_callback]
    if args.early_stopping_patience >= 0:
        callbacks.append(
            EarlyStopping(
                monitor="val_NED",
                mode="max",
                patience=args.early_stopping_patience,
                strict=True,
            )
        )
    model = create_model()
    trainer = Trainer(
        accelerator=accelerator,
        devices=1,
        max_epochs=args.epochs,
        precision="32-true",
        gradient_clip_val=20,
        logger=False,
        callbacks=callbacks,
        enable_progress_bar=True,
        deterministic=True,
        log_every_n_steps=1,
        num_sanity_val_steps=0,
    )
    trainer.fit(model, datamodule=data_module)

    best_model_path = checkpoint_callback.best_model_path
    if not best_model_path:
        raise PilotError("training produced no validation checkpoint")
    best_model = PARSeq.load_from_checkpoint(best_model_path, map_location="cpu")
    best_raw = evaluator.validate(best_model, datamodule=data_module, verbose=False)
    if len(best_raw) != 1:
        raise PilotError(f"unexpected best validation results: {best_raw}")
    best = parse_validation_metrics(best_raw[0])
    passed = pilot_passed(baseline, best)

    report = {
        "status": "passed" if passed else "failed",
        "acceptance": {
            "ned_must_improve": True,
            "accuracy_must_not_regress": True,
            "passed": passed,
        },
        "baseline": asdict(baseline),
        "best": asdict(best),
        "delta": {
            "accuracy": best.accuracy - baseline.accuracy,
            "ned": best.ned - baseline.ned,
            "loss": best.loss - baseline.loss,
        },
        "data": {
            "train_count": train_count,
            "validation_count": validation_count,
            "tree_sha256": data_hash,
            "files": data_files,
        },
        "input_checkpoint": {
            "path": os.fspath(checkpoint),
            "sha256": checkpoint_hash,
            "source_hashes": payload.get("source_hashes"),
        },
        "training": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "num_workers": args.num_workers,
            "augment": not args.no_augment,
            "seed": args.seed,
            "early_stopping_patience": args.early_stopping_patience,
            "accelerator": accelerator,
            "device": torch.cuda.get_device_name(0)
            if torch.cuda.is_available()
            else "cpu",
            "best_checkpoint": os.fspath(Path(best_model_path).resolve()),
            "best_checkpoint_sha256": sha256_file(Path(best_model_path)),
            "epoch_metrics": history_callback.metrics,
        },
        "runtime": {
            "python": sys.version,
            "torch": torch.__version__,
            "pytorch_lightning": __import__("pytorch_lightning").__version__,
            "parseq_revision": git_revision(parseq_root),
        },
        "safety": {
            "production_onnx_modified": False,
            "final_holdout_opened": False,
        },
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PilotError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
