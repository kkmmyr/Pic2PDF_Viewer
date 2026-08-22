from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts.export_novel_embeddings_mlx import Chunk
from scripts.export_novel_embeddings_nemotron_mlx import build_length_sorted_batches


@dataclass
class FakeTokenizer:
    def encode(self, value: str, *, add_special_tokens: bool) -> list[int]:
        overhead = 1 if add_special_tokens else 0
        return list(range(len(value.split()) + overhead))


def _chunk(chunk_id: int, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        book_name="book",
        page_no=chunk_id,
        chunk_idx=0,
        embedding_input=text,
    )


def test_length_batches_sort_by_tokens_and_keep_every_source_index() -> None:
    chunks = [
        _chunk(30, "long text has many words"),
        _chunk(10, "short"),
        _chunk(20, "medium text"),
        _chunk(40, "short"),
    ]

    batches, lengths = build_length_sorted_batches(
        chunks,
        FakeTokenizer(),
        batch_size=2,
        max_length=20,
    )

    assert batches == [[1, 3], [2, 0]]
    assert sorted(index for batch in batches for index in batch) == [0, 1, 2, 3]
    assert lengths[0] > lengths[2] > lengths[1]


def test_length_batches_reject_truncation() -> None:
    chunks = [_chunk(1, "one two three four five")]

    with pytest.raises(RuntimeError, match="exceed max_length"):
        build_length_sorted_batches(
            chunks,
            FakeTokenizer(),
            batch_size=1,
            max_length=5,
        )
