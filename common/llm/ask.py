#!/usr/bin/env python3
"""ask.py - Qwen3.6:35b-a3b へのシンプルな CLI ツール。

Gemma 4 の ask.py に対応する Qwen 版。Qwen は thinking モデルで応答が遅い
（1 問 ~120 秒）ため、用途は複雑な分析・長文検証・推論などに絞られる。
日常的な質問は Gemma 4 の ask.py を優先すること。

使い方:
  python ask.py "質問やタスクをここに書く"
  python ask.py -f code.py "このコードをレビューして"
  python ask.py --think "難しい論理パズル"     # thinking 過程も表示
  python ask.py --session                       # 会話履歴を引き継ぐセッション
  echo "長い文章" | python ask.py "論点を整理して"
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 共通 LLM パッケージ (local_llm) を import 可能にする
_PKG_PARENT = str(Path(__file__).parent)
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from local_llm import LLMError, backend_from_env  # noqa: E402
from local_llm.logger import log_interaction  # noqa: E402

# 環境変数 (QWEN_BACKEND / QWEN_OLLAMA_BASE_URL / ...) から Backend を 1 つ作る
_BACKEND = backend_from_env()


# ---------------------------------------------------------------------------
# ストリーミング呼び出し
# ---------------------------------------------------------------------------

def _stream_and_print(
    prompt: str,
    *,
    system: str | None,
    model: str | None,
    think: bool,
    context: list[int] | None,
    print_output: bool,
    source: str,
) -> tuple[str, list[int] | None]:
    """Qwen にストリーミングで問い合わせ、(response 全文, 新 context) を返す。

    `think=True` のときは thinking チャンクを `[Thinking] ` プレフィックス付きで
    流し、response チャンクに切り替わった時点で空行を挟む（Gemma 4 と同じ流儀）。
    """
    started = time.monotonic()
    response_parts: list[str] = []
    new_context: list[int] | None = None
    state = "start"  # "start" | "thinking" | "response"

    try:
        for event in _BACKEND.stream_ask(
            prompt, system=system, model=model, think=think, context=context,
        ):
            think_token = event.get("thinking", "")
            resp_token = event.get("response", "")
            if think_token:
                if state != "thinking" and print_output:
                    print("[Thinking] ", end="", flush=True)
                state = "thinking"
                if print_output:
                    print(think_token, end="", flush=True)
            if resp_token:
                if state == "thinking" and print_output:
                    print("\n\n", end="", flush=True)
                state = "response"
                response_parts.append(resp_token)
                if print_output:
                    print(resp_token, end="", flush=True)
            if event.get("done"):
                new_context = event.get("context")
                break
    except LLMError as e:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_interaction(source, prompt, f"[ERROR] {e}", elapsed_ms)
        print(f"\nエラー: Qwen 呼び出しに失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    full_response = "".join(response_parts)
    log_interaction(source, prompt, full_response, elapsed_ms)
    return full_response, new_context


# ---------------------------------------------------------------------------
# モード別エントリポイント
# ---------------------------------------------------------------------------

def ask_once(
    prompt: str,
    *,
    system: str | None,
    model: str | None,
    think: bool,
) -> None:
    _stream_and_print(
        prompt,
        system=system, model=model, think=think, context=None,
        print_output=True, source="cli",
    )
    print()


def ask_session(
    *,
    system: str | None,
    model: str | None,
    think: bool,
) -> None:
    print("セッション開始（終了: exit / quit / 終了 / Ctrl+C）\n", file=sys.stderr)
    context: list[int] | None = None
    while True:
        try:
            user_input = input("あなた: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nセッション終了", file=sys.stderr)
            break
        if user_input.lower() in ("exit", "quit", "終了"):
            print("セッション終了", file=sys.stderr)
            break
        if not user_input:
            continue
        print("Qwen: ", end="", flush=True)
        _, context = _stream_and_print(
            user_input,
            system=system, model=model, think=think, context=context,
            print_output=True, source="cli_session",
        )
        print()


# ---------------------------------------------------------------------------
# プロンプト構築
# ---------------------------------------------------------------------------

def build_prompt(
    user_prompt: str,
    file_path: str | None,
    stdin_text: str | None,
) -> str:
    parts: list[str] = []
    if file_path:
        try:
            with open(file_path, encoding="utf-8") as f:
                parts.append(f"=== ファイル: {file_path} ===\n{f.read()}\n")
        except FileNotFoundError:
            print(f"エラー: ファイルが見つかりません: {file_path}", file=sys.stderr)
            sys.exit(1)
    if stdin_text:
        parts.append(f"=== 入力テキスト ===\n{stdin_text}\n")
    parts.append(user_prompt)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# argparse エントリポイント
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen3.6:35b-a3b CLI ツール")
    parser.add_argument("prompt", nargs="?", help="質問またはタスク")
    parser.add_argument("-f", "--file", metavar="FILE", help="コンテキストとして読み込むファイル")
    parser.add_argument("-m", "--model", default=None, help="使用するモデル (デフォルト: $QWEN_MODEL または qwen3.6:35b-a3b)")
    parser.add_argument("--system", metavar="TEXT", help="システムプロンプト（役割設定など）")
    parser.add_argument("--think", action="store_true", help="thinking 過程も表示する（Qwen のデフォルトは think=False）")
    parser.add_argument("--session", action="store_true", help="会話履歴を引き継ぐセッションモードで起動")
    args = parser.parse_args()

    if args.session:
        ask_session(system=args.system, model=args.model, think=args.think)
        return

    stdin_text = None if sys.stdin.isatty() else sys.stdin.read().strip()

    if not args.prompt and not stdin_text:
        parser.print_help()
        sys.exit(1)

    full_prompt = build_prompt(args.prompt or "", args.file, stdin_text)
    ask_once(full_prompt, system=args.system, model=args.model, think=args.think)


if __name__ == "__main__":
    main()
