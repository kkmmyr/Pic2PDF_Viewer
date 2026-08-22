"""Nemotron-3-Embed-1B 8bit MLX の比較ベクトルを隔離生成する。

非公式MLX変換の実行コード・重み・tokenizerを固定SHAで照合した後、公式契約の
``query: `` / ``passage: `` prefix、双方向attention、mean pooling、L2正規化を
用いる。2048次元を公式未対応の1024次元へ切り詰めず、別LanceDB表で評価する。
SQLiteはread-onlyで、出力NPZに本文を含めない。
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
MODEL_ID = "mlx-community/Nemotron-3-Embed-1B-BF16-8bit"
MODEL_REVISION = "78d1c33d503cafe42fa2b590396a115523445d7c"
SOURCE_MODEL_ID = "nvidia/Nemotron-3-Embed-1B-BF16"
SOURCE_REVISION = "a5e0f804b9e90a1ca6784ecbf6e41595774fc834"
PROFILE_NAME = "nemotron_3_embed_1b_8bit"
DEFAULT_FIXTURE = _SCRIPT_DIR / "fixtures" / "novel_search_eval_v1.json"
EXPECTED_FILES = {
    "config.json": "58397cda6bf16ba51a8d4eed1e193161a1b01de81a28db295a37cc0da961f50b",
    "config_sentence_transformers.json": "dc2bc223baa9e5eedd8593d1d4230210681001e7dec73ac53d89697df97079ee",
    "model.safetensors": "7922a6d8d4645ba168436348ad38a5b9550bdbaaf4dd31ba8013886b5bf76c31",
    "model.safetensors.index.json": "450f1ef356e7ee9bd1b6a4ed15a51e2913f1780f54753ca68e2316d93a61b884",
    "tokenizer.json": "797410dfb649a5b9ba92bc4fef7dbf4022d00e73de6867c4ac199a8846439421",
    "tokenizer_config.json": "7bbb77c55282bc679b86d21a1b3953ed8d5d63aaf75f10800c20596eab30b980",
    "modules.json": "21ddb3037a55ebf4549eb5c1dc44c3f28f10b56ec7f1335c92fd90e5b30d88ac",
    "1_Pooling/config.json": "6dcf44c2f7e7878ac0ee2e992c8e7d1f6812e12724b00d1d0cb0fa3336f07f0d",
    "nemotron3_embed_mlx.py": "a30a86d8967593736ab9a04999529646bb26d9ef8027b2e4070b77a4c5fcc80c",
    "benchmark_mteb.py": "5d91dbda8b797542e0b2784234367a42c2f29541a9d3ecbafaa20153001dd530",
    "compare_backends.py": "481a0d01d550a555544cb468f1c3b41692bf18e3938208f925651adece07b379",
    "README.md": "224c6bb2798b0a8aa8870e4c080f2e2920f28f6c64b006a0b6438c55e620bc86",
}
EXPECTED_PYTHON_FILES = {
    "nemotron3_embed_mlx.py",
    "benchmark_mteb.py",
    "compare_backends.py",
}


def verify_model(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        raise FileNotFoundError(f"Nemotron Embed model directory not found: {path}")
    python_files = {str(item.relative_to(path)) for item in path.rglob("*.py") if ".cache" not in item.parts}
    if python_files != EXPECTED_PYTHON_FILES:
        raise RuntimeError(f"Nemotron checkpoint Python set differs from audited revision: {sorted(python_files)}")
    hashes: dict[str, str] = {}
    for name, expected in EXPECTED_FILES.items():
        file_path = path / name
        if not file_path.is_file():
            raise FileNotFoundError(f"required Nemotron model file is missing: {file_path}")
        actual = _sha256_file(file_path)
        if actual != expected:
            raise RuntimeError(f"Nemotron model file SHA-256 mismatch: {name}: {actual}")
        hashes[name] = actual

    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    prompts = json.loads((path / "config_sentence_transformers.json").read_text(encoding="utf-8")).get("prompts")
    pooling = json.loads((path / "1_Pooling" / "config.json").read_text(encoding="utf-8"))
    if config.get("model_type") != "ministral3" or config.get("is_causal") is not False:
        raise RuntimeError("unexpected Nemotron embedding architecture")
    if config.get("hidden_size") != 2048 or config.get("pooling") != "avg":
        raise RuntimeError("unexpected Nemotron embedding dimension or pooling")
    if config.get("quantization") != {"group_size": 64, "bits": 8, "mode": "affine"}:
        raise RuntimeError("unexpected Nemotron embedding quantization")
    if prompts != {"query": "query: ", "document": "passage: "}:
        raise RuntimeError("unexpected Nemotron query/document prompts")
    if pooling.get("pooling_mode_mean_tokens") is not True:
        raise RuntimeError("Nemotron mean pooling configuration is missing")
    readme = (path / "README.md").read_text(encoding="utf-8")
    if SOURCE_REVISION not in readme or "Prefixes matter" not in readme:
        raise RuntimeError("Nemotron conversion source or prefix evidence is missing")
    return {
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "source_model_id": SOURCE_MODEL_ID,
        "source_revision_claimed_by_conversion": SOURCE_REVISION,
        "path_name": path.name,
        "model_type": config["model_type"],
        "architecture": config.get("architectures", [None])[0],
        "dtype": config.get("dtype"),
        "quantization": config["quantization"],
        "dimension": 2048,
        "pooling": "mean",
        "normalization": "l2",
        "attention": "bidirectional key-padding mask",
        "query_prefix": "query: ",
        "document_prefix": "passage: ",
        "trust_remote_code": "audited local module only",
        "files": hashes,
    }


def build_length_sorted_batches(
    chunks: Sequence[Chunk],
    tokenizer: Any,
    *,
    batch_size: int,
    max_length: int,
) -> tuple[list[list[int]], list[int]]:
    if not chunks:
        raise ValueError("chunks must not be empty")
    lengths = [len(tokenizer.encode(f"passage: {chunk.embedding_input}", add_special_tokens=True)) for chunk in chunks]
    oversized = [chunks[index].chunk_id for index, length in enumerate(lengths) if length > max_length]
    if oversized:
        raise RuntimeError(f"Nemotron inputs exceed max_length without truncation: {oversized[:10]}")
    ordered = sorted(range(len(chunks)), key=lambda index: (lengths[index], chunks[index].chunk_id))
    batches = [ordered[start : start + batch_size] for start in range(0, len(ordered), batch_size)]
    if sorted(index for batch in batches for index in batch) != list(range(len(chunks))):
        raise RuntimeError("Nemotron length buckets lost or duplicated chunks")
    return batches, lengths


def _load_runtime(model_path: Path) -> tuple[Any, Any, Any]:
    sys.path.insert(0, str(model_path))
    try:
        from nemotron3_embed_mlx import encode, load

        model, tokenizer = load(str(model_path))
        return model, tokenizer, encode
    finally:
        sys.path.remove(str(model_path))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--snapshot-label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--progress-documents", type=int, default=256)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    import mlx.core as mx

    args = _build_parser().parse_args(argv)
    if args.batch_size < 1 or args.batch_size > 32:
        raise ValueError("--batch-size must be between 1 and 32")
    if args.max_length < 512 or args.max_length > 32768:
        raise ValueError("--max-length must be between 512 and 32768")
    if args.progress_documents < 1:
        raise ValueError("--progress-documents must be positive")
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
    model, tokenizer, encode = _load_runtime(args.model)
    load_seconds = time.perf_counter() - load_started
    batches, token_lengths = build_length_sorted_batches(
        chunks,
        tokenizer,
        batch_size=args.batch_size,
        max_length=args.max_length,
    )
    warmup = encode(
        model,
        tokenizer,
        [chunks[batches[0][0]].embedding_input],
        input_type="passage",
        batch_size=1,
        max_length=args.max_length,
    )
    if warmup.shape != (1, 2048) or not np.isfinite(warmup).all():
        raise RuntimeError(f"Nemotron smoke validation failed: {warmup.shape}")

    document_vectors = np.empty((len(chunks), 2048), dtype=np.float32)
    batch_latencies: list[float] = []
    done = 0
    next_progress = args.progress_documents
    document_started = time.perf_counter()
    for batch in batches:
        texts = [chunks[index].embedding_input for index in batch]
        current_started = time.perf_counter()
        vectors = encode(
            model,
            tokenizer,
            texts,
            input_type="passage",
            batch_size=len(texts),
            max_length=args.max_length,
        ).astype(np.float32)
        batch_latencies.append(time.perf_counter() - current_started)
        if vectors.shape != (len(batch), 2048) or not np.isfinite(vectors).all():
            raise RuntimeError(f"unexpected Nemotron output shape: {vectors.shape}")
        norms = np.linalg.norm(vectors, axis=1)
        if not np.allclose(norms, 1.0, atol=2e-3):
            raise RuntimeError("Nemotron output is not L2-normalized")
        document_vectors[batch] = vectors
        done += len(batch)
        if done >= next_progress or done == len(chunks):
            print(
                json.dumps(
                    {"event": "progress", "documents": done, "total": len(chunks)},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            while next_progress <= done:
                next_progress += args.progress_documents
    document_seconds = time.perf_counter() - document_started

    query_started = time.perf_counter()
    query_vectors = encode(
        model,
        tokenizer,
        [query.query for query in queries],
        input_type="query",
        batch_size=args.batch_size,
        max_length=args.max_length,
    ).astype(np.float32)
    query_seconds = time.perf_counter() - query_started
    if query_vectors.shape != (len(queries), 2048):
        raise RuntimeError(f"unexpected Nemotron query shape: {query_vectors.shape}")

    sqlite_hash_after = _sha256_file(args.sqlite)
    if sqlite_hash_after != sqlite_hash_before:
        raise RuntimeError("source SQLite changed during Nemotron embedding export")
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
            "smoke_shape": list(warmup.shape),
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
            "embedding_input": "passage: + contextual_text + two newlines + chunk text, or chunk text",
            "batch_policy": "stable token-length sort; restore original chunk order in artifact",
        },
        "artifact": {
            "file_name": args.output.name,
            "sha256": artifact_sha256,
            "size_bytes": args.output.stat().st_size,
            "dimension": 2048,
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
            "batch_size": args.batch_size,
            "batch_count": len(batches),
            "document_seconds": document_seconds,
            "documents_per_second": len(chunks) / document_seconds,
            "document_tokens": sum(token_lengths),
            "document_tokens_per_second": sum(token_lengths) / document_seconds,
            "document_raw_tokens_min": min(token_lengths),
            "document_raw_tokens_max": max(token_lengths),
            "document_raw_tokens_mean": statistics.fmean(token_lengths),
            "document_truncated_inputs": 0,
            "query_seconds": query_seconds,
            "query_truncated_inputs": 0,
            "batch_latency_seconds_p50": _percentile(batch_latencies, 50),
            "batch_latency_seconds_p95": _percentile(batch_latencies, 95),
            "batch_latency_seconds_mean": statistics.fmean(batch_latencies),
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
                "dimension": 2048,
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
