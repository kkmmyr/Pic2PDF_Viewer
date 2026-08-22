from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts.export_novel_embeddings_mlx import Chunk
from scripts.export_novel_embeddings_pplx_mlx import build_context_windows


@dataclass
class FakeTokenizer:
    sep_token: str = "<SEP>"

    def encode(self, value: str, *, add_special_tokens: bool) -> list[int]:
        if value == self.sep_token:
            return [99]
        overhead = 1 if add_special_tokens else 0
        return list(range(len(value.split()) + overhead))


def _chunk(chunk_id: int, book: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        book_name=book,
        page_no=chunk_id,
        chunk_idx=0,
        embedding_input=text,
    )


def test_context_windows_respect_token_limit_and_book_boundary() -> None:
    chunks = [
        _chunk(1, "A", "one two three"),
        _chunk(2, "A", "four five"),
        _chunk(3, "A", "six seven eight"),
        _chunk(4, "B", "nine"),
    ]

    windows, token_counts = build_context_windows(chunks, FakeTokenizer(), max_length=7)

    assert [[chunk.chunk_id for chunk in window] for window in windows] == [[1, 2], [3], [4]]
    assert token_counts == [7, 4, 2]
    assert all(len({chunk.book_name for chunk in window}) == 1 for window in windows)


def test_context_windows_reject_single_oversized_chunk() -> None:
    chunks = [_chunk(1, "A", "one two three four five")]

    with pytest.raises(RuntimeError, match="exceeds contextual max_length"):
        build_context_windows(chunks, FakeTokenizer(), max_length=5)
