"""B-20 読書会ディスカッション生成サービス。

Qwen に書籍全文（load_all_pages_of_book 経由）を投入し、2 人のペルソナが
語り合う対話を 1 回の astream_chat で生成する。

ターン境界は `[A]:` / `[B]:` マーカーを逐次検出することで、1 ターン完結
ごとにイベントを yield するリアルタイム SSE を実現している。
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config import (
    KINDLE_NOVEL_DIR,
    NOVEL_DB_LLM_MODEL,
    NOVEL_DB_QA_FULL_BOOK_NUM_CTX,
)
from utils.dt import JST
from utils.logger import get_logger

from .llm import astream_chat as _astream_chat
from .search import SearchHit

logger = get_logger(__name__)

# ディスカッション JSON 保存先
DISCUSSIONS_DIR = Path(KINDLE_NOVEL_DIR) / "discussions"

# 1 トークン ≈ 1.5 日本語文字として推定
_CHARS_PER_TOKEN = 1.5
# 131072 ctx から出力 8192 + プロンプト構造オーバーヘッドを引いた入力上限
MAX_INPUT_TOKENS = 112_000

LLM_OPTIONS: dict[str, Any] = {
    "temperature": 0.7,
    "repeat_penalty": 1.1,
    "num_predict": 8192,
    "num_ctx": NOVEL_DB_QA_FULL_BOOK_NUM_CTX,
}

# ターンマーカー: [A]: または [B]:
_TURN_RE = re.compile(r"\[([AB])\]:")


def _parse_turns_from_text(text: str) -> list[tuple[str, str]]:
    """完全なテキストを `[A]:` / `[B]:` マーカーで分割し (speaker, text) リストを返す。

    ストリーミング時のインクリメンタル解析とは別に、テストや後処理用に提供する。
    """
    parts = _TURN_RE.split(text)
    # parts = [prefix, speaker, text, speaker, text, ...]
    turns = []
    for i in range(1, len(parts) - 1, 2):
        speaker = parts[i]
        turn_text = parts[i + 1] if i + 1 < len(parts) else ""
        stripped = turn_text.strip()
        if stripped:
            turns.append((speaker, stripped))
    return turns


@dataclass
class Persona:
    name: str
    style_description: str


_SYSTEM_TEMPLATE = """あなたは読書会の進行 AI です。以下の小説を読んだ 2 人のキャラクターが読書会で語り合う対話を生成してください。

## 小説タイトル
{book_name}

## 登場キャラクター
- **キャラ A「{name_a}」**: {style_a}
- **キャラ B「{name_b}」**: {style_b}

## 小説本文（全ページ）
{book_text}

## 対話フォーマットのルール
- キャラ A の発言は必ず `[A]:` で始め、キャラ B の発言は必ず `[B]:` で始めてください。
- 各発言は 100〜300 字程度にまとめてください。
- それぞれのキャラクターの口調・視点・スタイルを厳守してください。
- 小説の具体的なシーン・人物・セリフを引用しながら語り合ってください。
- 合計 {num_turns} 往復（A→B を 1 往復）の対話を生成してください。
- `[A]:` または `[B]:` 以外のヘッダーや余分な前置き・後書きは追加しないでください。
"""

_USER_TEMPLATE = "{num_turns} 往復の読書会対話をお願いします。"


def estimate_book_tokens(hits: list[SearchHit]) -> int:
    """書籍全ページの文字数から推定トークン数を返す。"""
    total_chars = sum(len(h.snippet) for h in hits)
    return int(total_chars / _CHARS_PER_TOKEN)


def _format_book_text(hits: list[SearchHit]) -> str:
    lines = [f"[page {h.page_no}]\n{h.snippet}" for h in hits]
    return "\n\n".join(lines)


def build_messages(
    book_name: str,
    persona_a: Persona,
    persona_b: Persona,
    num_turns: int,
    hits: list[SearchHit],
) -> list[dict]:
    """astream_chat に渡す messages リストを組み立てる。"""
    system = _SYSTEM_TEMPLATE.format(
        book_name=book_name,
        name_a=persona_a.name,
        style_a=persona_a.style_description,
        name_b=persona_b.name,
        style_b=persona_b.style_description,
        book_text=_format_book_text(hits),
        num_turns=num_turns,
    )
    user = _USER_TEMPLATE.format(num_turns=num_turns)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def stream_discussion_turns(
    messages: list[dict],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    options: dict | None = None,
) -> AsyncIterator[dict]:
    """読書会ターンを 1 ターンごとに yield する。

    各イベント: {"type": "turn", "speaker": "A"|"B", "text": "..."}

    LLM 出力をトークン単位で受け取りながら `[A]:` / `[B]:` マーカーを検出し、
    1 ターン完了のタイミングで yield する。最後のターンはストリーム終端で yield。
    """
    opts = options or LLM_OPTIONS
    buffer = ""
    current_speaker: str | None = None

    async for event in _astream_chat(messages, model=model, options=opts):
        if event.get("response"):
            buffer += event["response"]

            # ターン境界の検出ループ（1 イベントに複数マーカーが含まれる場合も処理）
            while True:
                m = _TURN_RE.search(buffer)
                if m is None:
                    break
                text_before = buffer[: m.start()]
                if current_speaker is not None and text_before.strip():
                    yield {
                        "type": "turn",
                        "speaker": current_speaker,
                        "text": text_before.strip(),
                    }
                current_speaker = m.group(1)
                buffer = buffer[m.end() :]

        if event.get("done"):
            # 最後のターンをフラッシュ
            if current_speaker is not None and buffer.strip():
                yield {
                    "type": "turn",
                    "speaker": current_speaker,
                    "text": buffer.strip(),
                }
            return


def save_discussion(
    book_name: str,
    persona_a: Persona,
    persona_b: Persona,
    turns: list[dict],
) -> str:
    """ディスカッション結果を JSON 保存し、保存先パス文字列を返す。"""
    book_dir = DISCUSSIONS_DIR / book_name
    book_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(JST).strftime("%Y%m%dT%H%M%SZ")
    out_path = book_dir / f"{ts}.json"
    data = {
        "book": book_name,
        "personas": [
            {"name": persona_a.name, "style_description": persona_a.style_description},
            {"name": persona_b.name, "style_description": persona_b.style_description},
        ],
        "turns": turns,
        "partial": False,
        "created_at": datetime.now(JST).isoformat(),
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out_path)


def count_discussions(book_name: str) -> int:
    """指定書籍のディスカッション数を返す（ファイル数カウントのみ、JSON ロードなし）。"""
    book_dir = DISCUSSIONS_DIR / book_name
    if not book_dir.exists():
        return 0
    return sum(1 for _ in book_dir.glob("*.json"))


def list_discussions(book_name: str) -> list[dict]:
    """指定書籍のディスカッション一覧を新しい順で返す（turns 含む全データ）。"""
    book_dir = DISCUSSIONS_DIR / book_name
    if not book_dir.exists():
        return []
    results = []
    for f in sorted(book_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append(
                {
                    "filename": f.name,
                    "created_at": data.get("created_at"),
                    "personas": data.get("personas", []),
                    "turn_count": len(data.get("turns", [])),
                    "turns": data.get("turns", []),
                }
            )
        except Exception:
            logger.warning("discussion JSON parse failed: %s", f.name, exc_info=True)
    return results
