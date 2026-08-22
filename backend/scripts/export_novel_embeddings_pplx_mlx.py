"""PPLX context 0.6B の比較用 contextual embedding を隔離生成する。

非公式 MLX 変換に同梱された custom code を、固定 revision と全実行コードの
SHA-256を照合した後だけ読み込む。各書籍の連続チャンクを最大8K tokenの窓へ分け、
Perplexity公式方式と同じ双方向attention + late chunking + mean poolingで各チャンクの
ベクトルを得る。SQLite はread-onlyで、出力NPZには本文を含めない。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from export_novel_embeddings_mlx import (
    PROFILES,
    Chunk,
    EvalQuery,
    _max_rss_bytes,
    _percentile,
    _save_npz,
    _sha256_file,
    _write_json,
    load_chunks,
    load_queries,
    open_sqlite_read_only,
)

SCHEMA_VERSION = 1
MODEL_ID = "agentmish/pplx-embed-context-v1-0.6b-mlx"
MODEL_REVISION = "51c6d3cb34a9063c363ee5e94ac6ffc851088630"
SOURCE_MODEL_ID = "perplexity-ai/pplx-embed-context-v1-0.6b"
SOURCE_REVISION = "c2fe8bee1aee42534425a1dfa7f976f6c1a5d16b"
PROFILE_NAME = "pplx_context_0_6b"
DEFAULT_FIXTURE = _SCRIPT_DIR / "fixtures" / "novel_search_eval_v1.json"
EXPECTED_FILES = {
    "config.json": "06dcdc1712d379fdd33a734ed3968b565ec701b8031f70eecd57692ba47885eb",
    "conversion.json": "2bd152776c58ed1e6d7d64748fac17030762f29f1e41d6601d601ba12940007a",
    "model.safetensors": "3b1e94c5803b936725407fddb36ffc3767b06f8098aa7db81a8e7d20d53e8bf0",
    "model.safetensors.index.json": "0c3ae65ebb7e0906b04b16211a987e2fb5db0134291e5ad861d3c507060eb3e0",
    "tokenizer.json": "32687b48a8d7da95d23b32a8f24677795496605001bddee04016bb78ebcc2e67",
    "tokenizer_config.json": "e2b268f1cde7dfa133a40739ca4b87c6a0f41a498354c31ed24e81c63a2cf43c",
    "1_Pooling/config.json": "aa629215c1d83e73d9c51184e566f2c53456bc742f936984355a2990c8c8d046",
    "pplx_mlx_convert/__init__.py": "b4cbaf73389cbec452b9cd5d56b43d186861022bed7b754def80f1cc528dc58e",
    "pplx_mlx_convert/architecture.py": "92d9e203bfb68bce34050e406eb3d3f82e8701f14ab58570572d1ee2ea0b4e32",
    "pplx_mlx_convert/embeddings.py": "b5f0d3207c814b4cbc51c8cb289d22e13ccfb6f25f0da6178d5ab5ea08aeddc1",
    "pplx_mlx_convert/models.py": "6f0ce34711c6628027cb82bfcfa86c8b09d00c8f248ce2a442b3a9d19be7a2b0",
}
EXPECTED_PYTHON_FILES = {
    "pplx_mlx_convert/__init__.py",
    "pplx_mlx_convert/architecture.py",
    "pplx_mlx_convert/embeddings.py",
    "pplx_mlx_convert/models.py",
}


def verify_model(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        raise FileNotFoundError(f"PPLX model directory not found: {path}")
    python_files = {str(item.relative_to(path)) for item in path.rglob("*.py") if ".cache" not in item.parts}
    if python_files != EXPECTED_PYTHON_FILES:
        raise RuntimeError(
            f"PPLX checkpoint executable Python set differs from audited revision: {sorted(python_files)}"
        )
    hashes: dict[str, str] = {}
    for name, expected in EXPECTED_FILES.items():
        file_path = path / name
        if not file_path.is_file():
            raise FileNotFoundError(f"required PPLX model file is missing: {file_path}")
        actual = _sha256_file(file_path)
        if actual != expected:
            raise RuntimeError(f"PPLX model file SHA-256 mismatch: {name}: {actual}")
        hashes[name] = actual

    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    conversion = json.loads((path / "conversion.json").read_text(encoding="utf-8"))
    pooling = json.loads((path / "1_Pooling" / "config.json").read_text(encoding="utf-8"))
    if config.get("model_type") != "bidirectional_pplx_qwen3":
        raise RuntimeError("unexpected PPLX model_type")
    if config.get("use_bidirectional_attention") is not True or config.get("use_cache") is not False:
        raise RuntimeError("unexpected PPLX bidirectional attention configuration")
    if conversion.get("source_repo") != SOURCE_MODEL_ID or conversion.get("source_revision") != SOURCE_REVISION:
        raise RuntimeError("PPLX conversion source does not match audited official revision")
    if conversion.get("dtype") != "bfloat16":
        raise RuntimeError("unexpected PPLX conversion dtype")
    if pooling.get("pooling_mode_mean_tokens") is not True:
        raise RuntimeError("PPLX mean pooling configuration is missing")
    return {
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "source_model_id": SOURCE_MODEL_ID,
        "source_revision": SOURCE_REVISION,
        "path_name": path.name,
        "model_type": config["model_type"],
        "architecture": config.get("architectures", [None])[0],
        "dtype": conversion["dtype"],
        "quantization": None,
        "pooling": "mean over each late-chunk token span",
        "normalization": "l2 after float32 pooling",
        "attention": "bidirectional within each contiguous document window",
        "query_template": None,
        "document_prefix": "",
        "trust_remote_code": "audited local package only",
        "files": hashes,
    }


def build_context_windows(
    chunks: Sequence[Chunk],
    tokenizer: Any,
    *,
    max_length: int,
) -> tuple[list[list[Chunk]], list[int]]:
    if not chunks:
        raise ValueError("chunks must not be empty")
    sep_token = tokenizer.sep_token
    if not isinstance(sep_token, str) or not sep_token:
        raise ValueError("PPLX tokenizer has no separator token")
    sep_tokens = len(tokenizer.encode(sep_token, add_special_tokens=False))
    special_overhead = len(tokenizer.encode("", add_special_tokens=True))
    if sep_tokens < 1:
        raise ValueError("PPLX separator does not produce tokens")

    windows: list[list[Chunk]] = []
    token_counts: list[int] = []
    current: list[Chunk] = []
    current_tokens = special_overhead
    current_book: str | None = None
    for chunk in chunks:
        chunk_tokens = len(tokenizer.encode(chunk.embedding_input, add_special_tokens=False))
        if chunk_tokens + special_overhead > max_length:
            raise RuntimeError(f"chunk {chunk.chunk_id} exceeds contextual max_length without truncation")
        additional = chunk_tokens + (sep_tokens if current else 0)
        if current and (chunk.book_name != current_book or current_tokens + additional > max_length):
            windows.append(current)
            token_counts.append(current_tokens)
            current = []
            current_tokens = special_overhead
            additional = chunk_tokens
        current.append(chunk)
        current_tokens += additional
        current_book = chunk.book_name
    if current:
        windows.append(current)
        token_counts.append(current_tokens)

    if sum(len(window) for window in windows) != len(chunks):
        raise RuntimeError("PPLX context window split lost chunks")
    if any(count > max_length for count in token_counts):
        raise RuntimeError("PPLX context window exceeds max_length")
    if any(len({chunk.book_name for chunk in window}) != 1 for window in windows):
        raise RuntimeError("PPLX context window crosses a book boundary")
    return windows, token_counts


def _load_embedder(model_path: Path) -> Any:
    sys.path.insert(0, str(model_path))
    try:
        from pplx_mlx_convert import load_embedder

        return load_embedder(model_path)
    finally:
        sys.path.remove(str(model_path))


def _encode_queries(embedder: Any, queries: Sequence[EvalQuery]) -> tuple[np.ndarray, float]:
    started = time.perf_counter()
    outputs = embedder.encode(
        [[query.query] for query in queries],
        batch_size=len(queries),
        quantization="none",
        normalize_embeddings=True,
    )
    elapsed = time.perf_counter() - started
    if len(outputs) != len(queries) or any(output.shape[0] != 1 for output in outputs):
        raise RuntimeError("unexpected PPLX query embedding shape")
    return np.stack([output[0] for output in outputs]).astype(np.float32), elapsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--snapshot-label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--progress-windows", type=int, default=10)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    import mlx.core as mx

    args = _build_parser().parse_args(argv)
    if args.max_length < 512 or args.max_length > 32768:
        raise ValueError("--max-length must be between 512 and 32768")
    if args.progress_windows < 1:
        raise ValueError("--progress-windows must be positive")
    if args.output.suffix != ".npz":
        raise ValueError("--output must use the .npz suffix")
    if args.output.exists() or args.manifest.exists():
        raise FileExistsError("output or manifest already exists")

    started_at = datetime.now(UTC)
    model_manifest = verify_model(args.model)
    fixture_sha256 = _sha256_file(args.fixture)
    queries = load_queries(args.fixture)
    sqlite_hash_before = _sha256_file(args.sqlite)
    conn = open_sqlite_read_only(args.sqlite)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
        chunks = load_chunks(conn, PROFILES["bge_m3"])
    finally:
        conn.close()

    load_started = time.perf_counter()
    embedder = _load_embedder(args.model)
    load_seconds = time.perf_counter() - load_started
    smoke = embedder.smoke_validate()
    if not smoke.raw_float_finite or smoke.shapes != ((2, 1024), (1, 1024)):
        raise RuntimeError(f"PPLX smoke validation failed: {smoke}")
    windows, window_tokens = build_context_windows(
        chunks,
        embedder.tokenizer,
        max_length=args.max_length,
    )

    vector_batches: list[np.ndarray] = []
    window_latencies: list[float] = []
    done_chunks = 0
    document_started = time.perf_counter()
    for index, window in enumerate(windows, start=1):
        current_started = time.perf_counter()
        outputs = embedder.encode(
            [[chunk.embedding_input for chunk in window]],
            batch_size=1,
            quantization="none",
            normalize_embeddings=True,
        )
        latency = time.perf_counter() - current_started
        if len(outputs) != 1 or outputs[0].shape != (len(window), 1024):
            raise RuntimeError(
                f"unexpected PPLX document embedding shape at window {index}: {[output.shape for output in outputs]}"
            )
        current_vectors = outputs[0].astype(np.float32)
        if not np.isfinite(current_vectors).all():
            raise RuntimeError(f"PPLX embedding contains non-finite values at window {index}")
        norms = np.linalg.norm(current_vectors, axis=1)
        if not np.allclose(norms, 1.0, atol=2e-3):
            raise RuntimeError(f"PPLX embedding is not normalized at window {index}")
        vector_batches.append(current_vectors)
        window_latencies.append(latency)
        done_chunks += len(window)
        if index % args.progress_windows == 0 or index == len(windows):
            print(
                json.dumps(
                    {
                        "event": "progress",
                        "windows": index,
                        "total_windows": len(windows),
                        "documents": done_chunks,
                        "total_documents": len(chunks),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    document_seconds = time.perf_counter() - document_started
    document_vectors = np.concatenate(vector_batches, axis=0)
    if document_vectors.shape != (len(chunks), 1024):
        raise RuntimeError("PPLX document vectors are not aligned with source chunks")

    query_vectors, query_seconds = _encode_queries(embedder, queries)
    sqlite_hash_after = _sha256_file(args.sqlite)
    if sqlite_hash_after != sqlite_hash_before:
        raise RuntimeError("source SQLite changed during PPLX embedding export")
    _save_npz(
        args.output,
        chunks=chunks,
        document_vectors=document_vectors,
        queries=queries,
        query_vectors=query_vectors,
    )
    artifact_sha256 = _sha256_file(args.output)
    memory = {
        "mlx_active_bytes": int(mx.get_active_memory()),
        "mlx_peak_bytes": int(mx.get_peak_memory()),
        "process_max_rss_bytes": _max_rss_bytes(),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "started_at": started_at.isoformat(),
        "snapshot_label": args.snapshot_label,
        "profile": PROFILE_NAME,
        "model": {
            **model_manifest,
            "max_length": args.max_length,
            "load_seconds": load_seconds,
            "smoke": {
                "documents": smoke.documents,
                "chunk_counts": smoke.chunk_counts,
                "shapes": smoke.shapes,
                "dtypes": smoke.dtypes,
                "raw_float_finite": smoke.raw_float_finite,
            },
        },
        "fixture": {
            "file_name": args.fixture.name,
            "sha256": fixture_sha256,
            "query_count": len(queries),
        },
        "corpus": {
            "sqlite_file_name": args.sqlite.name,
            "sqlite_sha256": sqlite_hash_before,
            "integrity_check": "ok",
            "chunk_count": len(chunks),
            "book_count": len({chunk.book_name for chunk in chunks}),
            "page_count": len({(chunk.book_name, chunk.page_no) for chunk in chunks}),
            "embedding_input": "contextual_text + two newlines + chunk text, or chunk text",
            "window_policy": "contiguous chunks; never cross book; greedy max token length; no overlap",
        },
        "artifact": {
            "file_name": args.output.name,
            "sha256": artifact_sha256,
            "size_bytes": args.output.stat().st_size,
            "dimension": 1024,
            "dtype": str(document_vectors.dtype),
            "contains_source_text": False,
            "arrays": [
                "schema_version",
                "chunk_ids",
                "book_names",
                "page_nos",
                "chunk_indices",
                "document_vectors",
                "query_ids",
                "query_vectors",
            ],
        },
        "runtime": {
            "python": sys.version,
            "batch_size_windows": 1,
            "context_window_count": len(windows),
            "context_window_tokens_min": min(window_tokens),
            "context_window_tokens_max": max(window_tokens),
            "context_window_tokens_mean": statistics.fmean(window_tokens),
            "context_window_chunks_min": min(len(window) for window in windows),
            "context_window_chunks_max": max(len(window) for window in windows),
            "context_window_chunks_mean": statistics.fmean(len(window) for window in windows),
            "document_seconds": document_seconds,
            "documents_per_second": len(chunks) / document_seconds,
            "document_tokens": sum(window_tokens),
            "document_tokens_per_second": sum(window_tokens) / document_seconds,
            "document_truncated_inputs": 0,
            "query_seconds": query_seconds,
            "query_truncated_inputs": 0,
            "window_latency_seconds_p50": _percentile(window_latencies, 50),
            "window_latency_seconds_p95": _percentile(window_latencies, 95),
            "window_latency_seconds_mean": statistics.fmean(window_latencies),
            "memory": memory,
        },
        "safety": {
            "custom_code_audited": True,
            "custom_code_hashes_pinned": True,
            "sqlite_sha256_before": sqlite_hash_before,
            "sqlite_sha256_after": sqlite_hash_after,
            "source_text_in_artifact": False,
            "production_paths_modified": False,
        },
    }
    _write_json(args.manifest, manifest)
    print(
        json.dumps(
            {
                "event": "complete",
                "output": str(args.output),
                "manifest": str(args.manifest),
                "profile": PROFILE_NAME,
                "documents": len(chunks),
                "windows": len(windows),
                "dimension": 1024,
                "document_seconds": document_seconds,
                "documents_per_second": len(chunks) / document_seconds,
                "truncated_inputs": 0,
                "memory": memory,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
