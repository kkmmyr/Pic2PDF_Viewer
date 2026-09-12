"""Block imports that invert reviewed backend, frontend, or Kindle boundaries."""

from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TS_IMPORT_RE = re.compile(
    r"""(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?["'](?P<module>[^"']+)["']"""
)
KINDLE_FORBIDDEN_PREFIXES = (
    "backend",
    "capture_agent",
    "capture_agent_transport",
    "routers",
)
NOVEL_RAG_COMPAT_MODULES = {"_llm_backend", "_prompts"}
NOVEL_OCR_COMPAT_MODULES = {"ocr_qa", "ocr_staging", "surya_ocr"}
FRONTEND_REMOVED_MODULES = {
    "@/features/novel_db/sse",
    "@/hooks/useKindleCatalog",
    "@/types/kindleCatalog",
}


def _python_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            imports.append((node.lineno, module))
            compat_names = NOVEL_RAG_COMPAT_MODULES | NOVEL_OCR_COMPAT_MODULES
            imports.extend(
                (node.lineno, f"{module.rstrip('.')}.{alias.name}")
                for alias in node.names
                if alias.name in compat_names
            )
    return sorted(imports)


def _is_kindle_controller_or_capturer(relative: Path) -> bool:
    if relative.parts[:2] == ("kindle-pdf", "kindle_controller"):
        return True
    if relative.parent.as_posix() == "kindle-pdf" and relative.name.startswith(
        "kindle_app_"
    ):
        return True
    return relative.as_posix() in {
        "kindle-pdf/capture_base.py",
        "kindle-pdf/capture_loop.py",
        "kindle-pdf/capturer.py",
        "kindle-pdf/comic_capturer.py",
        "kindle-pdf/kindle_app_controller.py",
        "kindle-pdf/novel_capturer.py",
    }


def _frontend_imports(path: Path) -> list[tuple[int, str]]:
    content = path.read_text(encoding="utf-8")
    return [
        (content.count("\n", 0, match.start()) + 1, match.group("module"))
        for match in TS_IMPORT_RE.finditer(content)
    ]


def _frontend_imports_page(path: Path, module: str, project_root: Path) -> bool:
    if module == "@/pages" or module.startswith("@/pages/"):
        return True
    if not module.startswith("."):
        return False
    resolved = (path.parent / module).resolve()
    pages_root = (project_root / "frontend" / "src" / "pages").resolve()
    return resolved == pages_root or pages_root in resolved.parents


def _matches_compat_module(module: str, names: set[str]) -> bool:
    normalized = module.lstrip(".")
    return normalized in names or any(normalized.endswith(f".{name}") for name in names)


def _backend_violations(project_root: Path) -> list[str]:
    violations: list[str] = []
    services_root = project_root / "backend" / "services"
    if not services_root.exists():
        return violations
    for path in sorted(services_root.rglob("*.py")):
        relative = path.relative_to(project_root)
        is_novel = relative.parts[:3] == ("backend", "services", "novel_db")
        for line, module in _python_imports(path):
            if module == "routers" or module.startswith(
                ("routers.", "backend.routers.")
            ):
                violations.append(
                    f"{relative.as_posix()}:{line}: backend service must not import "
                    f"routers ({module})"
                )
            if is_novel and _matches_compat_module(module, NOVEL_RAG_COMPAT_MODULES):
                violations.append(
                    f"{relative.as_posix()}:{line}: Novel RAG production must not import "
                    f"compatibility facade ({module})"
                )
            if is_novel and _matches_compat_module(module, NOVEL_OCR_COMPAT_MODULES):
                violations.append(
                    f"{relative.as_posix()}:{line}: Novel OCR production must not import "
                    f"compatibility facade ({module})"
                )
    return violations


def _backend_script_violations(project_root: Path) -> list[str]:
    violations: list[str] = []
    scripts_root = project_root / "backend" / "scripts"
    if not scripts_root.exists():
        return violations
    for path in sorted(scripts_root.rglob("*.py")):
        relative = path.relative_to(project_root)
        for line, module in _python_imports(path):
            if _matches_compat_module(module, NOVEL_RAG_COMPAT_MODULES):
                violations.append(
                    f"{relative.as_posix()}:{line}: Novel RAG script must not import "
                    f"compatibility facade ({module})"
                )
    return violations


def _resolved_backend_imports(path: Path, project_root: Path) -> list[tuple[int, str]]:
    """Resolve relative and from-package imports for the explicitly isolated modules."""
    package = list(path.relative_to(project_root).parent.parts)
    imports: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            prefix = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join(prefix + ([node.module] if node.module else []))
            targets = [module, *(f"{module}.{alias.name}" for alias in node.names)]
        else:
            continue
        imports.update(
            (node.lineno, target.removeprefix("backend.")) for target in targets
        )
    return sorted(imports)


def _isolated_backend_violations(project_root: Path) -> list[str]:
    runtime = project_root / "backend" / "bootstrap" / "runtime.py"
    library = project_root / "backend" / "services" / "library"
    paths = ([runtime] if runtime.is_file() else []) + sorted(library.rglob("*.py"))
    forbidden = {"main", "bootstrap", "routers", "config", "fastapi", "starlette"}
    violations: list[str] = []
    for path in paths:
        for line, module in _resolved_backend_imports(path, project_root):
            root = module.split(".")[0]
            own_library = module == "services.library" or module.startswith(
                "services.library."
            )
            if path == library / "capture_metadata.py":
                if (
                    not any(
                        module == name or module.startswith(name + ".")
                        for name in {
                            "__future__",
                            "copy",
                            "dataclasses",
                            "typing",
                            "services.meta_store",
                        }
                    )
                    and module != "services"
                ):
                    violations.append(
                        f"{path.relative_to(project_root).as_posix()}:{line}: Library metadata adapter imports {module}"
                    )
                continue
            if root in forbidden or (
                root == "services" and (path == runtime or not own_library)
            ):
                # One diagnostic per import statement even for "from package import module".
                message = f"{path.relative_to(project_root).as_posix()}:{line}: isolated backend module imports {root}"
                if message not in violations:
                    violations.append(message)
    return violations


