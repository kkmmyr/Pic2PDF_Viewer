"""OpenAI 互換 /v1/chat/completions の SSE チャンクを Ollama 形式に正規化する。

`LlamaServerBackend`と`MlxBackend`で使用。`OllamaBackend`側は`/api/generate`が元から
Ollama 形式の NDJSON を返すので変換不要。
"""

from __future__ import annotations

from typing import Any


def convert_openai_chunk(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """OpenAI 互換 SSE の 1 チャンクを Ollama 形式 dict に正規化する。

    `stream_options.include_usage=true` を併用するため、`finish_reason` 付きの
    チャンクと末尾の `usage` 専用チャンクが**別々に**届く（合計 2 つの "完了系"
    イベント）。利用側の多くは最初の `done=True` で break するため、

        - 通常トークン: `{"response": "...", "done": False}`
        - finish_reason チャンク: `{"response": <最後のtoken>, "done": False, "_finish": "stop"}`
        - usage チャンク: `{"response": "", "done": True, "done_reason": ..., eval_count: ...}`

    という遅延終了形にする。`done=True` を 1 度だけ・`eval_count` 付きで出すための
    仕掛け。`_finish`は内部マーカー（外には漏れ出ず、OpenAI互換Backendの
    ストリーマで吸収される）。

    返り値:
        通常トークン / finish_reason チャンク / usage チャンクのいずれかの dict。
        空デルタ（role: assistant のみ等）は `None` を返して呼び出し側で skip させる。
    """
    choices = chunk.get("choices") or []
    if not choices:
        # 末尾 usage 専用チャンク
        usage = chunk.get("usage") or {}
        if usage:
            return {
                "response": "",
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": usage.get("prompt_tokens"),
                "eval_count": usage.get("completion_tokens"),
            }
        return None

    choice = choices[0]
    delta = choice.get("delta") or {}
    finish_reason = choice.get("finish_reason")
    text = delta.get("content") or ""

    if finish_reason is not None:
        # この時点では usage は来ていない（include_usage=true なら次チャンクで来る）。
        # done=True を立てない代わりに _finish マーカーをストリーマに渡す。
        return {"response": text, "done": False, "_finish": finish_reason}

    if not text:
        # 最初の role: assistant のみのデルタ等
        return None
    return {"response": text, "done": False}


def fallback_done_event(finish_reason: str) -> dict[str, Any]:
    """include_usage=true でも usage チャンクが届かないまま終端した場合の done フォールバック。

    eval_count / prompt_eval_count は不明扱い (None)。`done_reason` だけは
    finish_reason から復元する。
    """
    return {
        "response": "",
        "done": True,
        "done_reason": finish_reason,
        "prompt_eval_count": None,
        "eval_count": None,
    }
