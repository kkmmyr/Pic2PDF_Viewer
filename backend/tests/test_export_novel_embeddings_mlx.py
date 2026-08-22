from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.export_novel_embeddings_mlx import (
    PROFILES,
    MlxEmbedder,
    load_chunks,
    open_sqlite_read_only,
    verify_model,
)


def _create_chunks_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY,
            book_id INTEGER NOT NULL,
            page_no INTEGER NOT NULL,
            index_eligible INTEGER NOT NULL
        );
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            page_id INTEGER NOT NULL,
            chunk_idx INTEGER NOT NULL,
            text TEXT NOT NULL,
            contextual_text TEXT
        );
        INSERT INTO books VALUES (1, '評価本');
        INSERT INTO pages VALUES (10, 1, 7, 1), (11, 1, 8, 0);
        INSERT INTO chunks VALUES
            (100, 10, 0, '本文', '位置説明'),
            (101, 10, 1, '本文だけ', NULL),
            (102, 11, 0, '対象外', '対象外文脈');
        """
    )
    conn.commit()
    conn.close()


def _create_fake_model(path: Path, *, model_type: str = "xlm-roberta") -> None:
    (path / "1_Pooling").mkdir(parents=True)
    (path / "config.json").write_text(
        json.dumps({"model_type": model_type, "architectures": ["FakeModel"]}),
        encoding="utf-8",
    )
    (path / "model.safetensors").write_bytes(b"weights")
    (path / "tokenizer.json").write_text("{}", encoding="utf-8")
    (path / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (path / "1_Pooling" / "config.json").write_text(
        json.dumps({"pooling_mode_cls_token": True}),
        encoding="utf-8",
    )


def test_profiles_keep_official_query_contracts() -> None:
    query = "王の誓い"

    assert PROFILES["bge_m3"].query_input(query) == query
    assert PROFILES["qwen3_embedding"].query_input(query).endswith("Query:王の誓い")
    assert PROFILES["harrier"].query_input(query).endswith("Query: 王の誓い")


def test_load_chunks_uses_context_and_keeps_source_read_only(tmp_path: Path) -> None:
    database = tmp_path / "novel.db"
    _create_chunks_db(database)
    before = database.read_bytes()

    conn = open_sqlite_read_only(database)
    try:
        chunks = load_chunks(conn, PROFILES["bge_m3"])
    finally:
        conn.close()

    assert [chunk.chunk_id for chunk in chunks] == [100, 101]
    assert chunks[0].embedding_input == "位置説明\n\n本文"
    assert chunks[1].embedding_input == "本文だけ"
    assert database.read_bytes() == before


def test_verify_model_records_hashes_and_cls_pooling(tmp_path: Path) -> None:
    _create_fake_model(tmp_path)

    manifest = verify_model(tmp_path, PROFILES["bge_m3"], "0" * 40)

    assert manifest["model_type"] == "xlm-roberta"
    assert manifest["pooling"] == "cls"
    assert manifest["trust_remote_code"] is False
    assert set(manifest["files"]) == {
        "config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "1_Pooling/config.json",
    }


def test_verify_model_rejects_checkpoint_python(tmp_path: Path) -> None:
    _create_fake_model(tmp_path)
    (tmp_path / "modeling_custom.py").write_text("raise RuntimeError", encoding="utf-8")

    with pytest.raises(RuntimeError, match="executable Python"):
        verify_model(tmp_path, PROFILES["bge_m3"], "0" * 40)


def test_verify_model_rejects_mutable_revision(tmp_path: Path) -> None:
    _create_fake_model(tmp_path)

    with pytest.raises(ValueError, match="immutable commit SHA"):
        verify_model(tmp_path, PROFILES["bge_m3"], "main")


def test_verify_model_validates_local_conversion_provenance(tmp_path: Path) -> None:
    _create_fake_model(tmp_path)
    revision = "0" * 40

    def sha256(name: str) -> str:
        return hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()

    conversion = {
        "schema_version": 1,
        "source": {
            "model_id": PROFILES["bge_m3"].model_id,
            "revision": revision,
        },
        "conversion": {"tool": "test", "dtype": "float16"},
        "output": {
            "config_sha256": sha256("config.json"),
            "model_sha256": sha256("model.safetensors"),
            "tokenizer_sha256": sha256("tokenizer.json"),
            "tokenizer_config_sha256": sha256("tokenizer_config.json"),
        },
    }
    (tmp_path / "conversion_manifest.json").write_text(json.dumps(conversion), encoding="utf-8")

    manifest = verify_model(tmp_path, PROFILES["bge_m3"], revision)

    assert manifest["conversion"] == conversion
    assert "conversion_manifest.json" in manifest["files"]

    conversion["output"]["model_sha256"] = "f" * 64
    (tmp_path / "conversion_manifest.json").write_text(json.dumps(conversion), encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash mismatch: model.safetensors"):
        verify_model(tmp_path, PROFILES["bge_m3"], revision)


def test_embed_casts_bfloat16_output_on_mlx_side_before_numpy() -> None:
    class FakeEmbedding:
        def __init__(self) -> None:
            self.cast_dtype: object | None = None

        def astype(self, dtype: object) -> np.ndarray:
            self.cast_dtype = dtype
            return np.asarray([[0.3, 0.4]], dtype=np.float32)

    class FakeModel:
        def __init__(self, output: FakeEmbedding) -> None:
            self.output = output

        def __call__(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(text_embeds=self.output)

    class FakeTokenizer:
        def __call__(self, *_args: object, **_kwargs: object) -> dict[str, np.ndarray]:
            return {
                "attention_mask": np.asarray([[1]], dtype=np.int32),
                "input_ids": np.asarray([[7]], dtype=np.int32),
            }

        def encode(self, _text: str, *, add_special_tokens: bool) -> list[int]:
            assert add_special_tokens is True
            return [7]

    float32_sentinel = object()
    evaluated: list[object] = []
    embedding = FakeEmbedding()
    embedder = object.__new__(MlxEmbedder)
    embedder._mx = SimpleNamespace(  # type: ignore[attr-defined]
        array=lambda value: value,
        eval=evaluated.append,
        float32=float32_sentinel,
    )
    embedder._model = FakeModel(embedding)  # type: ignore[attr-defined]
    embedder._tokenizer = FakeTokenizer()  # type: ignore[attr-defined]
    embedder._normalize = True  # type: ignore[attr-defined]
    embedder.max_length = 128

    vectors, _stats = embedder.embed(["本文"])

    assert embedding.cast_dtype is float32_sentinel
    assert len(evaluated) == 1
    assert vectors.dtype == np.float32
    np.testing.assert_allclose(vectors, [[0.6, 0.8]])
