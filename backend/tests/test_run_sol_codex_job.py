"""Tests for the isolated Codex subscription job launcher."""

from pathlib import Path

import pytest

from scripts.run_sol_codex_job import append_inline_inputs, build_command, sanitized_environment


def test_sanitized_environment_removes_api_credentials() -> None:
    result = sanitized_environment({"PATH": "/bin", "OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret-2"})
    assert result == {"PATH": "/bin"}


def test_build_command_is_ephemeral_read_only_and_ignores_local_policy(tmp_path: Path) -> None:
    command = build_command(
        codex_path=Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
        work_dir=tmp_path,
        model="gpt-5.6-sol",
        effort="high",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
    )
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("-m") + 1] == "gpt-5.6-sol"
    assert 'model_reasoning_effort="high"' in command


def test_append_inline_inputs_embeds_each_file_once_with_digest(tmp_path: Path) -> None:
    source = tmp_path / "pages.jsonl"
    source.write_text("本文\n", encoding="utf-8")

    prompt = append_inline_inputs("instructions", [("pages.jsonl", source)])

    assert prompt.count("本文") == 1
    assert 'name="pages.jsonl"' in prompt
    assert "sha256=" in prompt


def test_append_inline_inputs_rejects_duplicate_names_and_overflow(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("12345", encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        append_inline_inputs("", [("same", source), ("same", source)])
    with pytest.raises(ValueError, match="exceed"):
        append_inline_inputs("", [("input", source)], max_chars=4)
