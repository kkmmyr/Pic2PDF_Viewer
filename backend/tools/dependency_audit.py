"""期限・理由付きallowlistを検証してから ``uv audit`` を実行する。"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOWLIST = PROJECT_ROOT / "security" / "uv-audit-allowlist.toml"


class AllowlistError(ValueError):
    """allowlistの形式・期限が監査ポリシーに違反している。"""


@dataclass(frozen=True)
class Exemption:
    package: str
    locked_version: str
    expires: date
    reason: str
    ids: tuple[str, ...]


def _require_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AllowlistError(f"{key} は空でない文字列が必要です")
    return value.strip()


def load_allowlist(path: Path, *, today: date | None = None) -> list[Exemption]:
    """allowlistを読み込み、形式・重複・期限を検証する。"""
    current_date = today or date.today()
    with path.open("rb") as file:
        data = tomllib.load(file)

    if data.get("version") != 1:
        raise AllowlistError("allowlist version は 1 である必要があります")

    raw_exemptions = data.get("exemptions")
    if not isinstance(raw_exemptions, list):
        raise AllowlistError("exemptions 配列が必要です")

    exemptions: list[Exemption] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_exemptions, start=1):
        if not isinstance(raw, dict):
            raise AllowlistError(f"exemptions[{index}] はテーブルである必要があります")
        expires = raw.get("expires")
        if not isinstance(expires, date):
            raise AllowlistError(f"exemptions[{index}].expires は YYYY-MM-DD 形式の日付が必要です")
        if expires < current_date:
            package = raw.get("package", "unknown")
            raise AllowlistError(f"{package} の例外期限 {expires.isoformat()} が切れています")

        raw_ids = raw.get("ids")
        if not isinstance(raw_ids, list) or not raw_ids or not all(isinstance(item, str) for item in raw_ids):
            raise AllowlistError(f"exemptions[{index}].ids は1件以上の文字列配列が必要です")
        ids = tuple(item.strip() for item in raw_ids)
        if any(not item for item in ids):
            raise AllowlistError(f"exemptions[{index}].ids に空文字列は指定できません")
        duplicates = seen_ids.intersection(ids)
        duplicates.update(item for item in ids if ids.count(item) > 1)
        if duplicates:
            raise AllowlistError(f"脆弱性IDが重複しています: {', '.join(sorted(duplicates))}")
        seen_ids.update(ids)

        exemptions.append(
            Exemption(
                package=_require_text(raw, "package"),
                locked_version=_require_text(raw, "locked_version"),
                expires=expires,
                reason=_require_text(raw, "reason"),
                ids=ids,
            )
        )
    return exemptions


def build_audit_command(exemptions: list[Exemption]) -> list[str]:
    """uv auditへ渡す明示的なignore引数を構築する。"""
    command = ["uv", "--preview-features", "audit", "audit", "--locked"]
    for exemption in exemptions:
        for vulnerability_id in exemption.ids:
            command.extend(("--ignore", vulnerability_id))
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    args = parser.parse_args(argv)

    try:
        exemptions = load_allowlist(args.allowlist)
    except (OSError, tomllib.TOMLDecodeError, AllowlistError) as exc:
        print(f"dependency-audit: allowlist error: {exc}", file=sys.stderr)
        return 2

    print("dependency-audit: accepted exemptions")
    for exemption in exemptions:
        print(
            f"- {exemption.package} {exemption.locked_version}: "
            f"{len(exemption.ids)} IDs (expires {exemption.expires.isoformat()})"
        )
    return subprocess.run(build_audit_command(exemptions), cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
