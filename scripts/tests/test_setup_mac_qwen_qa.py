"""LaunchAgent preparation without invoking launchctl, SSH or MLX."""

import importlib.util
import json
import plistlib
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "setup_mac_qwen_qa", Path(__file__).parents[1] / "setup_mac_qwen_qa.py"
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def completed(args=(), code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, code, stdout, stderr)


@pytest.fixture
def environment(tmp_path, monkeypatch):
    configuration = setup.plan(
        tmp_path / "home with spaces",
        tmp_path / "runtime with spaces",
        "user",
        "server",
    )
    model = Path(configuration["model"])
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}")
    (model / "model.safetensors").write_bytes(b"test")
    executable = Path(configuration["runtime"])
    executable.parent.mkdir(parents=True)
    executable.write_text("not executed")
    original = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda p: (
            str(p)
            in {
                "/usr/bin/caffeinate",
                "/usr/bin/ssh",
                "/bin/launchctl",
                "/usr/sbin/lsof",
                "/bin/ps",
            }
            or original(p)
        ),
    )
    monkeypatch.setattr(setup.os, "access", lambda *args: True)
    monkeypatch.setattr(setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(setup, "_port_open", lambda: False)
    monkeypatch.setattr(setup, "_loaded", lambda label: completed(code=113))
    calls = []

    def fake_run(args):
        calls.append(args)
        return completed(args)

    monkeypatch.setattr(setup, "run", fake_run)
    return configuration, calls


def test_plan_loopback_commands_safe_paths_and_no_embedding_preload(tmp_path):
    p = setup.plan(tmp_path / "home", tmp_path / "a $(touch nope)", "user", "server")
    server, tunnel = [a["plist"] for a in p["agents"]]
    command = server["ProgramArguments"]
    assert command[:2] == ["/usr/bin/caffeinate", "-i"]
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "11437"
    assert command[command.index("--max-num-seqs") + 1] == "1"
    assert "--embedding-model" not in command
    assert "$(touch nope)" in command[2]
    assert tunnel["ProgramArguments"][-3:] == [
        "-R",
        "127.0.0.1:11437:127.0.0.1:11437",
        "user@server",
    ]
    assert not any(
        "StrictHostKeyChecking" in item for item in tunnel["ProgramArguments"]
    )
    assert tunnel["ProgramArguments"][0:2] == ["/usr/bin/ssh", "-NT"]
    assert (
        server["KeepAlive"] and server["RunAtLoad"] and server["ThrottleInterval"] == 30
    )
    assert set(p["linux_settings"]) == {
        "NOVEL_DB_LLM_BACKEND",
        "NOVEL_DB_LLM_MODEL",
        "NOVEL_DB_MLX_BASE_URL",
    }
    assert not (tmp_path / "home").exists()


def test_default_cli_is_json_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["setup", "--home", str(tmp_path), "--runtime-root", str(tmp_path / "missing")],
    )
    monkeypatch.setattr(
        setup, "run", lambda args: pytest.fail("dry-run must not invoke subprocess")
    )
    assert setup.main() == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "dry_run"
    assert list(tmp_path.iterdir()) == []


def test_install_then_same_config_is_idempotent(environment, monkeypatch):
    p, calls = environment
    assert [r["status"] for r in setup.install(p)["results"]] == [
        "bootstrapped",
        "bootstrapped",
    ]
    paths = [Path(a["path"]) for a in p["agents"]]
    for path, agent in zip(paths, p["agents"], strict=True):
        assert plistlib.loads(path.read_bytes()) == agent["plist"]
    prior = [path.stat().st_mtime_ns for path in paths]
    monkeypatch.setattr(
        setup,
        "_loaded",
        lambda label: completed(
            stdout=f"path = {next(a['path'] for a in p['agents'] if a['plist']['Label'] == label)}\npid = 123"
        ),
    )
    calls.clear()
    assert [r["status"] for r in setup.install(p)["results"]] == [
        "already_loaded",
        "already_loaded",
    ]
    assert calls == []
    assert [path.stat().st_mtime_ns for path in paths] == prior


@pytest.mark.parametrize(
    "conflict",
    ["port", "remote", "plist", "unmanaged_label", "missing_model", "non_mac"],
)
def test_preflight_conflicts_make_no_changes(environment, monkeypatch, conflict):
    p, calls = environment
    paths = [Path(a["path"]) for a in p["agents"]]
    if conflict == "port":
        monkeypatch.setattr(setup, "_port_open", lambda: True)
    elif conflict == "remote":
        monkeypatch.setattr(
            setup, "run", lambda args: completed(stdout="LISTEN occupied")
        )
    elif conflict == "plist":
        paths[1].parent.mkdir(parents=True)
        paths[1].write_bytes(
            plistlib.dumps({"Label": setup.TUNNEL, "ProgramArguments": ["other"]})
        )
    elif conflict == "unmanaged_label":
        monkeypatch.setattr(
            setup, "_loaded", lambda label: completed(stdout="pid = 123")
        )
    elif conflict == "missing_model":
        (Path(p["model"]) / "config.json").unlink()
    else:
        monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    with pytest.raises(ValueError):
        setup.install(p)
    assert not paths[0].exists()
    assert not Path(p["logs"]).exists()
    assert not any("bootstrap" in c for c in calls)


