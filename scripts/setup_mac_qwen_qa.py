#!/usr/bin/env python3
"""Prepare or install two user LaunchAgents for loopback Qwen QA transport."""

from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import re
import socket
import subprocess
from pathlib import Path

SERVER = "local.pic2pdf.qwen-qa"
TUNNEL = "local.pic2pdf.qwen-qa-tunnel"
PORT = 11437


class PartialInstallError(RuntimeError):
    """Report retained progress so the operator can resume only missing agents."""

    def __init__(self, message: str, results: list[dict], failed_label: str):
        super().__init__(message)
        self.partial_results = list(results)
        self.failed_label = failed_label


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True, timeout=30)


def plan(home: Path, runtime_root: Path, user: str, host: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", user) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9.-]*", host
    ):
        raise ValueError("invalid SSH user or host")
    home, runtime_root = (
        home.expanduser().resolve(),
        runtime_root.expanduser().resolve(),
    )
    model = runtime_root / "models/qwen3.6-35b-a3b-4bit"
    runtime = runtime_root / ".venv/bin/mlx_vlm.server"
    logs = runtime_root / "qa-service/logs"
    arguments = {
        SERVER: [
            "/usr/bin/caffeinate",
            "-i",
            str(runtime),
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--model",
            str(model),
            "--max-num-seqs",
            "1",
        ],
        TUNNEL: [
            "/usr/bin/ssh",
            "-NT",
            "-o",
            "BatchMode=yes",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "ControlMaster=no",
            "-o",
            "ControlPath=none",
            "-R",
            f"127.0.0.1:{PORT}:127.0.0.1:{PORT}",
            f"{user}@{host}",
        ],
    }
    agents = []
    for label, args in arguments.items():
        agents.append(
            {
                "path": str(home / "Library/LaunchAgents" / f"{label}.plist"),
                "plist": {
                    "Label": label,
                    "ProgramArguments": args,
                    "RunAtLoad": True,
                    "KeepAlive": True,
                    "ThrottleInterval": 30,
                    "WorkingDirectory": str(runtime_root),
                    "StandardOutPath": str(logs / f"{label}.out.log"),
                    "StandardErrorPath": str(logs / f"{label}.err.log"),
                },
            }
        )
    return {
        "agents": agents,
        "logs": str(logs),
        "runtime": str(runtime),
        "model": str(model),
        "linux_settings": {
            "NOVEL_DB_LLM_BACKEND": "mlx",
            "NOVEL_DB_MLX_BASE_URL": f"http://127.0.0.1:{PORT}",
            "NOVEL_DB_LLM_MODEL": str(model),
        },
    }


def _loaded(label: str) -> subprocess.CompletedProcess[str]:
    return run(["/bin/launchctl", "print", f"gui/{os.getuid()}/{label}"])


def _port_open() -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def _owned_listener(service: subprocess.CompletedProcess[str]) -> bool:
    match = re.search(r"\bpid = (\d+)", service.stdout)
    if service.returncode != 0 or not match:
        return False
    parent = int(match[1])
    listeners = run(["/usr/sbin/lsof", "-nP", f"-iTCP:{PORT}", "-sTCP:LISTEN", "-t"])
    pids = listeners.stdout.split()
    if listeners.returncode or not pids:
        return False
    for value in pids:
        if not value.isdigit():
            return False
        pid = int(value)
        for _ in range(10):
            if pid == parent:
                break
            ancestor = run(["/bin/ps", "-o", "ppid=", "-p", str(pid)])
            if ancestor.returncode or not ancestor.stdout.strip().isdigit():
                return False
            pid = int(ancestor.stdout.strip())
        else:
            return False
    return True


