"""qa_history テーブルの読み書き。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §4 / API §7.5-7.7。
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import Any

from .search import Scope, SearchHit


def save_start(
    conn: sqlite3.Connection,
    *,
    scope: Scope,
    question: str,
    prompt: str,
    hits: list[SearchHit],
    model: str,
    options: dict[str, Any],
) -> int:
    """質問送信時に履歴行を作成し、id を返す。answer / finished_at は後で更新。"""
    cur = conn.execute(
        "INSERT INTO qa_history (scope_type, scope_id, question, answer, prompt, "
        "context_json, model, options_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            scope.type,
            scope.id,
            question,
            "",  # 生成完了時に上書き
            prompt,
            json.dumps([asdict(h) for h in hits], ensure_ascii=False),
            model,
            json.dumps(options),
        ),
    )
    conn.commit()
    return cur.lastrowid


def save_finish(
    conn: sqlite3.Connection,
    history_id: int,
    *,
    answer: str,
    done_reason: str,
    eval_count: int | None,
) -> None:
    conn.execute(
        "UPDATE qa_history SET answer = ?, finished_at = datetime('now'), "
        "done_reason = ?, eval_count = ? WHERE id = ?",
        (answer, done_reason, eval_count, history_id),
    )
    conn.commit()


def save_error(conn: sqlite3.Connection, history_id: int, error: str) -> None:
    conn.execute(
        "UPDATE qa_history SET error_message = ?, finished_at = datetime('now'), "
        "done_reason = 'error' WHERE id = ?",
        (error, history_id),
    )
    conn.commit()


def list_history(
    conn: sqlite3.Connection, offset: int = 0, limit: int = 20, book: str | None = None
) -> dict:
    """[API §7.5] 一覧（要約）。book 指定時はその書籍への質問のみ返す。"""
    if book is not None:
        rows = conn.execute(
            "SELECT id, asked_at, finished_at, scope_type, scope_id, question, answer, "
            "done_reason FROM qa_history "
            "WHERE scope_type='book' AND scope_id=? "
            "ORDER BY asked_at DESC, id DESC LIMIT ? OFFSET ?",
            (book, limit, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM qa_history WHERE scope_type='book' AND scope_id=?",
            (book,),
        ).fetchone()[0]
    else:
        rows = conn.execute(
            "SELECT id, asked_at, finished_at, scope_type, scope_id, question, answer, "
            "done_reason FROM qa_history "
            "ORDER BY asked_at DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM qa_history").fetchone()[0]

    items = []
    for row in rows:
        (id_, asked_at, finished_at, scope_type, scope_id, question, answer, done_reason) = row
        preview = (answer or "")[:120]
        if len(answer or "") > 120:
            preview += "…"
        items.append({
            "id": id_,
            "asked_at": asked_at,
            "finished_at": finished_at,
            "scope": {"type": scope_type, "id": scope_id},
            "question": question,
            "answer_preview": preview,
            "done_reason": done_reason,
        })
    return {"items": items, "total": total}


def get_history_detail(conn: sqlite3.Connection, history_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, asked_at, finished_at, scope_type, scope_id, question, answer, "
        "prompt, context_json, model, options_json, eval_count, done_reason, "
        "error_message FROM qa_history WHERE id = ?",
        (history_id,),
    ).fetchone()
    if row is None:
        return None
    (
        id_, asked_at, finished_at, scope_type, scope_id, question, answer,
        prompt, context_json, model, options_json, eval_count, done_reason,
        error_message,
    ) = row
    return {
        "id": id_,
        "asked_at": asked_at,
        "finished_at": finished_at,
        "scope": {"type": scope_type, "id": scope_id},
        "question": question,
        "answer": answer,
        "prompt": prompt,
        "context": json.loads(context_json),
        "model": model,
        "options": json.loads(options_json),
        "eval_count": eval_count,
        "done_reason": done_reason,
        "error_message": error_message,
    }


def delete_history(conn: sqlite3.Connection, history_id: int) -> bool:
    cur = conn.execute("DELETE FROM qa_history WHERE id = ?", (history_id,))
    conn.commit()
    return cur.rowcount > 0