def test_owned_listener_checks_process_ancestry(monkeypatch):
    replies = iter([completed(stdout="456\n"), completed(stdout="123\n")])
    monkeypatch.setattr(setup, "run", lambda args: next(replies))
    assert setup._owned_listener(completed(stdout="\tpid = 123\n"))
    assert not setup._owned_listener(completed(code=113))


def test_stop_only_two_labels_retains_files(environment, monkeypatch):
    p, calls = environment
    setup.install(p)
    monkeypatch.setattr(setup, "_loaded", lambda label: completed(stdout="pid = 123"))
    calls.clear()
    result = setup.stop()
    assert [c[-1] for c in calls] == [
        f"gui/{setup.os.getuid()}/{setup.TUNNEL}",
        f"gui/{setup.os.getuid()}/{setup.SERVER}",
    ]
    assert all(c[:2] == ["/bin/launchctl", "bootout"] for c in calls)
    assert result["plist_files"] == "retained"
    assert all(Path(a["path"]).exists() for a in p["agents"])


@pytest.mark.parametrize(
    "user,host",
    [
        ("-option", "server"),
        ("user", "-host"),
        ("a;touch", "server"),
        ("user", "host\ncommand"),
    ],
)
def test_reject_option_or_shell_like_ssh_targets(tmp_path, user, host):
    with pytest.raises(ValueError):
        setup.plan(tmp_path, tmp_path, user, host)


def test_loaded_other_path_refuses_matching_on_disk_plist(environment, monkeypatch):
    p, _ = environment
    setup.install(p)
    monkeypatch.setattr(
        setup,
        "_loaded",
        lambda label: completed(stdout="path = /other/service.plist\npid = 123"),
    )
    with pytest.raises(ValueError, match="another LaunchAgent path"):
        setup.install(p)


def test_incomplete_weight_shards_refused(environment):
    p, _ = environment
    (Path(p["model"]) / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"weight": "missing.safetensors"}})
    )
    with pytest.raises(ValueError, match="shards are incomplete"):
        setup.install(p)


def test_partial_install_reports_progress_and_retry_starts_only_missing(
    environment, monkeypatch, capsys
):
    configuration, calls = environment
    loaded = set()
    failed_once = False
    paths = {a["plist"]["Label"]: a["path"] for a in configuration["agents"]}

    def status(label):
        return (
            completed(stdout=f"path = {paths[label]}\npid = 123")
            if label in loaded
            else completed(code=113)
        )

    def commands(args):
        nonlocal failed_once
        calls.append(args)
        if "bootstrap" in args:
            label = Path(args[-1]).stem
            if label == setup.TUNNEL and not failed_once:
                failed_once = True
                return completed(code=5, stderr="injected bootstrap failure")
            loaded.add(label)
        return completed()

    monkeypatch.setattr(setup, "_loaded", status)
    monkeypatch.setattr(setup, "run", commands)
    monkeypatch.setattr(
        "sys.argv",
        [
            "setup",
            "--install",
            "--home",
            str(Path(configuration["agents"][0]["path"]).parents[2]),
            "--runtime-root",
            str(Path(configuration["runtime"]).parents[2]),
            "--ssh-user",
            "user",
            "--ssh-host",
            "server",
        ],
    )
    assert setup.main() == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["partial_results"] == [
        {"label": setup.SERVER, "status": "bootstrapped"}
    ]
    assert failure["failed_label"] == setup.TUNNEL
    assert failure["plist_files"] == "retained"
    assert loaded == {setup.SERVER}
    modified = [Path(path).stat().st_mtime_ns for path in paths.values()]
    assert setup.main() == 0
    success = json.loads(capsys.readouterr().out)
    assert success["results"] == [
        {"label": setup.SERVER, "status": "already_loaded"},
        {"label": setup.TUNNEL, "status": "bootstrapped"},
    ]
    assert [Path(c[-1]).stem for c in calls if "bootstrap" in c] == [
        setup.SERVER,
        setup.TUNNEL,
        setup.TUNNEL,
    ]
    assert not any("bootout" in c for c in calls)
    assert [Path(path).stat().st_mtime_ns for path in paths.values()] == modified