def _check_configuration(
    configuration: dict,
) -> dict[str, subprocess.CompletedProcess[str]]:
    if platform.system() != "Darwin":
        raise ValueError("installation requires macOS")
    for executable in (
        configuration["runtime"],
        "/usr/bin/caffeinate",
        "/usr/bin/ssh",
        "/bin/launchctl",
        "/usr/sbin/lsof",
        "/bin/ps",
    ):
        if not Path(executable).is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f"required executable unavailable: {executable}")
    model = Path(configuration["model"])
    if not (model / "config.json").is_file() or not list(model.glob("*.safetensors")):
        raise ValueError(f"model files unavailable: {model}")
    index = model / "model.safetensors.index.json"
    if index.exists():
        shards = set(json.loads(index.read_text())["weight_map"].values())
        if not shards or any(
            not (model / shard).resolve().is_relative_to(model.resolve())
            or not (model / shard).is_file()
            for shard in shards
        ):
            raise ValueError("model weight shards are incomplete")
    loaded = {}
    for agent in configuration["agents"]:
        path = Path(agent["path"])
        if path.is_symlink():
            raise ValueError(f"refusing a symlink LaunchAgent: {path}")
        if path.exists() and plistlib.loads(path.read_bytes()) != agent["plist"]:
            raise ValueError(f"existing LaunchAgent configuration differs: {path}")
        status = _loaded(agent["plist"]["Label"])
        if status.returncode == 0 and not path.exists():
            raise ValueError("existing loaded label has no matching managed plist")
        if status.returncode == 0:
            origin = re.search(r"^\s*path = (.+)$", status.stdout, re.MULTILINE)
            if not origin or Path(origin[1]).resolve() != path.resolve():
                raise ValueError("loaded label belongs to another LaunchAgent path")
        loaded[agent["plist"]["Label"]] = status
    if _port_open() and not _owned_listener(loaded[SERVER]):
        raise ValueError(f"local port {PORT} belongs to another service")
    if loaded[TUNNEL].returncode:
        ssh = configuration["agents"][1]["plist"]["ProgramArguments"]
        target = ssh[-1]
        remote = run(
            [
                "/usr/bin/ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ControlMaster=no",
                "-o",
                "ControlPath=none",
                target,
                f"ss -H -ltn 'sport = :{PORT}'",
            ]
        )
        if remote.returncode:
            raise ValueError(
                f"SSH authentication or remote port check failed: {remote.stderr.strip()}"
            )
        if remote.stdout.strip():
            raise ValueError(f"remote port {PORT} already occupied")
    return loaded


def install(configuration: dict) -> dict:
    loaded = _check_configuration(configuration)
    Path(configuration["logs"]).mkdir(parents=True, exist_ok=True)
    results = []
    for agent in configuration["agents"]:
        path = Path(agent["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("xb") as handle:
                handle.write(plistlib.dumps(agent["plist"]))
            path.chmod(0o600)
        label = agent["plist"]["Label"]
        if loaded[label].returncode == 0:
            results.append({"label": label, "status": "already_loaded"})
            continue
        try:
            result = run(
                ["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)]
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PartialInstallError(
                f"bootstrap interrupted for {label}; installed files retained: {error}",
                results,
                label,
            ) from error
        if result.returncode:
            raise PartialInstallError(
                f"bootstrap failed for {label}; installed files retained: {result.stderr.strip()}",
                results,
                label,
            )
        results.append({"label": label, "status": "bootstrapped"})
    return {"mode": "install", **configuration, "results": results}


def stop() -> dict:
    if platform.system() != "Darwin":
        raise ValueError("stop requires macOS")
    results = []
    for label in (TUNNEL, SERVER):
        if _loaded(label).returncode:
            results.append({"label": label, "status": "not_loaded"})
            continue
        result = run(["/bin/launchctl", "bootout", f"gui/{os.getuid()}/{label}"])
        if result.returncode:
            raise RuntimeError(f"bootout failed for {label}: {result.stderr.strip()}")
        results.append({"label": label, "status": "stopped"})
    return {"mode": "stop", "results": results, "plist_files": "retained"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--install", action="store_true")
    modes.add_argument("--stop", action="store_true")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument(
        "--runtime-root", type=Path, default=Path.home() / ".local/share/pic2pdf-mlx"
    )
    parser.add_argument("--ssh-user", default="amashio")
    parser.add_argument("--ssh-host", default="medaroserver")
    args = parser.parse_args()
    try:
        configuration = plan(args.home, args.runtime_root, args.ssh_user, args.ssh_host)
        result = (
            stop()
            if args.stop
            else install(configuration)
            if args.install
            else {"mode": "dry_run", **configuration}
        )
    except (
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        failure = {"error": str(error)}
        if isinstance(error, PartialInstallError):
            failure.update(
                mode="install",
                partial_results=error.partial_results,
                failed_label=error.failed_label,
                plist_files="retained",
            )
        print(json.dumps(failure, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
