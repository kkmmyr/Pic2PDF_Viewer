from __future__ import annotations

import os
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


@pytest.mark.parametrize("script", [ARCHIVE_HELPER, DEPLOY_SCRIPT, ACTIVATION_SCRIPT])
def test_release_shell_scripts_have_valid_bash_syntax(script: Path) -> None:
    completed = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_release_archive_drops_host_metadata(tmp_path: Path) -> None:
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
            "bash",
            "-c",
            'source "$1"; create_release_archive -czf "$2" -C "$3" .',
            "release-archive-test",
            str(ARCHIVE_HELPER),
            str(archive),
            str(source),
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


def test_activation_rejects_appledouble_before_systemd_or_writes(tmp_path: Path) -> None:
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
    _ = (workspace / "backend").symlink_to(next_backend, target_is_directory=True)
    _ = (workspace / "common" / "llm").symlink_to(next_common, target_is_directory=True)
    _ = (app_root / "backend").symlink_to(previous_backend, target_is_directory=True)

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
            "PIC2PDF_APP_ROOT": str(app_root),
            "PIC2PDF_UV_BIN": str(fake_uv),
            "PIC2PDF_PYTHON_BIN": str(fake_python),
            "PIC2PDF_SERVICE_NAME": "pic2pdf-test",
            "PIC2PDF_TEST_SYSTEMCTL_MARKER": str(marker),
        }
    )
    completed = subprocess.run(
        [
            "bash",
            str(ACTIVATION_SCRIPT),
            "release-test",
            str(next_backend),
            str(next_common),
            str(workspace),
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
