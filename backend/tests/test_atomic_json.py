import json
import os
from pathlib import Path

import pytest

from utils.atomic_json import atomic_write_json


def test_atomic_write_json_replaces_file_from_same_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "state.json"
    target.write_text('{"old": true}\n', encoding="utf-8")
    original_replace = os.replace
    calls: list[tuple[Path, Path]] = []

    def track_replace(source: str | Path, destination: str | Path) -> None:
        calls.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr(os, "replace", track_replace)
    atomic_write_json(target, {"日本語": [1, 2]})

    assert json.loads(target.read_text(encoding="utf-8")) == {"日本語": [1, 2]}
    assert target.read_text(encoding="utf-8").endswith("\n")
    assert calls[0][0].parent == target.parent
    assert calls[0][1] == target
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_json_keeps_original_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "watchlist.json"
    original = '{"artists": ["old"]}\n'
    target.write_text(original, encoding="utf-8")

    def fail_replace(_source: str | Path, _destination: str | Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        atomic_write_json(target, {"artists": ["new"]})

    assert target.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_json_keeps_original_on_serialization_error(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    original = '{"ok": true}\n'
    target.write_text(original, encoding="utf-8")

    with pytest.raises(TypeError):
        atomic_write_json(target, {"invalid": object()})

    assert target.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("*.tmp")) == []
