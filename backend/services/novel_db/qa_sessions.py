"""B-16 マルチターン会話 QA: セッション + メッセージの CRUD。

`qa_sessions` 1 行に対し `qa_messages` が複数並ぶ。scope はセッション開始時に
固定（途中変更不可）。LLM 呼び出しは別レイヤ（`llm.stream_chat_session`）が
本ファイルの読み書きを介して履歴を構築する。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §7.x / B-16。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .search import Scope


@dataclass(frozen=True)
class SessionMeta:
    """セッション一覧用の軽量情報（messages は含まない）。"""
    id: int
    scope_type: str
    scope_id: str | None
    title: str | None
    started_at: str
    last_message_at: str | None
    message_count: int


@dataclass(frozen=True)
class ChatMessage:
    """qa_messages の 1 行。assistant のときのみ eval_count / done_reason が入る。"""
    id: int
    role: str        # 'user' / 'assistant' / 'system'
    content: str
    eval_count: int | None
    done_reason: str | None
    created_at: str


@dataclass(frozen=True)
class SessionDetail:
    """セッション詳細（メッセージ全件含む）。"""
    id: int
    scope_type: str
    scope_id: str | None
    title: str | None
    started_at: str
    last_message_at: str | None
    messages: list[ChatMessage]


# ---------------------------------------------------------------------------
# 書き込み
# ---------------------------------------------------------------------------

def create_session(
    conn: sqlite3.Connection,
    scope: Scope,
    *,
    title: str | None = None,
) -> int:
    """新しいセッションを作成し、id を返す。

    `title` は呼び出し側が「初手質問の先頭 30 字」等で生成して渡す想定
    （`None` のままでもよく、UI は時刻で代替表示する）。
    """
    cur = conn.execute(
        """
        INSERT INTO qa_sessions (scope_type, scope_id, title)
        VALUES (?, ?, ?)
        """,
        (scope.type, scope.id, title),
    )
    conn.commit()
    return cur.lastrowid


def append_message(
    conn: sqlite3.Connection,
    session_id: int,
    *,
    role: str,
    content: str,
    eval_count: int | None = None,
    done_reason: str | None = None,
) -> int:
    """セッションに 1 メッセージを追記し、id を返す。

    `last_message_at` も同時に更新する（同一トランザクション）。
    """
    cur = conn.execute(
        """
        INSERT INTO qa_messages (session_id, role, content, eval_count, done_reason)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, role, content, eval_count, done_reason),
    )
    conn.execute(
        "UPDATE qa_sessions SET last_message_at = datetime('now') WHERE id = ?",
        (session_id,),
    )
    conn.commit()
    return cur.lastrowid


def update_session_title(
    conn: sqlite3.Connection,
    session_id: int,
    title: str,
) -> None:
    """セッションタイトルを更新する（初手質問から自動生成 / 手動編集の両用途）。"""
    conn.execute(
        "UPDATE qa_sessions SET title = ? WHERE id = ?",
        (title, session_id),
    )
    conn.commit()


def delete_session(conn: sqlite3.Connection, session_id: int) -> bool:
    """セッションを削除する（CASCADE で qa_messages も消える）。

    Returns: True なら削除した、False なら該当 id なし。
    """
    cur = conn.execute("DELETE FROM qa_sessions WHERE id = ?", (session_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# 読み出し
# ---------------------------------------------------------------------------

def list_sessions(
    conn: sqlite3.Connection,
    *,
    offset: int = 0,
    limit: int = 20,
    scope_type: str | None = None,
    scope_id: str | None = None,
) -> list[SessionMeta]:
    """セッション一覧。`last_message_at` 降順（活動順）→ `started_at` 降順。

    scope_type を指定すると scope_type + scope_id の完全一致で絞り込む。
    scope_type='all' のときは scope_id が NULL のセッションを対象とする。
    """
    where_parts: list[str] = []
    params: list = []
    if scope_type is not None:
        where_parts.append("s.scope_type = ?")
        params.append(scope_type)
        if scope_id is not None:
            where_parts.append("s.scope_id = ?")
            params.append(scope_id)
        else:
            where_parts.append("s.scope_id IS NULL")

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    rows = conn.execute(
        f"""
        SELECT s.id, s.scope_type, s.scope_id, s.title, s.started_at,
               s.last_message_at,
               (SELECT COUNT(*) FROM qa_messages m WHERE m.session_id = s.id)
                  AS message_count
        FROM qa_sessions s
        {where_sql}
        ORDER BY COALESCE(s.last_message_at, s.started_at) DESC, s.id DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()
    return [
        SessionMeta(
            id=r[0], scope_type=r[1], scope_id=r[2], title=r[3],
            started_at=r[4], last_message_at=r[5], message_count=r[6],
        )
        for r in rows
    ]


def get_session_meta(
    conn: sqlite3.Connection, session_id: int,
) -> SessionMeta | None:
    row = conn.execute(
        """
        SELECT s.id, s.scope_type, s.scope_id, s.title, s.started_at,
               s.last_message_at,
               (SELECT COUNT(*) FROM qa_messages m WHERE m.session_id = s.id)
                  AS message_count
        FROM qa_sessions s
        WHERE s.id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return SessionMeta(
        id=row[0], scope_type=row[1], scope_id=row[2], title=row[3],
        started_at=row[4], last_message_at=row[5], message_count=row[6],
    )


def get_session_detail(
    conn: sqlite3.Connection, session_id: int,
) -> SessionDetail | None:
    """1 セッション + 全メッセージ。未存在なら None。"""
    meta = get_session_meta(conn, session_id)
    if meta is None:
        return None
    rows = conn.execute(
        """
        SELECT id, role, content, eval_count, done_reason, created_at
        FROM qa_messages
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    ).fetchall()
    messages = [
        ChatMessage(
            id=r[0], role=r[1], content=r[2],
            eval_count=r[3], done_reason=r[4], created_at=r[5],
        )
        for r in rows
    ]
    return SessionDetail(
        id=meta.id, scope_type=meta.scope_type, scope_id=meta.scope_id,
        title=meta.title, started_at=meta.started_at,
        last_message_at=meta.last_message_at, messages=messages,
    )


def load_chat_messages(
    conn: sqlite3.Connection, session_id: int,
) -> list[dict[str, str]]:
    """LLM 投入用に OpenAI Chat 形式 `[{role, content}, ...]` を返す。

    `qa_messages` を id 昇順で全部取って `{role, content}` だけに整形する。
    """
    rows = conn.execute(
        """
        SELECT role, content FROM qa_messages
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    ).fetchall()
    return [{"role": role, "content": content} for role, content in rows]
