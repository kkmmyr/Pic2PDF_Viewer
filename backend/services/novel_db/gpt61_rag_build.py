"""Checkpointed, version-pinned RAG publication for reviewed GPT-6.1 bodies.

The operator must serialize this utility with all other SQLite/Lance writers.
Embedding preparation does not mutate either production store.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import struct
from pathlib import Path
from typing import Any

from . import embedder
from .chunker import MAX_CHARS, MIN_CHARS_FOR_CHUNK, OVERLAP, chunk_page
from .gpt61_body_publication import ENGINE, MODEL, _verify_published, current_digest, digest_json, validate_package
from .lance_store import get_chunks_table, get_summaries_table

SCHEMA = "gpt61-rag-build-v1"
BATCH_SIZE = 16
DIMENSION = 1024


def _settings() -> dict[str, Any]:
    return {
        "embedding_model": embedder.NOVEL_DB_EMBED_MODEL,
        "embedding_backend": embedder.NOVEL_DB_EMBED_BACKEND,
        "dimension": DIMENSION,
        "max_chars": MAX_CHARS,
        "overlap": OVERLAP,
        "minimum_page_chars": MIN_CHARS_FOR_CHUNK,
        "batch_size": BATCH_SIZE,
        "contextual_embedding": False,
    }


def _source(conn: sqlite3.Connection, package: dict[str, Any]) -> dict[str, Any]:
    validate_package(package)
    rows = conn.execute(
        "SELECT r.id, r.runtime_manifest_json,r.state,r.qa_state,r.model FROM ocr_runs r JOIN ocr_publications p ON p.run_id=r.id "
        "JOIN books b ON b.id=p.book_id WHERE b.name=? AND p.retired_at IS NULL AND r.engine=?",
        (package["book_name"], ENGINE),
    ).fetchall()
    if len(rows) != 1 or json.loads(rows[0][1]).get("package_sha256") != package["package_sha256"]:
        raise ValueError("published artifact version conflict")
    if tuple(rows[0][2:]) != ("completed", "approved", MODEL):
        raise ValueError("publication is not an approved completed GPT-6.1 run")
    verified = _verify_published(conn, package, rows[0][0], check_fts=False)
    if not verified["body_published"]:
        raise ValueError("body is not published")
    return verified


def _chunks(conn: sqlite3.Connection, package: dict[str, Any]) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT p.id,p.page_no,p.full_text,p.char_count FROM pages p JOIN books b ON b.id=p.book_id "
        "WHERE b.name=? AND p.index_eligible=1 ORDER BY p.page_no",
        (package["book_name"],),
    ).fetchall()
    return [
        {"page_id": p[0], "page_no": p[1], "chunk_idx": i, "text": text, "char_count": p[3]}
        for p in rows
        if p[3] >= MIN_CHARS_FOR_CHUNK
        for i, text in enumerate(chunk_page(p[2] or ""))
    ]


def _vector(vector: Any) -> list[float]:
    if not isinstance(vector, list) or len(vector) != DIMENSION:
        raise ValueError("invalid vector dimension")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
        raise ValueError("non-finite vector")
    # Lance persists float32; seal precisely that representation before publication.
    result = list(struct.unpack(f"<{DIMENSION}f", struct.pack(f"<{DIMENSION}f", *vector)))
    if not all(math.isfinite(v) for v in result) or sum(v * v for v in result) <= 0:
        raise ValueError("invalid vector norm")
    return result


def _write(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def prepare_build(
    conn: sqlite3.Connection,
    package: dict[str, Any],
    cache_dir: Path,
    *,
    execution_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = _source(conn, package)
    chunks = _chunks(conn, package)
    if not chunks:
        raise ValueError("published body has no eligible chunks")
    header = {
        "schema": SCHEMA,
        "book_name": package["book_name"],
        "package_sha256": package["package_sha256"],
        "body_sha256": source["current_sha256"],
        "run_id": source["run_id"],
        "settings": _settings(),
        "chunks_sha256": digest_json(chunks),
        "execution": execution_metadata or {},
    }
    cache_dir = Path(cache_dir) / digest_json(header)
    cache_dir.mkdir(parents=True, exist_ok=True)
    vectors = []
    for offset in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[offset : offset + BATCH_SIZE]
        path = cache_dir / f"batch-{offset:06d}.json"
        key = digest_json({"header": header, "offset": offset, "chunks": batch})
        if path.exists():
            saved = json.loads(path.read_text())
            if saved.get("key") != key or saved.get("sha256") != digest_json(saved.get("vectors")):
                raise ValueError("embedding checkpoint mismatch")
            batch_vectors = saved["vectors"]
        else:
            batch_vectors = [_vector(v) for v in embedder.embed_batch([c["text"] for c in batch])]
            _write(path, {"key": key, "vectors": batch_vectors, "sha256": digest_json(batch_vectors)})
        if len(batch_vectors) != len(batch):
            raise ValueError("embedding batch count mismatch")
        vectors.extend(_vector(v) for v in batch_vectors)
    if current_digest(conn, package["book_name"]) != header["body_sha256"]:
        raise ValueError("published body changed during embedding preparation")
    staged = {**header, "chunks": chunks, "vectors": vectors}
    staged["staged_sha256"] = digest_json(staged)
    _write(cache_dir / "staged.json", staged)
    return staged


def _validate_staged(conn: sqlite3.Connection, package: dict[str, Any], staged: dict[str, Any]) -> dict[str, Any]:
    source = _source(conn, package)
    if staged.get("staged_sha256") != digest_json({k: v for k, v in staged.items() if k != "staged_sha256"}):
        raise ValueError("staged artifact digest mismatch")
    if any(
        staged.get(key) != value
        for key, value in {
            "schema": SCHEMA,
            "book_name": package["book_name"],
            "package_sha256": package["package_sha256"],
            "body_sha256": source["current_sha256"],
            "run_id": source["run_id"],
            "settings": _settings(),
        }.items()
    ):
        raise ValueError("staged artifact source/settings conflict")
    expected = _chunks(conn, package)
    if staged.get("chunks") != expected or staged.get("chunks_sha256") != digest_json(expected):
        raise ValueError("staged chunks differ from published body")
    if not expected or len(staged.get("vectors", [])) != len(expected):
        raise ValueError("staged vector count mismatch")
    for vector in staged["vectors"]:
        _vector(vector)
    return source


def _filter(name: str) -> str:
    return "book_name = '" + name.replace("'", "''") + "'"


def verify_build(conn: sqlite3.Connection, package: dict[str, Any], staged: dict[str, Any]) -> dict[str, Any]:
    source = _validate_staged(conn, package, staged)
    name = package["book_name"]
    rows = conn.execute(
        "SELECT c.id,c.page_id,p.page_no,c.chunk_idx,c.text,c.char_count,c.contextual_text,c.contextual_generated_at "
        "FROM chunks c JOIN pages p ON p.id=c.page_id JOIN books b ON b.id=p.book_id "
        "WHERE b.name=? ORDER BY p.page_no,c.chunk_idx,c.id",
        (name,),
    ).fetchall()
    ids = ",".join(str(row[0]) for row in rows)
    condition = _filter(name) + (f" OR chunk_id IN ({ids})" if ids else "")
    vectors = get_chunks_table().search().where(condition).limit(max(len(rows) + 1, 1)).to_list()
    by_id = {row["chunk_id"]: row for row in vectors}
    if len(rows) != len(staged["chunks"]) or len(vectors) != len(rows) or len(by_id) != len(rows):
        raise ValueError("SQLite/Lance chunk count or duplicate mismatch")
    page_count = len(package["pages"])
    for row, chunk, vector in zip(rows, staged["chunks"], staged["vectors"], strict=True):
        expected_sql = [
            chunk["page_id"],
            chunk["page_no"],
            chunk["chunk_idx"],
            chunk["text"],
            len(chunk["text"]),
            None,
            None,
        ]
        if list(row)[1:] != expected_sql:
            raise ValueError("SQLite chunk/page/text mismatch")
        actual = by_id.get(row[0])
        expected_lance = {
            "chunk_id": row[0],
            "book_name": name,
            "page_no": chunk["page_no"],
            "text": chunk["text"],
            "char_count": chunk["char_count"],
            "page_count": page_count,
        }
        if not actual or any(actual.get(k) != v for k, v in expected_lance.items()):
            raise ValueError("Lance chunk identity/metadata mismatch")
        if _vector(actual["embedding"]) != _vector(vector):
            raise ValueError("Lance embedding mismatch")
    book_id = conn.execute("SELECT id FROM books WHERE name=?", (name,)).fetchone()[0]
    book = conn.execute(
        "SELECT summary,summary_generated_at,catalog_summary,catalog_summary_generated_at FROM books WHERE id=?",
        (book_id,),
    ).fetchone()
    if any(value is not None for value in book):
        raise ValueError("stale textual summaries remain")
    for derivative in ("book_characters", "character_relations", "summary_grounding_reports", "fact_extraction_blocks"):
        if conn.execute(f"SELECT count(*) FROM {derivative} WHERE book_id=?", (book_id,)).fetchone()[0]:
            raise ValueError("stale character/fact derivatives remain")
    if conn.execute(
        "SELECT count(*) FROM pages WHERE book_id=? AND main_characters IS NOT NULL", (book_id,)
    ).fetchone()[0]:
        raise ValueError("stale page characters remain")
    if get_summaries_table().count_rows(_filter(name)):
        raise ValueError("stale summary vectors remain")
    return {
        "book_name": name,
        "run_id": source["run_id"],
        "package_sha256": package["package_sha256"],
        "body_sha256": source["current_sha256"],
        "staged_sha256": staged["staged_sha256"],
        "settings": staged["settings"],
        "chunks_verified": len(rows),
        "derivatives": "invalidated",
        "execution": staged.get("execution", {}),
    }


def _invalidate(conn: sqlite3.Connection, book_id: int) -> None:
    conn.execute(
        "UPDATE books SET summary=NULL,summary_generated_at=NULL,catalog_summary=NULL,"
        "catalog_summary_generated_at=NULL WHERE id=?",
        (book_id,),
    )
    for table in ("book_characters", "character_relations", "summary_grounding_reports", "fact_extraction_blocks"):
        conn.execute(f"DELETE FROM {table} WHERE book_id=?", (book_id,))
    conn.execute("UPDATE pages SET main_characters=NULL WHERE book_id=?", (book_id,))


def publish_build(conn: sqlite3.Connection, package: dict[str, Any], staged: dict[str, Any]) -> dict[str, Any]:
    if conn.in_transaction:
        raise ValueError("publication requires a clean connection")
    source = _validate_staged(conn, package, staged)
    name = package["book_name"]
    book_id, ready = conn.execute("SELECT id,indexed_at FROM books WHERE name=?", (name,)).fetchone()
    manifest = json.loads(
        conn.execute("SELECT runtime_manifest_json FROM ocr_runs WHERE id=?", (source["run_id"],)).fetchone()[0]
    )
    prior = manifest.get("rag_build", {})
    if ready and prior.get("state") == "ready" and prior.get("staged_sha256") == staged["staged_sha256"]:
        try:
            result = verify_build(conn, package, staged)
        except Exception as error:
            conn.rollback()
            conn.execute("UPDATE books SET indexed_at=NULL WHERE id=?", (book_id,))
            manifest["rag_build"] = {"state": "failed", "staged_sha256": staged["staged_sha256"], "error": str(error)}
            conn.execute(
                "UPDATE ocr_runs SET runtime_manifest_json=? WHERE id=?", (json.dumps(manifest), source["run_id"])
            )
            conn.commit()
            raise
        conn.commit()
        return {**result, "status": "already_built"}
    conn.execute("BEGIN IMMEDIATE")
    _validate_staged(conn, package, staged)
    conn.execute("UPDATE books SET indexed_at=NULL WHERE id=?", (book_id,))
    _invalidate(conn, book_id)
    manifest["rag_build"] = {
        "state": "building",
        "staged_sha256": staged["staged_sha256"],
        "body_sha256": staged["body_sha256"],
    }
    conn.execute("UPDATE ocr_runs SET runtime_manifest_json=? WHERE id=?", (json.dumps(manifest), source["run_id"]))
    conn.commit()  # Fail closed before the first non-transactional Lance mutation.
    try:
        conn.execute("BEGIN IMMEDIATE")
        _validate_staged(conn, package, staged)
        _invalidate(conn, book_id)
        get_summaries_table().delete(_filter(name))
        table = get_chunks_table()
        old_ids = [
            row[0]
            for row in conn.execute(
                "SELECT c.id FROM chunks c JOIN pages p ON p.id=c.page_id WHERE p.book_id=?", (book_id,)
            )
        ]
        deletion = _filter(name) + (" OR chunk_id IN (" + ",".join(map(str, old_ids)) + ")" if old_ids else "")
        table.delete(deletion)  # Includes orphan IDs and metadata with the wrong book name.
        conn.execute("DELETE FROM chunks WHERE page_id IN (SELECT id FROM pages WHERE book_id=?)", (book_id,))
        lance_rows = []
        for chunk, vector in zip(staged["chunks"], staged["vectors"], strict=True):
            cursor = conn.execute(
                "INSERT INTO chunks(page_id,chunk_idx,text,char_count) VALUES(?,?,?,?)",
                (chunk["page_id"], chunk["chunk_idx"], chunk["text"], len(chunk["text"])),
            )
            lance_rows.append(
                {
                    "chunk_id": cursor.lastrowid,
                    "book_name": name,
                    "page_no": chunk["page_no"],
                    "text": chunk["text"],
                    "char_count": chunk["char_count"],
                    "page_count": len(package["pages"]),
                    "embedding": _vector(vector),
                }
            )
        table.add(lance_rows)
        result = verify_build(conn, package, staged)
        manifest["rag_build"] = {**result, "state": "ready"}
        conn.execute("UPDATE ocr_runs SET runtime_manifest_json=? WHERE id=?", (json.dumps(manifest), source["run_id"]))
        conn.execute("UPDATE books SET indexed_at=datetime('now','+9 hours') WHERE id=?", (book_id,))
        conn.commit()
        return {**result, "status": "built"}
    except Exception as error:
        conn.rollback()
        manifest["rag_build"] = {"state": "failed", "staged_sha256": staged["staged_sha256"], "error": str(error)}
        conn.execute("UPDATE ocr_runs SET runtime_manifest_json=? WHERE id=?", (json.dumps(manifest), source["run_id"]))
        conn.commit()
        raise
