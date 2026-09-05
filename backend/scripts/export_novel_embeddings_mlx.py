"""日本語小説検索の比較用 embedding を MLX で隔離生成する。

repo 外の MLX venv で実行する。SQLite は read-only URI で開き、現行の
LanceDB / API 設定には触れない。出力 NPZ は ID・ページ参照・ベクトルだけを
含み、本文や contextual_text は保存しない。モデル比較条件は profile ごとに
pooling、query instruction、padding を固定する。

使用例::

    /path/to/pic2pdf-mlx/.venv/bin/python \
      backend/scripts/export_novel_embeddings_mlx.py \
      --sqlite /tmp/search-eval/novel.db \
      --fixture backend/scripts/fixtures/novel_search_eval_v1.json \
      --profile bge_m3 \
      --model /path/to/models/bge-m3-fp16 \
      --revision a37eddded9a6a1273a87fb8b0da0d1cdbd98aeec \
      --snapshot-label 2026-08-22_020001 \
      --output /tmp/search-eval/bge-m3-vectors.npz \
      --manifest /tmp/search-eval/bge-m3-manifest.json
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

if __package__:
    from scripts.novel_embedding_eval_common import (
        DEFAULT_TASK,
        PROFILES,
        SCHEMA_VERSION,
        EmbeddingProfile,
        _percentile,
        _save_npz,
        _sha256_file,
        _write_json,
        load_chunks,
        load_queries,
        open_sqlite_read_only,
    )
    from scripts.novel_embedding_eval_common import (
        Chunk as Chunk,
    )
    from scripts.novel_embedding_eval_common import (
        EvalQuery as EvalQuery,
    )
    from scripts.novel_eval_runtime import process_max_rss_bytes as _max_rss_bytes
else:
    from novel_embedding_eval_common import (
        DEFAULT_TASK,
        PROFILES,
        SCHEMA_VERSION,
        EmbeddingProfile,
        _percentile,
        _save_npz,
        _sha256_file,
        _write_json,
        load_chunks,
        load_queries,
        open_sqlite_read_only,
    )
    from novel_embedding_eval_common import (
        Chunk as Chunk,
    )
    from novel_embedding_eval_common import (
        EvalQuery as EvalQuery,
    )
    from novel_eval_runtime import process_max_rss_bytes as _max_rss_bytes

DEFAULT_FIXTURE = Path(__file__).with_name("fixtures") / "novel_search_eval_v1.json"


def _pooling_mode(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    explicit = value.get("pooling_mode")
    if isinstance(explicit, str):
        return explicit
    legacy = {
        "pooling_mode_cls_token": "cls",
        "pooling_mode_mean_tokens": "mean",
        "pooling_mode_max_tokens": "max",
        "pooling_mode_lasttoken": "lasttoken",
    }
    active = [mode for key, mode in legacy.items() if value.get(key) is True]
    return active[0] if len(active) == 1 else None


def verify_model(path: Path, profile: EmbeddingProfile, revision: str) -> dict[str, Any]:
    if not path.is_dir():
        raise FileNotFoundError(f"embedding model directory not found: {path}")
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision.lower()):
        raise ValueError("--revision must be a 40-character immutable commit SHA")
    python_files = sorted(item.name for item in path.glob("*.py"))
    if python_files:
        raise RuntimeError(f"generic embedding checkpoint contains executable Python files: {python_files}")

    required = ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json")
    hashes: dict[str, str] = {}
    for name in required:
        file_path = path / name
        if not file_path.is_file():
            raise FileNotFoundError(f"required model file is missing: {file_path}")
        hashes[name] = _sha256_file(file_path)

    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    if config.get("model_type") != profile.expected_model_type:
        raise RuntimeError(f"unexpected model_type for {profile.name}: {config.get('model_type')!r}")
    pooling_path = path / "1_Pooling" / "config.json"
    pooling_config = json.loads(pooling_path.read_text(encoding="utf-8")) if pooling_path.is_file() else None
    effective_pooling = _pooling_mode(pooling_config) or (
        "mean" if profile.expected_model_type == "xlm-roberta" else "lasttoken"
    )
    if effective_pooling != profile.pooling:
        raise RuntimeError(
            f"unexpected pooling for {profile.name}: {effective_pooling!r}; expected {profile.pooling!r}"
        )
    if pooling_path.is_file():
        hashes["1_Pooling/config.json"] = _sha256_file(pooling_path)

    conversion_path = path / "conversion_manifest.json"
    conversion: dict[str, Any] | None = None
    if conversion_path.is_file():
        value = json.loads(conversion_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise RuntimeError("unsupported conversion manifest")
        source = value.get("source")
        output = value.get("output")
        if not isinstance(source, dict) or not isinstance(output, dict):
            raise RuntimeError("conversion manifest is missing source or output metadata")
        if source.get("model_id") != profile.model_id or source.get("revision") != revision:
            raise RuntimeError("conversion manifest source does not match the requested model revision")
        output_files = {
            "config_sha256": "config.json",
            "model_sha256": "model.safetensors",
            "tokenizer_sha256": "tokenizer.json",
            "tokenizer_config_sha256": "tokenizer_config.json",
        }
        for manifest_key, file_name in output_files.items():
            if output.get(manifest_key) != hashes[file_name]:
                raise RuntimeError(f"conversion manifest hash mismatch: {file_name}")
        hashes["conversion_manifest.json"] = _sha256_file(conversion_path)
        conversion = value

    cache_tree = path / ".cache" / "huggingface" / "trees" / f"{revision}.json"
    revision_evidence = cache_tree.is_file()
    return {
        "model_id": profile.model_id,
        "revision": revision,
        "revision_cache_evidence": revision_evidence,
        "path_name": path.name,
        "model_type": config["model_type"],
        "architecture": config.get("architectures", [None])[0],
        "quantization": config.get("quantization"),
        "pooling": profile.pooling,
        "normalization": "l2" if profile.normalize else "none",
        "padding_side": profile.padding_side,
        "query_template": profile.query_template,
        "document_prefix": profile.document_prefix,
        "task_instruction": DEFAULT_TASK if profile.query_template else None,
        "trust_remote_code": False,
        "conversion": conversion,
        "files": hashes,
    }


class MlxEmbedder:
    def __init__(
        self,
        model_path: Path,
        *,
        profile: EmbeddingProfile,
        max_length: int,
    ) -> None:
        import mlx.core as mx
        from mlx_vlm.embedding_loader import load_embedding_model
        from mlx_vlm.models.pooling import read_pooling_config
        from mlx_vlm.utils import load_processor

        self._mx = mx
        started = time.perf_counter()
        self._model = load_embedding_model(model_path)
        self._model.pooling_config = read_pooling_config(model_path)
        processor = load_processor(model_path, add_detokenizer=False)
        self._tokenizer = getattr(processor, "tokenizer", processor)
        self._tokenizer.padding_side = profile.padding_side
        self._normalize = profile.normalize
        self.load_seconds = time.perf_counter() - started
        self.max_length = max_length

    def embed(self, texts: Sequence[str]) -> tuple[Any, dict[str, Any]]:
        import numpy as np

        encoded = self._tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="np",
        )
        attention = encoded["attention_mask"]
        input_ids = encoded["input_ids"]
        raw_lengths = [len(self._tokenizer.encode(text, add_special_tokens=True)) for text in texts]
        started = time.perf_counter()
        output = self._model(
            self._mx.array(input_ids),
            attention_mask=self._mx.array(attention),
        )
        # NumPy cannot consume MLX bfloat16 through the PEP 3118 buffer
        # protocol. Cast on the MLX side so BF16 and quantized checkpoints
        # share the same validated FP32 export boundary.
        float_embeddings = output.text_embeds.astype(self._mx.float32)
        self._mx.eval(float_embeddings)
        elapsed = time.perf_counter() - started
        vectors = np.asarray(float_embeddings, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(texts):
            raise RuntimeError(f"unexpected embedding shape: {vectors.shape}")
        if not np.isfinite(vectors).all():
            raise RuntimeError("embedding contains non-finite values")
        norms = np.linalg.norm(vectors, axis=1)
        if np.any(norms <= np.finfo(np.float32).tiny):
            raise RuntimeError("embedding contains a zero vector")
        if self._normalize:
            vectors = vectors / norms[:, np.newaxis]
            norms = np.linalg.norm(vectors, axis=1)
        if not np.allclose(norms, 1.0, atol=2e-3):
            raise RuntimeError(f"embedding is not L2-normalized: min={norms.min()}, max={norms.max()}")
        return vectors, {
            "seconds": elapsed,
            "tokens": int(attention.sum()),
            "max_padded_tokens": int(input_ids.shape[1]),
            "truncated_inputs": sum(length > self.max_length for length in raw_lengths),
            "raw_tokens_max": max(raw_lengths),
        }

    def memory(self) -> dict[str, int | None]:
        active = getattr(self._mx, "get_active_memory", None)
        peak = getattr(self._mx, "get_peak_memory", None)
        return {
            "mlx_active_bytes": int(active()) if callable(active) else None,
            "mlx_peak_bytes": int(peak()) if callable(peak) else None,
            "process_max_rss_bytes": _max_rss_bytes(),
        }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--snapshot-label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=8192)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    import numpy as np

    args = _build_parser().parse_args(argv)
    if args.batch_size < 1 or args.batch_size > 64:
        raise ValueError("--batch-size must be between 1 and 64")
    if args.max_length < 128 or args.max_length > 32768:
        raise ValueError("--max-length must be between 128 and 32768")
    if args.output.suffix != ".npz":
        raise ValueError("--output must use the .npz suffix")
    if args.output.exists() or args.manifest.exists():
        raise FileExistsError("output or manifest already exists")

    started_at = datetime.now(UTC)
    profile = PROFILES[args.profile]
    model_manifest = verify_model(args.model, profile, args.revision.lower())
    fixture_sha256 = _sha256_file(args.fixture)
    queries = load_queries(args.fixture)
    sqlite_hash_before = _sha256_file(args.sqlite)
    conn = open_sqlite_read_only(args.sqlite)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
        chunks = load_chunks(conn, profile)
    finally:
        conn.close()

    embedder = MlxEmbedder(
        args.model,
        profile=profile,
        max_length=args.max_length,
    )
    embedder.embed([chunks[0].embedding_input, queries[0].query])

    batch_timings: list[float] = []
    total_tokens = 0
    max_padded_tokens = 0
    max_raw_tokens = 0
    truncated_inputs = 0
    vectors: list[Any] = []
    document_started = time.perf_counter()
    for start in range(0, len(chunks), args.batch_size):
        batch = chunks[start : start + args.batch_size]
        current_vectors, stats = embedder.embed([chunk.embedding_input for chunk in batch])
        vectors.append(current_vectors)
        batch_timings.append(float(stats["seconds"]))
        total_tokens += int(stats["tokens"])
        max_padded_tokens = max(max_padded_tokens, int(stats["max_padded_tokens"]))
        max_raw_tokens = max(max_raw_tokens, int(stats["raw_tokens_max"]))
        truncated_inputs += int(stats["truncated_inputs"])
        done = min(start + args.batch_size, len(chunks))
        if done % 256 == 0 or done == len(chunks):
            print(
                json.dumps(
                    {"event": "progress", "documents": done, "total": len(chunks)},
                    ensure_ascii=False,
                ),
                flush=True,
            )
    document_seconds = time.perf_counter() - document_started
    document_vectors = np.concatenate(vectors, axis=0)

    query_inputs = [profile.query_input(query.query) for query in queries]
    query_started = time.perf_counter()
    query_vectors, query_stats = embedder.embed(query_inputs)
    query_seconds = time.perf_counter() - query_started
    if document_vectors.shape[1] != query_vectors.shape[1]:
        raise RuntimeError("document and query embedding dimensions differ")

    sqlite_hash_after = _sha256_file(args.sqlite)
    if sqlite_hash_after != sqlite_hash_before:
        raise RuntimeError("source SQLite changed during embedding export")
    _save_npz(
        args.output,
        chunks=chunks,
        document_vectors=document_vectors,
        queries=queries,
        query_vectors=query_vectors,
    )
    artifact_sha256 = _sha256_file(args.output)
    memory = embedder.memory()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "started_at": started_at.isoformat(),
        "snapshot_label": args.snapshot_label,
        "profile": profile.name,
        "model": {
            **model_manifest,
            "max_length": args.max_length,
            "load_seconds": embedder.load_seconds,
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
        },
        "artifact": {
            "file_name": args.output.name,
            "sha256": artifact_sha256,
            "size_bytes": args.output.stat().st_size,
            "dimension": int(document_vectors.shape[1]),
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
            "document_seconds": document_seconds,
            "documents_per_second": len(chunks) / document_seconds,
            "query_seconds": query_seconds,
            "document_tokens": total_tokens,
            "document_tokens_per_second": total_tokens / document_seconds,
            "document_raw_tokens_max": max_raw_tokens,
            "document_padded_tokens_max": max_padded_tokens,
            "document_truncated_inputs": truncated_inputs,
            "query_tokens": int(query_stats["tokens"]),
            "query_raw_tokens_max": int(query_stats["raw_tokens_max"]),
            "query_truncated_inputs": int(query_stats["truncated_inputs"]),
            "batch_latency_seconds_p50": _percentile(batch_timings, 50),
            "batch_latency_seconds_p95": _percentile(batch_timings, 95),
            "batch_latency_seconds_mean": statistics.fmean(batch_timings),
            "memory": memory,
        },
        "safety": {
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
                "profile": profile.name,
                "documents": len(chunks),
                "dimension": int(document_vectors.shape[1]),
                "document_seconds": document_seconds,
                "documents_per_second": len(chunks) / document_seconds,
                "truncated_inputs": truncated_inputs,
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
