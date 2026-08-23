"""Run one isolated, non-persistent Codex JSON job through ChatGPT authentication."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


def sanitized_environment(source: Mapping[str, str]) -> dict[str, str]:
    environment = dict(source)
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("CODEX_API_KEY", None)
    return environment


def build_command(
    *,
    codex_path: Path,
    work_dir: Path,
    model: str,
    effort: str,
    schema_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        str(codex_path),
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "-C",
        str(work_dir),
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "--json",
        "-",
    ]


def require_chatgpt_login(codex_path: Path, environment: Mapping[str, str]) -> str:
    result = subprocess.run(
        [str(codex_path), "login", "status"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=dict(environment),
    )
    status = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0 or "Logged in using ChatGPT" not in status:
        raise RuntimeError("Codex CLI is not authenticated with ChatGPT; refusing API fallback")
    return "chatgpt"


def append_inline_inputs(
    instructions: str,
    inline_inputs: Sequence[tuple[str, Path]],
    *,
    max_chars: int = 400_000,
) -> str:
    names = [name for name, _ in inline_inputs]
    if any(not name.strip() or "\n" in name for name in names) or len(names) != len(set(names)):
        raise ValueError("inline input names must be non-empty, single-line, and unique")
    sections = [instructions]
    total_chars = 0
    for name, path in inline_inputs:
        content = path.read_text(encoding="utf-8")
        total_chars += len(content)
        if total_chars > max_chars:
            raise ValueError(f"inline inputs exceed {max_chars} characters")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        sections.extend(
            [
                "",
                f'<data-file name={json.dumps(name)} chars="{len(content)}" sha256="{digest}">',
                content,
                "</data-file>",
            ]
        )
    return "\n".join(sections)


def run_job(
    *,
    codex_path: Path,
    work_dir: Path,
    instruction_path: Path,
    schema_path: Path,
    output_path: Path,
    events_path: Path,
    model: str,
    effort: str,
    run_id: str,
    inline_inputs: Sequence[tuple[str, Path]] = (),
) -> dict[str, object]:
    if not run_id.strip():
        raise ValueError("run_id is required")
    for path in (codex_path, work_dir, instruction_path, schema_path):
        if not path.exists():
            raise FileNotFoundError(path)
    if output_path.exists() or events_path.exists():
        raise FileExistsError("Sol output and event paths must be new")
    environment = sanitized_environment(os.environ)
    auth_mode = require_chatgpt_login(codex_path, environment)
    instructions = append_inline_inputs(
        instruction_path.read_text(encoding="utf-8"),
        inline_inputs,
    )
    instructions += f"\n\nFor this invocation, the run ID is exactly `{run_id}`.\n"
    command = build_command(
        codex_path=codex_path,
        work_dir=work_dir,
        model=model,
        effort=effort,
        schema_path=schema_path,
        output_path=output_path,
    )
    with events_path.open("x", encoding="utf-8", newline="\n") as events:
        events_path.chmod(0o600)
        result = subprocess.run(
            command,
            input=instructions,
            stdout=events,
            check=False,
            text=True,
            encoding="utf-8",
            env=environment,
        )
    if output_path.exists():
        output_path.chmod(0o600)
    if result.returncode != 0:
        raise RuntimeError(f"Codex job failed with exit code {result.returncode}; inspect {events_path}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Codex job completed without a final output")
    return {
        "run_id": run_id,
        "auth_mode": auth_mode,
        "model": model,
        "effort": effort,
        "output": str(output_path),
        "events": str(events_path),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--instructions", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", choices=("medium", "high"), default="high")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--inline-file",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Append a UTF-8 data file to stdin once; repeat for multiple files",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inline_inputs: list[tuple[str, Path]] = []
    for value in args.inline_file:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path:
            _parser().error("--inline-file must use NAME=PATH")
        inline_inputs.append((name, Path(raw_path)))
    result = run_job(
        codex_path=args.codex,
        work_dir=args.work_dir,
        instruction_path=args.instructions,
        schema_path=args.schema,
        output_path=args.output,
        events_path=args.events,
        model=args.model,
        effort=args.effort,
        run_id=args.run_id,
        inline_inputs=inline_inputs,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
