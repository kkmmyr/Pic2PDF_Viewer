from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import novel_eval_runtime


@pytest.fixture
def restore_sys_platform() -> Iterator[None]:
    original = sys.platform
    try:
        yield
    finally:
        sys.platform = original


@pytest.mark.parametrize(
    "module_name",
    (
        "scripts.export_novel_embeddings_mlx",
        "scripts.eval_novel_reranker_mlx",
    ),
)
def test_evaluation_modules_import_without_unix_resource(module_name: str) -> None:
    """Common evaluation code must remain importable on Windows and Linux."""
    script = f"""
import builtins

original_import = builtins.__import__

def block_resource(name, *args, **kwargs):
    if name == 'resource':
        raise ModuleNotFoundError("No module named 'resource'")
    return original_import(name, *args, **kwargs)

builtins.__import__ = block_resource
__import__({module_name!r})
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_rss_adapter_does_not_fabricate_a_value_without_resource() -> None:
    script = """
import builtins

original_import = builtins.__import__

def block_resource(name, *args, **kwargs):
    if name == 'resource':
        raise ModuleNotFoundError("No module named 'resource'")
    return original_import(name, *args, **kwargs)

builtins.__import__ = block_resource
from scripts.novel_eval_runtime import process_max_rss_bytes
try:
    process_max_rss_bytes()
except RuntimeError:
    pass
else:
    raise AssertionError('missing resource must not produce a synthetic RSS value')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("platform", "reported_rss", "expected_bytes"),
    (("darwin", 123, 123), ("linux", 123, 123 * 1024)),
)
def test_rss_adapter_keeps_kernel_unit_contract(
    monkeypatch: pytest.MonkeyPatch,
    restore_sys_platform: None,
    platform: str,
    reported_rss: int,
    expected_bytes: int,
) -> None:
    fake_resource = SimpleNamespace(
        RUSAGE_SELF=object(),
        getrusage=lambda _target: SimpleNamespace(ru_maxrss=reported_rss),
    )
    monkeypatch.setitem(sys.modules, "resource", fake_resource)
    sys.platform = platform

    assert novel_eval_runtime.process_max_rss_bytes() == expected_bytes
