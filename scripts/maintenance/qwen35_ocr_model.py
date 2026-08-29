"""Fixed Qwen3.5 OCR snapshot fingerprint contract."""

from __future__ import annotations

import hashlib
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_fingerprint(model_path: Path) -> str:
    root = model_path.resolve()
    if not root.is_dir():
        raise ValueError(f"model path is not a directory: {root}")
    required = {
        "chat_template.jinja",
        "config.json",
        "generation_config.json",
        "model.safetensors.index.json",
        "preprocessor_config.json",
        "processor_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    }
    missing = sorted(name for name in required if not (root / name).is_file())
    if missing:
        raise ValueError(f"model snapshot is missing required files: {missing}")
    weights = sorted(root.glob("*.safetensors"))
    if not weights:
        raise ValueError("model snapshot has no safetensors weights")
    digest = hashlib.sha256()
    for path in sorted(root / name for name in required) + weights:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(_sha256(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()
