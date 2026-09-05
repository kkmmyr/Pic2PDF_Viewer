"""OS 共通の小説 embedding 評価データとファイル操作。"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_TASK = "Given a web search query, retrieve relevant passages that answer the query"


@dataclass(frozen=True)
class EmbeddingProfile:
    name: str
    model_id: str
    expected_model_type: str
    pooling: str
    padding_side: str
    query_template: str | None
    document_prefix: str
    normalize: bool = True

    def query_input(self, query: str) -> str:
        if self.query_template is None:
            return query
        return self.query_template.format(task=DEFAULT_TASK, query=query)


PROFILES = {
    "bge_m3": EmbeddingProfile(
        name="bge_m3",
        model_id="mlx-community/bge-m3-mlx-fp16",
        expected_model_type="xlm-roberta",
        pooling="cls",
        padding_side="right",
        query_template=None,
        document_prefix="",
    ),
    "qwen3_embedding": EmbeddingProfile(
        name="qwen3_embedding",
        model_id="mlx-community/Qwen3-Embedding-0.6B-8bit",
        expected_model_type="qwen3",
        pooling="lasttoken",
        padding_side="left",
        query_template="Instruct: {task}\nQuery:{query}",
        document_prefix="",
    ),
    "harrier": EmbeddingProfile(
        name="harrier",
        model_id="microsoft/harrier-oss-v1-0.6b",
        expected_model_type="qwen3",
        pooling="lasttoken",
        padding_side="left",
        query_template="Instruct: {task}\nQuery: {query}",
        document_prefix="",
    ),
}


@dataclass(frozen=True)
class Chunk:
    chunk_id: int
    book_name: str
    page_no: int
    chunk_idx: int
    embedding_input: str


@dataclass(frozen=True)
class EvalQuery:
    case_id: str
    query: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile / 100.0) * len(ordered)))
    return ordered[rank - 1]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def open_sqlite_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"SQLite DB not found: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)


def load_chunks(conn: sqlite3.Connection, profile: EmbeddingProfile) -> list[Chunk]:
    rows = conn.execute(
        """
        SELECT c.id, b.name, p.page_no, c.chunk_idx, c.text, c.contextual_text
        FROM chunks c
        JOIN pages p ON p.id = c.page_id
        JOIN books b ON b.id = p.book_id
        WHERE p.index_eligible = 1
        ORDER BY b.id, p.page_no, c.chunk_idx, c.id
        """
    ).fetchall()
    chunks: list[Chunk] = []
    seen_ids: set[int] = set()
    for chunk_id, book_name, page_no, chunk_idx, text, contextual_text in rows:
        current_id = int(chunk_id)
        if current_id in seen_ids:
            raise RuntimeError(f"duplicate SQLite chunk id: {current_id}")
        seen_ids.add(current_id)
        raw_text = str(text)
        context = str(contextual_text).strip() if contextual_text is not None else ""
        embedding_input = f"{context}\n\n{raw_text}" if context else raw_text
        chunks.append(
            Chunk(
                chunk_id=current_id,
                book_name=str(book_name),
                page_no=int(page_no),
                chunk_idx=int(chunk_idx),
                embedding_input=f"{profile.document_prefix}{embedding_input}",
            )
        )
    if not chunks:
        raise RuntimeError("isolated SQLite contains no eligible chunks")
    return chunks


def load_queries(path: Path) -> list[EvalQuery]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported fixture")
    raw_cases = value.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("fixture cases are missing")
    queries: list[EvalQuery] = []
    seen_ids: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("fixture case is not an object")
        case_id = raw.get("id")
        query = raw.get("query")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"invalid or duplicate case id: {case_id!r}")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"case {case_id}: query is missing")
        seen_ids.add(case_id)
        queries.append(EvalQuery(case_id=case_id, query=query))
    return queries


def _save_npz(
    path: Path,
    *,
    chunks: Sequence[Chunk],
    document_vectors: Any,
    queries: Sequence[EvalQuery],
    query_vectors: Any,
) -> None:
    import numpy as np

    if path.exists():
        raise FileExistsError(f"embedding artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(
            handle,
            schema_version=np.asarray([SCHEMA_VERSION], dtype=np.int16),
            chunk_ids=np.asarray([chunk.chunk_id for chunk in chunks], dtype=np.int64),
            book_names=np.asarray([chunk.book_name for chunk in chunks], dtype=np.str_),
            page_nos=np.asarray([chunk.page_no for chunk in chunks], dtype=np.int32),
            chunk_indices=np.asarray([chunk.chunk_idx for chunk in chunks], dtype=np.int32),
            document_vectors=np.asarray(document_vectors, dtype=np.float32),
            query_ids=np.asarray([query.case_id for query in queries], dtype=np.str_),
            query_vectors=np.asarray(query_vectors, dtype=np.float32),
        )
    temporary.replace(path)