def _capture_publication_violations(project_root: Path) -> list[str]:
    path = project_root / "backend/services/kindle_catalog/capture_publication.py"
    if not path.is_file():
        return []
    forbidden = {"services.meta_store", "services.meta_db"}
    return sorted(
        {
            f"{path.relative_to(project_root).as_posix()}:{line}: Capture publication must use Library metadata operations"
            for line, module in _resolved_backend_imports(path, project_root)
            if any(
                module == name or module.startswith(name + ".") for name in forbidden
            )
        }
    )


def _novel_module_violations(project_root: Path) -> list[str]:
    allowed_modules = {
        "full_build_content": {"services.novel_db.character_names"},
        "full_build_repository": {"sqlite3", "services.novel_db.full_build_content"},
        "search_ranking": set(),
        "search_presentation": {
            "html",
            "re",
            "urllib.parse",
            "services.novel_db.search_ranking",
        },
        "search_queries": {"sqlite3", "lancedb.table"},
        "ocr_job_application": {
            "utils.logger",
            "services.novel_db.extractor",
            "services.novel_db.ocr_run_store",
        },
    }
    common = {"__future__", "collections", "dataclasses", "typing"}
    violations: set[str] = set()
    for name, dependencies in allowed_modules.items():
        boundary = (
            "Full Build"
            if name.startswith("full_build")
            else "OCR application"
            if name == "ocr_job_application"
            else "Search"
        )
        path = project_root / "backend" / "services" / "novel_db" / f"{name}.py"
        if not path.is_file():
            continue
        for line, module in _resolved_backend_imports(path, project_root):
            if module in {"services", "services.novel_db"}:
                continue
            if any(
                module == allowed or module.startswith(allowed + ".")
                for allowed in common | dependencies
            ):
                continue
            violations.add(
                f"{path.relative_to(project_root).as_posix()}:{line}: {boundary} boundary imports {module}"
            )
    return sorted(violations)


def _frontend_violations(project_root: Path) -> list[str]:
    violations: list[str] = []
    frontend_root = project_root / "frontend" / "src"
    lower_layers = (
        "components",
        "config",
        "contexts",
        "features",
        "hooks",
        "lib",
        "stores",
        "types",
        "utils",
    )
    for layer in lower_layers:
        layer_root = frontend_root / layer
        if not layer_root.exists():
            continue
        for path in sorted(
            candidate
            for candidate in layer_root.rglob("*")
            if candidate.suffix in {".ts", ".tsx"} and candidate.is_file()
        ):
            relative = path.relative_to(project_root)
            for line, module in _frontend_imports(path):
                if _frontend_imports_page(path, module, project_root):
                    violations.append(
                        f"{relative.as_posix()}:{line}: frontend lower layer must not "
                        f"import pages ({module})"
                    )
                if module in FRONTEND_REMOVED_MODULES:
                    violations.append(
                        f"{relative.as_posix()}:{line}: frontend production must not import "
                        f"removed compatibility facade ({module})"
                    )
    return violations


def _reader_session_violations(project_root: Path) -> list[str]:
    """Keep the reviewed route, view lifetime, and lifecycle boundaries narrow."""
    allowed = {
        "pages/ViewerPage.tsx": {"@/features/library"},
        "features/library/LibraryWorkspace.tsx": {
            "@/components/library",
            "@/features/reader",
            "@/features/library/useLibrarySession",
        },
        "features/reader/useReaderLifecycle.ts": {"react"},
    }
    violations: list[str] = []
    for relative, modules in allowed.items():
        path = project_root / "frontend/src" / relative
        if not path.is_file():
            continue
        for line, module in _frontend_imports(path):
            if module not in modules:
                violations.append(
                    f"frontend/src/{relative}:{line}: Library/Reader session boundary imports {module}"
                )
    return violations


def _kindle_violations(project_root: Path) -> list[str]:
    violations: list[str] = []
    kindle_root = project_root / "kindle-pdf"
    if not kindle_root.exists():
        return violations
    for path in sorted(kindle_root.rglob("*.py")):
        relative = path.relative_to(project_root)
        if not _is_kindle_controller_or_capturer(relative):
            continue
        for line, module in _python_imports(path):
            if module.startswith(KINDLE_FORBIDDEN_PREFIXES):
                violations.append(
                    f"{relative.as_posix()}:{line}: Kindle controller/capturer must "
                    f"not import agent/backend layer ({module})"
                )
    return violations


def find_violations(project_root: Path = PROJECT_ROOT) -> list[str]:
    violations = _backend_violations(project_root)
    violations.extend(_backend_script_violations(project_root))
    violations.extend(_isolated_backend_violations(project_root))
    violations.extend(_capture_publication_violations(project_root))
    violations.extend(_novel_module_violations(project_root))
    violations.extend(_frontend_violations(project_root))
    violations.extend(_reader_session_violations(project_root))
    violations.extend(_kindle_violations(project_root))
    return sorted(violations)


def main() -> int:
    violations = find_violations()
    if violations:
        print("Import-boundary check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("Import-boundary check passed: backend, frontend, and Kindle boundaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
