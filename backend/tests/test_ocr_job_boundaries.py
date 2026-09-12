"""OCR applicationの具体設定・実行moduleへの逆依存を検出する。"""

import builtins
import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from services.novel_db import ocr_job_application as application
from tests.test_quality_guardrails import import_boundaries


@pytest.mark.parametrize(
    ("source", "rejected"),
    [
        ("import config", True),
        ("from config import app_settings", True),
        ("from . import qwen_dots_worker", True),
        ("from .ocr_job_configuration import resolve_ocr_run_spec", True),
        ("import backend.services.novel_db.job_worker", True),
        ("from .ocr_worker_session import OcrSession", True),
        ("import fastapi", True),
        ("from collections.abc import Callable", False),
        ("from utils.logger import get_logger", False),
        ("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .ocr_run_store import OcrInputPage", False),
    ],
)
def test_ocr_application_import_boundary(tmp_path: Path, source: str, rejected: bool) -> None:
    path = tmp_path / "backend/services/novel_db/ocr_job_application.py"
    path.parent.mkdir(parents=True)
    path.write_text(source + "\n", encoding="utf-8")

    violations = import_boundaries.find_violations(tmp_path, require_novel_targets=False)

    assert bool(violations) is rejected
    if rejected:
        assert all("OCR application boundary" in violation for violation in violations)


def test_application_load_does_not_import_concrete_adapters(monkeypatch) -> None:
    """元moduleのcacheに隠れず、型の供給元も実行時importしない。"""
    original_import = builtins.__import__
    forbidden = {"config", "extractor", "ocr_run_store", "qwen_dots_worker", "ocr_job_configuration"}

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if any(part in forbidden for part in name.split(".")) or forbidden.intersection(fromlist or ()):
            raise AssertionError(f"Unexpected runtime import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    name = "services.novel_db._isolated_ocr_application_test"
    spec = importlib.util.spec_from_file_location(name, application.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    spec.loader.exec_module(module)


def test_application_uses_injected_run_spec_once_for_all_books() -> None:
    calls = Mock()
    calls.resolve_run_spec.return_value = application.OcrRunSpec("test-engine", "test-revision")
    calls.collect_input_pages.return_value = []
    calls.prepare_run.side_effect = [(11, []), (12, [])]
    calls.iter_ocr_pages.return_value = iter([])
    deps = application.OcrJobDependencies(
        resolve_run_spec=calls.resolve_run_spec,
        collect_input_pages=calls.collect_input_pages,
        prepare_run=calls.prepare_run,
        iter_ocr_pages=calls.iter_ocr_pages,
        save_page_result=calls.save_page_result,
        mark_run_failed=calls.mark_run_failed,
        stage_run_for_qa=calls.stage_run_for_qa,
    )

    application.execute_ocr_job(7, ["a", "b"], 2, application.OcrJobCallbacks(Mock(), Mock()), deps)

    calls.resolve_run_spec.assert_called_once_with()
    assert calls.mock_calls[0] == call.resolve_run_spec()
    assert calls.prepare_run.call_args_list == [
        call("a", "test-engine", "test-revision", []),
        call("b", "test-engine", "test-revision", []),
    ]
