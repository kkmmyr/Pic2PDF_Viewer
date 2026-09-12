"""本構築の生成結果と、DB・モデルに接続しない人物公開検査。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple

from .character_names import derive_character_evidence_aliases, normalize_character_entries


@dataclass(frozen=True)
class GeneratedBookContent:
    summary: str
    catalog_summary: str
    characters: Mapping[str, str]


class CharacterRow(NamedTuple):
    name: str
    summary: str
    first_page: int
    page_count: int


def prepare_character_rows(
    char_summaries: Mapping[str, str],
    page_rows: Sequence[tuple[int, str]],
    *,
    log: Callable[[str], None],
    canonical_names: list[str],
) -> list[CharacterRow]:
    """Normalize characters and require evidence in eligible pages before publication."""
    entries = normalize_character_entries(char_summaries, canonical_names=canonical_names)
    prepared: list[CharacterRow] = []
    for entry in entries:
        derived_aliases = derive_character_evidence_aliases(entry.name)
        derived_page_counts = {alias: sum(alias in text for _, text in page_rows) for alias in derived_aliases}
        evidence_aliases = (
            *entry.aliases,
            *(alias for alias, count in derived_page_counts.items() if count >= 2),
        )
        evidence_pages = [page_no for page_no, text in page_rows if any(alias in text for alias in evidence_aliases)]
        if not evidence_pages:
            log(f"  omit character without page evidence: {entry.name}")
            continue
        prepared.append(CharacterRow(entry.name, entry.summary, min(evidence_pages), len(evidence_pages)))
    return prepared


def guard_character_deletion_regression(
    page_texts: Sequence[str],
    *,
    existing_names: list[str],
    prepared_names: list[str],
    log: Callable[[str], None],
) -> None:
    """Reject unexplained deletion of published characters with current page evidence."""
    if not existing_names:
        return

    published = normalize_character_entries(
        {name: name for name in existing_names},
        canonical_names=existing_names,
    )
    prepared = normalize_character_entries(
        {name: name for name in prepared_names},
        canonical_names=[entry.name for entry in published],
    )
    prepared_set = {entry.name for entry in prepared}
    unexplained: list[str] = []
    for entry in published:
        if entry.name in prepared_set:
            continue
        exact_count = sum(entry.name in text for text in page_texts)
        derived_counts = {
            alias: sum(alias in text for text in page_texts) for alias in derive_character_evidence_aliases(entry.name)
        }
        if exact_count > 0 or any(count >= 2 for count in derived_counts.values()):
            unexplained.append(entry.name)
        else:
            log(f"  allow removal without current page evidence: {entry.name}")

    if unexplained:
        names = ", ".join(unexplained)
        raise ValueError(
            "character deletion regression failed; evidenced published characters missing: "
            f"{names}; existing generated content was preserved"
        )
