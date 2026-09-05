from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_HELPER = PROJECT_ROOT / "scripts" / "release_archive.sh"
DEPLOY_SCRIPT = PROJECT_ROOT / "scripts" / "deploy_to_linux.sh"
ACTIVATION_SCRIPT = PROJECT_ROOT / "deploy" / "activate-backend.sh"


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")
    _ = path.chmod(0o755)


def _require_bash() -> str:
    candidates = [shutil.which("bash")]
    if program_files := os.environ.get("ProgramFiles"):
        candidates.extend(
            [
                str(Path(program_files) / "Git" / "bin" / "bash.exe"),
                str(Path(program_files) / "Git" / "usr" / "bin" / "bash.exe"),
            ]
        )
    for candidate in dict.fromkeys(path for path in candidates if path):
        try:
            completed = subprocess.run(
                [candidate, "-c", "exit 0"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0:
            return candidate
    pytest.skip("usable bash is unavailable; release shell checks run in Linux CI")


def _path_for_bash(bash: str, path: Path) -> str:
    if os.name != "nt":
        return str(path)
    completed = subprocess.run(
        [bash, "-c", 'cygpath -u "$1"', "path-conversion", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _symlink_or_skip(link: Path, target: Path, *, target_is_directory: bool) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable in this environment: {exc}")


@pytest.mark.parametrize("script", [ARCHIVE_HELPER, DEPLOY_SCRIPT, ACTIVATION_SCRIPT])
def test_release_shell_scripts_have_valid_bash_syntax(script: Path) -> None:
    bash = _require_bash()
    completed = subprocess.run(
        [bash, "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_release_archive_drops_host_metadata(tmp_path: Path) -> None:
    bash = _require_bash()
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)
    regular_file = source / "regular.txt"
    _ = regular_file.write_text("release payload\n", encoding="utf-8")
    _ = (source / "._regular.txt").write_text("appledouble\n", encoding="utf-8")
    _ = (source / ".DS_Store").write_text("finder\n", encoding="utf-8")
    _ = (nested / "kept.txt").write_text("nested payload\n", encoding="utf-8")
    _ = (nested / "._kept.txt").write_text("appledouble\n", encoding="utf-8")
    _ = (nested / ".DS_Store").write_text("finder\n", encoding="utf-8")
    try:
        attribute = "com.pic2pdf.release-test" if sys.platform == "darwin" else "user.pic2pdf.release-test"
        _ = os.setxattr(regular_file, attribute, b"must-not-ship")
    except (AttributeError, OSError):
        pass

    archive = tmp_path / "release.tar.gz"
    completed = subprocess.run(
        [
            bash,
            "-c",
            'source "$1"; create_release_archive -czf "$2" -C "$3" .',
            "release-archive-test",
            _path_for_bash(bash, ARCHIVE_HELPER),
            _path_for_bash(bash, archive),
            _path_for_bash(bash, source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    with tarfile.open(archive) as release:
        members = release.getmembers()
    names = {member.name.removeprefix("./") for member in members}
    assert "regular.txt" in names
    assert "nested/kept.txt" in names
    assert all(not Path(name).name.startswith("._") for name in names)
    assert all(Path(name).name != ".DS_Store" for name in names)
    assert all("xattr" not in key.lower() for member in members for key in member.pax_headers)


def test_release_smoke_checks_stable_lance_path_and_active_icu() -> None:
    script = ACTIVATION_SCRIPT.read_text(encoding="utf-8")

    assert "LanceDB path is scoped to a backend release" in script
    assert 'config.NOVEL_DB_LEXICAL_BACKEND in {"shadow", "lance_icu"}' in script
    assert "search_page_fts(" in script
    assert "page ICU no-match smoke unexpectedly returned a row" in script


def test_deploy_restarts_installed_codex_coordination_user_service() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "systemctl --user cat codex-coordination-mcp.service" in script
    assert "systemctl --user restart codex-coordination-mcp.service" in script
    assert "systemctl --user is-active --quiet codex-coordination-mcp.service" in script


def test_activation_allows_reviewed_ocr_migration_and_verifies_columns() -> None:
    script = ACTIVATION_SCRIPT.read_text(encoding="utf-8")

    assert "0015_ocr_candidate_selection_reason.py | 0016_ocr_provenance_and_timing.py" in script
    assert "migration is not approved for backward-compatible rollout" in script
    assert 'required_run_columns = {"runtime_manifest_json", "timing_json"' in script
    assert '"candidate_manifest_json",' in script
    assert "ocr_page_results migration columns are missing" in script


def test_activation_rejects_appledouble_before_systemd_or_writes(tmp_path: Path) -> None:
    bash = _require_bash()
    app_root = tmp_path / "app"
    previous_backend = app_root / "backend-previous"
    next_backend = app_root / "backend-next"
    next_common = app_root / "common" / "llm-next"
    workspace = app_root / ".deploy-workspace-next"
    for path in (previous_backend, next_backend, next_common, workspace / "common"):
        path.mkdir(parents=True)

    for path in (
        app_root / "pyproject.toml",
        app_root / "uv.lock",
        next_backend / "pyproject.toml",
        next_common / "pyproject.toml",
        workspace / "pyproject.toml",
        workspace / "uv.lock",
    ):
        _ = path.write_text("fixture\n", encoding="utf-8")
    _ = (next_backend / "._0012_fixture.py").write_text("appledouble\n", encoding="utf-8")
    _symlink_or_skip(workspace / "backend", next_backend, target_is_directory=True)
    _symlink_or_skip(workspace / "common" / "llm", next_common, target_is_directory=True)
    _symlink_or_skip(app_root / "backend", previous_backend, target_is_directory=True)

    active_python = previous_backend / ".venv" / "bin" / "python"
    fake_uv = tmp_path / "fake-uv"
    fake_python = tmp_path / "fake-python"
    for executable in (active_python, fake_uv, fake_python):
        _write_executable(executable, "#!/bin/sh\nexit 99\n")

    marker = tmp_path / "systemctl-called"
    fake_bin = tmp_path / "bin"
    _write_executable(
        fake_bin / "systemctl",
        '#!/bin/sh\n: > "$PIC2PDF_TEST_SYSTEMCTL_MARKER"\nexit 99\n',
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "PIC2PDF_APP_ROOT": _path_for_bash(bash, app_root),
            "PIC2PDF_UV_BIN": _path_for_bash(bash, fake_uv),
            "PIC2PDF_PYTHON_BIN": _path_for_bash(bash, fake_python),
            "PIC2PDF_SERVICE_NAME": "pic2pdf-test",
            "PIC2PDF_TEST_SYSTEMCTL_MARKER": _path_for_bash(bash, marker),
        }
    )
    completed = subprocess.run(
        [
            bash,
            _path_for_bash(bash, ACTIVATION_SCRIPT),
            "release-test",
            _path_for_bash(bash, next_backend),
            _path_for_bash(bash, next_common),
            _path_for_bash(bash, workspace),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert completed.returncode != 0
    assert "AppleDouble metadata is not allowed in staged release" in completed.stderr
    assert not marker.exists()
    assert (app_root / "backend").resolve() == previous_backend.resolve()
