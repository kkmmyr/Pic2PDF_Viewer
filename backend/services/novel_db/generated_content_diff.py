"""生成内容snapshotの差分・品質評価・Markdown renderer。"""

from __future__ import annotations

from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .generated_content_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    CharacterSnapshot,
    GeneratedContentSnapshot,
    write_json,
)
from .generation_quality import generated_prose_issues
from .summary_prompts import CATALOG_SUMMARY_MAX_CHARS, CATALOG_SUMMARY_MIN_CHARS


def build_generated_content_diff(
    before: GeneratedContentSnapshot,
    after: GeneratedContentSnapshot,
) -> dict[str, Any]:
    if before.book_name != after.book_name:
        raise ValueError(f"book mismatch: {before.book_name} != {after.book_name}")
    before_chars = {item.name: item for item in before.characters}
    after_chars = {item.name: item for item in after.characters}
    added = sorted(after_chars.keys() - before_chars.keys())
    removed = sorted(before_chars.keys() - after_chars.keys())
    changed = [
        _character_change(before_chars[name], after_chars[name])
        for name in sorted(before_chars.keys() & after_chars.keys())
        if before_chars[name] != after_chars[name]
    ]
    quality = _quality(after)
    summary_changed = before.summary != after.summary
    catalog_changed = before.catalog_summary != after.catalog_summary
    review_required = summary_changed or catalog_changed or bool(added or removed or changed)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "book_name": before.book_name,
        "compared_at": datetime.now(UTC).isoformat(),
        "before": before.to_dict(),
        "after": after.to_dict(),
        "summary_change": _text_change(
            before.summary,
            after.summary,
            generated_at_changed=before.summary_generated_at != after.summary_generated_at,
        ),
        "catalog_summary_change": _text_change(
            before.catalog_summary,
            after.catalog_summary,
            generated_at_changed=(before.catalog_summary_generated_at != after.catalog_summary_generated_at),
        ),
        "character_changes": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "before_count": len(before.characters),
            "after_count": len(after.characters),
        },
        "quality": quality,
        "review": {
            "required": review_required,
            "targets": [
                *(["summary"] if summary_changed else []),
                *(["catalog_summary"] if catalog_changed else []),
                *[f"character:{name}" for name in added],
                *[f"character:{name}" for name in removed],
                *[f"character:{item['name']}" for item in changed],
            ],
        },
    }


def _quality(snapshot: GeneratedContentSnapshot) -> dict[str, Any]:
    summary_issues = generated_prose_issues(snapshot.summary or "")
    catalog_issues = generated_prose_issues(snapshot.catalog_summary or "")
    catalog_length = len(snapshot.catalog_summary or "")
    if not CATALOG_SUMMARY_MIN_CHARS <= catalog_length <= CATALOG_SUMMARY_MAX_CHARS:
        catalog_issues.append(
            f"catalog summary length must be {CATALOG_SUMMARY_MIN_CHARS}-{CATALOG_SUMMARY_MAX_CHARS}: {catalog_length}"
        )
    character_issues = {
        item.name: issues
        for item in snapshot.characters
        if (
            issues := generated_prose_issues(
                item.summary or "",
                required_subject=item.name,
            )
        )
    }
    return {
        "passed": not summary_issues and not catalog_issues and not character_issues and bool(snapshot.characters),
        "summary_issues": summary_issues,
        "catalog_summary_issues": catalog_issues,
        "character_issues": character_issues,
        "no_characters": not snapshot.characters,
    }


