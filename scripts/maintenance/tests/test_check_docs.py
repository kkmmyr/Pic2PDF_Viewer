"""Documentation lifecycle guardrail tests."""

import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_docs.py"
sys.path.insert(0, str(_SCRIPT_PATH.parent))
_SPEC = importlib.util.spec_from_file_location("check_docs", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"line {index}" for index in range(count)), encoding="utf-8"
    )


def test_adr_size_rejects_experiment_log_bloat(tmp_path: Path, monkeypatch) -> None:
    adr_dir = tmp_path / "ADR"
    _write_lines(adr_dir / "0001_example.md", _MODULE.ADR_DOC_LINE_LIMIT + 1)
    monkeypatch.setattr(_MODULE, "ADR_DIR", adr_dir)
    monkeypatch.setattr(_MODULE, "PROJECT_ROOT", tmp_path)

    violations = _MODULE.check_adr_size()

    assert len(violations) == 1
    assert "archive/検証" in violations[0]


def test_technical_knowledge_size_requires_history_split(
    tmp_path: Path, monkeypatch
) -> None:
    knowledge_dir = tmp_path / "knowledge"
    _write_lines(knowledge_dir / "large.md", _MODULE.TECH_KNOWLEDGE_LINE_LIMIT + 1)
    monkeypatch.setattr(_MODULE, "TECH_KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(_MODULE, "PROJECT_ROOT", tmp_path)

    violations = _MODULE.check_technical_knowledge_size()

    assert len(violations) == 1
    assert "検証履歴" in violations[0]


def test_plan_lifecycle_accepts_only_active_or_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    plan_dir = tmp_path / "plans"
    plan_dir.mkdir()
    (plan_dir / "active.md").write_text(
        "# Active\n\n> status: active | last-verified: 2026-08-22 | owner: owner\n",
        encoding="utf-8",
    )
    (plan_dir / "completed.md").write_text(
        "# Done\n\n> status: completed | last-verified: 2026-08-22 | owner: owner\n",
        encoding="utf-8",
    )
    (plan_dir / "missing.md").write_text("# Missing\n", encoding="utf-8")
    monkeypatch.setattr(_MODULE, "PLAN_DIR", plan_dir)
    monkeypatch.setattr(_MODULE, "PROJECT_ROOT", tmp_path)

    violations = _MODULE.check_plan_lifecycle()

    assert len(violations) == 2
    assert any("archive" in violation for violation in violations)
    assert any("statusヘッダ" in violation for violation in violations)


def test_managed_module_design_doc_requires_status_header(
    tmp_path: Path, monkeypatch
) -> None:
    design_dir = tmp_path / "docs" / "design"
    design_dir.mkdir(parents=True)
    module_doc = tmp_path / "kindle-pdf" / "docs" / "detailed_design.md"
    module_doc.parent.mkdir(parents=True)
    module_doc.write_text("# Module design\n", encoding="utf-8")
    monkeypatch.setattr(_MODULE, "DESIGN_DIR", design_dir)
    monkeypatch.setattr(_MODULE, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(_MODULE, "MANAGED_MODULE_DESIGN_DOCS", (module_doc,))

    violations = _MODULE.check_design_headers()

    assert len(violations) == 1
    assert str(Path("kindle-pdf") / "docs" / "detailed_design.md") in violations[0]


def test_managed_module_design_doc_rejects_broken_markdown_link(
    tmp_path: Path, monkeypatch
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    module_doc = tmp_path / "kindle-pdf" / "docs" / "detailed_design.md"
    module_doc.parent.mkdir(parents=True)
    module_doc.write_text(
        "# Module design\n\n"
        "> status: living | last-verified: 2026-09-05\n\n"
        "[missing](missing.md)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_MODULE, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(_MODULE, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(_MODULE, "MANAGED_MODULE_DESIGN_DOCS", (module_doc,))

    violations, frozen_info = _MODULE.check_broken_links()

    assert len(violations) == 1
    assert str(Path("kindle-pdf") / "docs" / "detailed_design.md") in violations[0]
    assert frozen_info == []
