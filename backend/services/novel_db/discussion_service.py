"""B-28 読書会ロングフォーム生成サービス（B-20 を置き換え）。

固定ホストキャラ 2 人（discussion_cast）による番組台本を 2 段の LLM 呼び出しで生成する:
①構成ステップ（generate_plan: 対立する主張・テーマ・脱線ネタカードを JSON で取得）
②台本ステップ（stream_discussion_turns: セグメント境界マーカー付き台本を SSE ストリーミング）

ターン境界は `[A]:` / `[B]:`（表記揺れ許容）、セグメント境界は `[S:segment_id]` を
逐次検出することで、1 ターン完結ごとにイベントを yield するリアルタイム SSE を実現している。
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
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

# 構成ステップ用: JSON 出力なので温度を下げ、出力上限も台本より小さくてよい
PLAN_LLM_OPTIONS: dict[str, Any] = {
    "temperature": 0.4,
    "repeat_penalty": 1.1,
    "num_predict": 2048,
    "num_ctx": NOVEL_DB_QA_FULL_BOOK_NUM_CTX,
}

# 保存ファイル名のバリデーション（delete 用）
_FILENAME_RE = re.compile(r"^[\w+\-]+\.json$")

# ターンマーカー: [A]: の表記揺れ（[A>: / [A]： / [A): 等）を許容する寛容パーサ
_TURN_RE = re.compile(r"\[([AB])[\]\>）\)]?\s*[:：]")

# セグメントマーカー: [S:segment_id]（閉じ括弧の揺れ・欠落を許容）
_SEG_RE = re.compile(r"\[S[:：]\s*([a-z0-9_]+)\s*[\]\>]?")


def _parse_turns_from_text(text: str) -> list[tuple[str, str]]:
    """完全なテキストを `[A]:` / `[B]:` マーカーで分割し (speaker, text) リストを返す。

    セグメントマーカー `[S:...]` は除去する。
    ストリーミング時のインクリメンタル解析とは別に、テストや後処理用に提供する。
    """
    cleaned = _SEG_RE.sub("", text)
    parts = _TURN_RE.split(cleaned)
    # parts = [prefix, speaker, text, speaker, text, ...]
    turns = []
    for i in range(1, len(parts) - 1, 2):
        speaker = parts[i]
        turn_text = parts[i + 1] if i + 1 < len(parts) else ""
        stripped = turn_text.strip()
        if stripped:
            turns.append((speaker, stripped))
    return turns


def estimate_book_tokens(hits: list[SearchHit]) -> int:
    """書籍全ページの文字数から推定トークン数を返す。"""
    total_chars = sum(len(h.snippet) for h in hits)
    return int(total_chars / _CHARS_PER_TOKEN)


def format_book_text(hits: list[SearchHit]) -> str:
    """書籍全ページをプロンプト差し込み用の 1 文字列に整形する。"""
    lines = [f"[page {h.page_no}]\n{h.snippet}" for h in hits]
    return "\n\n".join(lines)


def _extract_json_object(text: str) -> dict:
    """LLM 出力からコードフェンス・前置きを取り除いて JSON オブジェクトを抽出する。"""
    cleaned = re.sub(r"```(?:json)?", "", text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("構成メモの JSON が見つかりません")
    return json.loads(cleaned[start : end + 1])


def _validate_plan(plan: dict) -> None:
    themes = plan.get("themes")
    if not isinstance(themes, list) or len(themes) != 2:
        raise ValueError("構成メモの themes は 2 件必要です")
    for theme in themes:
        if not isinstance(theme, dict) or not theme.get("title") or not theme.get("question"):
            raise ValueError("構成メモの themes に title / question がありません")
    stances = plan.get("stances")
    if not isinstance(stances, dict) or not stances.get("a") or not stances.get("b"):
        raise ValueError("構成メモの stances に a / b がありません")
    cards = plan.get("cards")
    if not isinstance(cards, list) or len(cards) < 1:
        raise ValueError("構成メモの cards は 1 件以上必要です")


async def generate_plan(
    messages: list[dict],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    options: dict | None = None,
) -> dict:
    """構成ステップ（Call 1）を実行し、バリデーション済み構成メモ dict を返す。

    JSON 抽出・パース・バリデーション失敗時は ValueError
    （呼び出し側で SSE error に変換する）。
    """
    opts = options or PLAN_LLM_OPTIONS
    chunks: list[str] = []
    async for event in _astream_chat(messages, model=model, options=opts):
        if event.get("response"):
            chunks.append(event["response"])
        if event.get("done"):
            break
    full_text = "".join(chunks)
    try:
        plan = _extract_json_object(full_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"構成メモの JSON パースに失敗しました: {e}") from e
    _validate_plan(plan)
    return plan


async def stream_discussion_turns(
    messages: list[dict],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    options: dict | None = None,
) -> AsyncIterator[dict]:
    """台本ステップ（Call 2）のイベントを逐次 yield する。

    - {"type": "segment", "id": "<segment_id>"} — セグメント境界検出時
    - {"type": "turn", "speaker": "A"|"B", "text": "...", "segment": <現在のセグメントID|None>}

    LLM 出力をトークン単位で受け取りながらターン / セグメントマーカーを検出し、
    1 ターン完了のタイミングで yield する。最後のターンはストリーム終端で yield。
    セグメントマーカーは turn text に含めない。
    """
    opts = options or LLM_OPTIONS
    buffer = ""
    current_speaker: str | None = None
    current_segment: str | None = None

    def _flush_turn(text: str) -> dict | None:
        stripped = text.strip()
        if current_speaker is None or not stripped:
            return None
        return {
            "type": "turn",
            "speaker": current_speaker,
            "text": stripped,
            "segment": current_segment,
        }

    def _drain(at_end: bool):
        """buffer からマーカーを検出できる限りイベントを取り出す（1 イベント複数マーカー対応）。"""
        nonlocal buffer, current_speaker, current_segment
        while True:
            turn_m = _TURN_RE.search(buffer)
            seg_m = _SEG_RE.search(buffer)
            if turn_m is None and seg_m is None:
                return
            # 先に出現した方を処理する
            if seg_m is not None and (turn_m is None or seg_m.start() < turn_m.start()):
                # 閉じ括弧が省略可能なため、マッチが buffer 終端に達していて閉じ括弧を
                # 消費していない場合はセグメント ID が途中の可能性がある → 次チャンクを待つ
                if not at_end and seg_m.end() == len(buffer) and buffer[-1] not in "]>":
                    return
                turn = _flush_turn(buffer[: seg_m.start()])
                if turn:
                    yield turn
                current_speaker = None
                current_segment = seg_m.group(1)
                yield {"type": "segment", "id": current_segment}
                buffer = buffer[seg_m.end() :]
            else:
                assert turn_m is not None
                turn = _flush_turn(buffer[: turn_m.start()])
                if turn:
                    yield turn
                current_speaker = turn_m.group(1)
                buffer = buffer[turn_m.end() :]

    async for event in _astream_chat(messages, model=model, options=opts):
        if event.get("response"):
            buffer += event["response"]
            for ev in _drain(at_end=False):
                yield ev

        if event.get("done"):
            for ev in _drain(at_end=True):
                yield ev
            # 最後のターンをフラッシュ
            turn = _flush_turn(buffer)
            if turn:
                yield turn
            return


def save_discussion(
    book_name: str,
    cast_snapshot: list[dict],
    segments: list[dict],
    cards: list[dict],
    turns: list[dict],
    checks: dict,
) -> str:
    """ディスカッション結果を format_version 2 の JSON で保存し、保存先パス文字列を返す。

    ファイル名は JST タイムスタンプ + UTC オフセット（例: 20260707T123456+0900.json）。
    """
    book_dir = DISCUSSIONS_DIR / book_name
    book_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(JST).strftime("%Y%m%dT%H%M%S%z")
    out_path = book_dir / f"{ts}.json"
    data = {
        "format_version": 2,
        "book": book_name,
        "cast": cast_snapshot,
        "segments": segments,
        "cards": cards,
        "turns": turns,
        "checks": checks,
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
    """指定書籍のディスカッション一覧を新しい順で返す（turns 含む全データ）。

    v1（format_version なし・自由ペルソナ）と v2（固定キャスト + segments + checks）の
    両形式を読める。v2 では personas をキャストから合成する（name + stance）。
    """
    book_dir = DISCUSSIONS_DIR / book_name
    if not book_dir.exists():
        return []
    results = []
    for f in sorted(book_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            version = data.get("format_version", 1)
            if version >= 2:
                personas = [
                    {"name": c.get("name", ""), "style_description": c.get("stance", "")} for c in data.get("cast", [])
                ]
            else:
                personas = data.get("personas", [])
            results.append(
                {
                    "filename": f.name,
                    "created_at": data.get("created_at"),
                    "personas": personas,
                    "turn_count": len(data.get("turns", [])),
                    "turns": data.get("turns", []),
                    "format_version": version,
                    "segments": data.get("segments"),
                    "checks": data.get("checks"),
                }
            )
        except Exception:
            logger.warning("discussion JSON parse failed: %s", f.name, exc_info=True)
    return results


def delete_discussion(book_name: str, filename: str) -> bool:
    """指定ディスカッション JSON を削除する。

    filename 不正・パストラバーサルは ValueError。
    ファイルが存在しなければ False、削除成功で True。
    """
    if not _FILENAME_RE.match(filename):
        raise ValueError(f"不正なファイル名です: {filename}")
    target = (DISCUSSIONS_DIR / book_name / filename).resolve()
    if not target.is_relative_to(DISCUSSIONS_DIR.resolve()):
        raise ValueError(f"不正なパスです: {book_name}/{filename}")
    if not target.exists():
        return False
    target.unlink()
    return True