def render_diff_markdown(report: dict[str, Any]) -> str:
    before = report["before"]
    after = report["after"]
    summary_change = report["summary_change"]
    catalog_change = report["catalog_summary_change"]
    character_changes = report["character_changes"]
    quality = report["quality"]
    lines = [
        f"# 生成内容差分監査: {report['book_name']}",
        "",
        f"- 比較日時: `{report['compared_at']}`",
        f"- 要約変更: `{summary_change['changed']}` （{summary_change['before_chars']} → "
        f"{summary_change['after_chars']}文字、類似度 {summary_change['similarity']:.3f}）",
        f"- 一覧向け短縮要約変更: `{catalog_change['changed']}` "
        f"（{catalog_change['before_chars']} → {catalog_change['after_chars']}文字、"
        f"類似度 {catalog_change['similarity']:.3f}）",
        f"- 人物数: {character_changes['before_count']} → {character_changes['after_count']}",
        f"- 機械品質ゲート: `{'PASS' if quality['passed'] else 'FAIL'}`",
        f"- Codex補助QA: `{'required' if report['review']['required'] else 'not required'}`",
        "",
        "## 人物集合の差分",
        "",
        f"- 追加: {_join_names(character_changes['added'])}",
        f"- 削除: {_join_names(character_changes['removed'])}",
        f"- 変更: {_join_names([item['name'] for item in character_changes['changed']])}",
        "",
        "## 機械品質ゲート",
        "",
        f"- 要約: {_join_names(quality['summary_issues'])}",
        f"- 一覧向け短縮要約: {_join_names(quality['catalog_summary_issues'])}",
        f"- 人物なし: `{quality['no_characters']}`",
    ]
    character_issues = quality["character_issues"]
    lines.extend(
        (f"- {name}: {_join_names(issues)}" for name, issues in character_issues.items())
        if character_issues
        else ["- 人物説明: 問題なし"]
    )
    _append_text_changes(lines, before, after, summary_change, catalog_change)
    _append_character_changes(lines, before, after, character_changes)
    return "\n".join(lines) + "\n"


def _append_text_changes(
    lines: list[str],
    before: dict[str, Any],
    after: dict[str, Any],
    summary_change: dict[str, Any],
    catalog_change: dict[str, Any],
) -> None:
    if summary_change["changed"]:
        lines.extend(["", "## 要約（変更前）", "", before["summary"] or "（なし）"])
        lines.extend(["", "## 要約（変更後）", "", after["summary"] or "（なし）"])
    if catalog_change["changed"]:
        lines.extend(["", "## 一覧向け短縮要約（変更前）", "", before["catalog_summary"] or "（なし）"])
        lines.extend(["", "## 一覧向け短縮要約（変更後）", "", after["catalog_summary"] or "（なし）"])


def _append_character_changes(
    lines: list[str],
    before: dict[str, Any],
    after: dict[str, Any],
    changes: dict[str, Any],
) -> None:
    before_chars = {item["name"]: item for item in before["characters"]}
    after_chars = {item["name"]: item for item in after["characters"]}
    names = [
        *changes["added"],
        *changes["removed"],
        *[item["name"] for item in changes["changed"]],
    ]
    for name in dict.fromkeys(names):
        old = before_chars.get(name)
        new = after_chars.get(name)
        lines.extend(["", f"## 人物: {name}", "", "### 変更前", ""])
        lines.append(old["summary"] if old and old["summary"] else "（なし）")
        lines.extend(["", "### 変更後", ""])
        lines.append(new["summary"] if new and new["summary"] else "（なし）")


def write_diff_report(
    *,
    json_path: Path,
    markdown_path: Path,
    report: dict[str, Any],
) -> None:
    write_json(json_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = markdown_path.with_suffix(markdown_path.suffix + ".tmp")
    temporary.write_text(render_diff_markdown(report), encoding="utf-8")
    temporary.replace(markdown_path)


def _text_change(
    before: str | None,
    after: str | None,
    *,
    generated_at_changed: bool,
) -> dict[str, Any]:
    return {
        "changed": before != after,
        "before_chars": len(before or ""),
        "after_chars": len(after or ""),
        "similarity": _similarity(before, after),
        "generated_at_changed": generated_at_changed,
    }


def _character_change(before: CharacterSnapshot, after: CharacterSnapshot) -> dict[str, Any]:
    return {
        "name": before.name,
        "summary_changed": before.summary != after.summary,
        "before_chars": len(before.summary or ""),
        "after_chars": len(after.summary or ""),
        "similarity": _similarity(before.summary, after.summary),
        "first_page": [before.first_page, after.first_page],
        "page_count": [before.page_count, after.page_count],
        "generated_at_changed": before.generated_at != after.generated_at,
    }


def _similarity(before: str | None, after: str | None) -> float:
    return SequenceMatcher(None, before or "", after or "").ratio()


def _join_names(values: list[str]) -> str:
    return "、".join(values) if values else "なし"
