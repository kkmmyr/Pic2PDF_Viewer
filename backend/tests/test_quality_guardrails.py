from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAINTENANCE_DIR = PROJECT_ROOT / "scripts" / "maintenance"
if str(MAINTENANCE_DIR) not in sys.path:
    sys.path.insert(0, str(MAINTENANCE_DIR))


def _load_script(name: str):
    path = PROJECT_ROOT / "scripts" / "maintenance" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


code_size = _load_script("check_code_size")
openapi_contract = _load_script("check_openapi_contract")
import_boundaries = _load_script("check_import_boundaries")
monthly_audit = _load_script("monthly_health_audit")
docs_contracts = _load_script("check_docs_contracts")
check_docs = _load_script("check_docs")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("backend/services/example.py", True),
        ("kindle-pdf/capturer.py", True),
        ("frontend/src/features/example.ts", True),
        ("frontend/src/types/api.d.ts", False),
        ("backend/tests/test_example.py", False),
        ("backend/.venv/Lib/site-packages/example.py", False),
        ("backend/alembic/versions/001_example.py", False),
        ("kindle-pdf/tests/test_capturer.py", False),
        ("frontend/src/test/example.test.ts", False),
        ("frontend/src/features/example.spec.tsx", False),
    ],
)
def test_code_size_production_source_exclusions(path: str, expected: bool) -> None:
    assert code_size.is_production_source(Path(path)) is expected


def test_code_size_rejects_new_and_growing_oversized_files() -> None:
    baseline = {"backend/existing.py": 450}
    current = {
        "backend/existing.py": 451,
        "backend/new_large.py": 401,
        "backend/normal.py": 400,
    }

    assert code_size.find_regressions(baseline, current) == [
        "code size worsened: backend/existing.py = 451 lines (baseline 450)",
        "new oversized production file: backend/new_large.py = 401 lines (limit 400)",
    ]


def test_code_size_prunes_excluded_directories_before_descent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "backend").mkdir()

    def fake_walk(root: Path):
        dirnames = ["data", "services"]
        yield str(root), dirnames, []
        assert dirnames == ["services"]

    monkeypatch.setattr(code_size.os, "walk", fake_walk)

    assert code_size.collect_line_counts(tmp_path) == {}


def test_openapi_normalization_is_stable_and_drops_runtime_servers() -> None:
    first = {
        "servers": [{"url": "http://localhost:8766"}],
        "paths": {"/b": {"get": {}}, "/a": {"post": {}}},
        "info": {"version": "1", "title": "Example"},
    }
    second = {
        "info": {"title": "Example", "version": "1"},
        "paths": {"/a": {"post": {}}, "/b": {"get": {}}},
    }

    assert openapi_contract.normalize_schema(first) == openapi_contract.normalize_schema(second)


def test_import_boundaries_detect_all_three_layer_violations(tmp_path: Path) -> None:
    files = {
        "backend/services/bad.py": "from routers import library\n",
        "frontend/src/hooks/bad.ts": "import { Page } from '@/pages/ViewerPage';\n",
        "kindle-pdf/kindle_app_reader.py": ("from capture_agent_transport import AgentConfig\n"),
        "backend/services/good.py": "from utils import logger\n",
    }
    for relative, content in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    assert import_boundaries.find_violations(tmp_path) == [
        "backend/services/bad.py:1: backend service must not import routers (routers)",
        ("frontend/src/hooks/bad.ts:1: frontend lower layer must not import pages (@/pages/ViewerPage)"),
        (
            "kindle-pdf/kindle_app_reader.py:1: Kindle controller/capturer must not "
            "import agent/backend layer (capture_agent_transport)"
        ),
    ]


def test_import_boundaries_reject_reviewed_compatibility_facades(tmp_path: Path) -> None:
    files = {
        "backend/services/novel_db/rag_bad.py": "from ._llm_backend import QWEN_BACKEND\n",
        "backend/services/novel_db/ocr_bad.py": "from services.novel_db import ocr_staging\n",
        "backend/scripts/bad.py": "from services.novel_db._prompts import MAP_PROMPT\n",
        "frontend/src/features/bad.ts": ("import { streamQa } from '@/features/novel_db/sse';\n"),
    }
    for relative, content in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    assert import_boundaries.find_violations(tmp_path) == [
        (
            "backend/scripts/bad.py:1: Novel RAG script must not import compatibility "
            "facade (services.novel_db._prompts)"
        ),
        (
            "backend/services/novel_db/ocr_bad.py:1: Novel OCR production must not import "
            "compatibility facade (services.novel_db.ocr_staging)"
        ),
        (
            "backend/services/novel_db/rag_bad.py:1: Novel RAG production must not import "
            "compatibility facade (._llm_backend)"
        ),
        (
            "frontend/src/features/bad.ts:1: frontend production must not import removed "
            "compatibility facade (@/features/novel_db/sse)"
        ),
    ]


