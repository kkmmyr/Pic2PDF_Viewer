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


def _python_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.lineno, node.module))
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


def find_violations(project_root: Path = PROJECT_ROOT) -> list[str]:
    violations: list[str] = []

    services_root = project_root / "backend" / "services"
    if services_root.exists():
        for path in sorted(services_root.rglob("*.py")):
            relative = path.relative_to(project_root)
            for line, module in _python_imports(path):
                if (
                    module == "routers"
                    or module.startswith("routers.")
                    or module == "backend.routers"
                    or module.startswith("backend.routers.")
                ):
                    violations.append(
                        f"{relative.as_posix()}:{line}: backend service must not import "
                        f"routers ({module})"
                    )

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

    kindle_root = project_root / "kindle-pdf"
    if kindle_root.exists():
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
