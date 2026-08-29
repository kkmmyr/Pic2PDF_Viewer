from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tools.dependency_audit import AllowlistError, build_audit_command, load_allowlist


def _write_allowlist(path: Path, *, expires: str = "2026-10-18", ids: str = '"GHSA-test"') -> None:
    path.write_text(
        "\n".join(
            (
                "version = 1",
                "[[exemptions]]",
                'package = "torch"',
                'locked_version = "2.6.0+cu124"',
                f"expires = {expires}",
                'reason = "GPU互換性を実機確認する"',
                f"ids = [{ids}]",
            )
        ),
        encoding="utf-8",
    )


def test_load_allowlist_accepts_unexpired_entry(tmp_path: Path):
    path = tmp_path / "allowlist.toml"
    _write_allowlist(path)

    exemptions = load_allowlist(path, today=date(2026, 7, 18))

    assert exemptions[0].ids == ("GHSA-test",)


def test_load_allowlist_rejects_expired_entry(tmp_path: Path):
    path = tmp_path / "allowlist.toml"
    _write_allowlist(path, expires="2026-07-17")

    with pytest.raises(AllowlistError, match="期限"):
        load_allowlist(path, today=date(2026, 7, 18))


def test_load_allowlist_rejects_duplicate_id(tmp_path: Path):
    path = tmp_path / "allowlist.toml"
    _write_allowlist(path, ids='"GHSA-test", "GHSA-test"')

    with pytest.raises(AllowlistError, match="重複"):
        load_allowlist(path, today=date(2026, 7, 18))


def test_build_audit_command_includes_every_id(tmp_path: Path):
    path = tmp_path / "allowlist.toml"
    _write_allowlist(path, ids='"GHSA-one", "PYSEC-two"')
    exemptions = load_allowlist(path, today=date(2026, 7, 18))

    assert build_audit_command(exemptions) == [
        "uv",
        "--preview-features",
        "audit",
        "audit",
        "--locked",
        "--ignore",
        "GHSA-one",
        "--ignore",
        "PYSEC-two",
    ]