def test_monthly_audit_detects_completed_plan_outside_coordinators(
    tmp_path: Path,
) -> None:
    plan_dir = tmp_path / "docs" / "log" / "計画"
    plan_dir.mkdir(parents=True)
    (plan_dir / "完了計画.md").write_text("# 完了計画\n\n> 状態: 完了\n", encoding="utf-8")
    (plan_dir / "バックログ.md").write_text("# バックログ\n\n> 状態: 完了\n", encoding="utf-8")
    (plan_dir / "進行中.md").write_text("# 進行中\n\n> 状態: 実施中\n", encoding="utf-8")
    (plan_dir / "部分完了.md").write_text("# 部分完了\n\n> 状態: Phase 1完了、Phase 2実施中\n", encoding="utf-8")
    (plan_dir / "フェーズ完了.md").write_text(
        "# フェーズ完了\n\n> 状態: Phase 5 実装・実機受入完了\n",
        encoding="utf-8",
    )

    assert monthly_audit.find_completed_plan_files(plan_dir) == [
        "docs/log/計画/フェーズ完了.md",
        "docs/log/計画/完了計画.md",
    ]


def test_monthly_audit_resolves_npm_launcher(monkeypatch) -> None:
    monkeypatch.setattr(
        monthly_audit.shutil,
        "which",
        lambda name: "C:/node/npm.cmd" if name == "npm" else None,
    )

    frontend_check = next(check for check in monthly_audit.audit_commands("python") if check.name == "frontend-unused")

    assert frontend_check.command == ("C:/node/npm.cmd", "run", "lint:deps")


def test_docs_size_violation_is_blocking(monkeypatch) -> None:
    monkeypatch.setattr(check_docs, "check_broken_links", lambda: ([], []))
    monkeypatch.setattr(check_docs, "check_changelog_size", lambda: [])
    monkeypatch.setattr(check_docs, "check_nav_sync", lambda: [])
    monkeypatch.setattr(
        check_docs,
        "check_design_doc_size",
        lambda: ["docs/design/large.md: 801 行"],
    )
    monkeypatch.setattr(check_docs, "check_design_headers", lambda: [])
    monkeypatch.setattr(check_docs, "check_file_map_annotations", lambda: [])
    monkeypatch.setattr(check_docs, "check_canonical_contracts", lambda: ([], []))

    with pytest.raises(SystemExit) as exc_info:
        check_docs.main()

    assert exc_info.value.code == 1


def _write_contract_fixture(tmp_path: Path, *, canonical_link: bool = True) -> Path:
    owner = tmp_path / "docs" / "design" / "owner.md"
    owner.parent.mkdir(parents=True)
    owner.write_text(
        "# Owner\n\n<!-- contract-owner: example-contract -->\n",
        encoding="utf-8",
    )
    index = tmp_path / "docs" / "index.md"
    link = "[Owner](design/owner.md)" if canonical_link else "Owner"
    index.write_text(
        f'<a id="canonical-map"></a>\n## 正本マップ\n\n{link}\n\n## Next\n',
        encoding="utf-8",
    )
    registry = tmp_path / "scripts" / "maintenance" / "docs_contracts.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        '{"contracts":[{"id":"example-contract","owner":"docs/design/owner.md"}]}',
        encoding="utf-8",
    )
    return owner


def test_docs_contracts_accepts_unique_linked_owner(tmp_path: Path) -> None:
    _write_contract_fixture(tmp_path)

    assert docs_contracts.find_violations(tmp_path) == ([], [])


def test_docs_contracts_rejects_missing_map_link_and_duplicate_owner(
    tmp_path: Path,
) -> None:
    _write_contract_fixture(tmp_path, canonical_link=False)
    duplicate = tmp_path / "docs" / "design" / "duplicate.md"
    duplicate.write_text(
        "<!-- contract-owner: example-contract -->\n",
        encoding="utf-8",
    )

    link_violations, marker_violations = docs_contracts.find_violations(tmp_path)

    assert link_violations == ["example-contract: 正本マップにownerリンクがありません (docs/design/owner.md)"]
    assert marker_violations == [
        "example-contract: owner markerが正本以外または重複です (docs/design/duplicate.md, docs/design/owner.md)"
    ]
