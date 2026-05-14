"""routers/novel_db.py の検索 / QA / 履歴エンドポイントの HTTP テスト。

LLM (stream_qa) と embedder (embed_batch) はモックする。
"""
import json

import pytest

from services.novel_db import init_schema, with_db
from services.novel_db.embedder import serialize_f32


def _stub_embed(texts):
    return [[0.1] + [0.0] * 1023 for _ in texts]


@pytest.fixture
def search_setup(tmp_data_dir, monkeypatch):
    """検索可能な小さな DB を作って embed_batch をスタブする。

    NOVEL_DB_BODY_PAGE_MARGIN=5 でフィルタされても本文ページが残るよう、
    page_count=15 で先頭 5 / 末尾 5 を除いた中央 5 ページに本文を配置する。
    """
    with with_db() as conn:
        init_schema(conn)
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("book-1", "/dummy/book-1.pdf", "/dummy/images/book-1", 15),
        )
        book_id = cur.lastrowid
        body_text_a = "デュークはレティの新しい騎士である。" * 20  # 約 360 字
        body_text_b = "アストリッドは元暗殺者だった。デュークの後輩。" * 18  # 約 360 字
        filler = "あ" * 320  # クエリと無関係な本文相当（min_chars 通過、検索ヒットしない）

        for i in range(1, 16):
            if i == 7:
                text = body_text_a
            elif i == 8:
                text = body_text_b
            else:
                text = filler
            cur = conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (book_id, i, None, text, len(text)),
            )
            page_id = cur.lastrowid
            cur = conn.execute(
                "INSERT INTO chunks (page_id, chunk_idx, text, char_count) "
                "VALUES (?, ?, ?, ?)",
                (page_id, 0, text, len(text)),
            )
            chunk_id = cur.lastrowid
            conn.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                (chunk_id, serialize_f32([0.1] + [0.0] * 1023)),
            )
        conn.execute(
            "INSERT INTO pages_fts (rowid, full_text) "
            "SELECT id, full_text FROM pages WHERE book_id = ?",
            (book_id,),
        )
        conn.commit()

    from services.novel_db import search as search_mod
    monkeypatch.setattr(search_mod, "embed_batch", _stub_embed)


# ---------------------------------------------------------------------------
# 検索
# ---------------------------------------------------------------------------

def test_post_search_returns_hits(client, search_setup):
    res = client.post(
        "/api/novel_db/search",
        json={"query": "デューク", "scope": {"type": "all"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert any("デューク" in (h["snippet"] or "") for h in body["hits"]) or \
        any("<mark>" in h["snippet"] for h in body["hits"])
    # 各 hit の構造
    h = body["hits"][0]
    assert {"book_name", "page_no", "snippet", "has_highlight", "image_url", "rrf_score"} <= set(h)


def test_post_search_pagination_offset_limit(client, search_setup):
    res1 = client.post(
        "/api/novel_db/search",
        json={"query": "デューク", "scope": {"type": "all"}, "offset": 0, "limit": 1},
    )
    body1 = res1.json()
    assert body1["limit"] == 1
    assert len(body1["hits"]) <= 1


def test_post_search_validation_empty_query(client, search_setup):
    res = client.post(
        "/api/novel_db/search",
        json={"query": "", "scope": {"type": "all"}},
    )
    assert res.status_code == 422


def test_post_search_validation_oversized_query(client, search_setup):
    res = client.post(
        "/api/novel_db/search",
        json={"query": "あ" * 201, "scope": {"type": "all"}},
    )
    assert res.status_code == 422


def test_post_search_returns_503_when_rebuild_running(client, search_setup, monkeypatch):
    from services.novel_db.job_queue import job_queue
    monkeypatch.setattr(job_queue, "_is_running", True, raising=False)
    res = client.post(
        "/api/novel_db/search",
        json={"query": "デューク", "scope": {"type": "all"}},
    )
    assert res.status_code == 503
    assert res.headers.get("Retry-After") == "10"


# ---------------------------------------------------------------------------
# QA (SSE)
# ---------------------------------------------------------------------------

async def _stub_stream_qa_ok(prompt, **kwargs):
    """3 token + done のストリームをシミュレート。"""
    yield {"response": "デューク"}
    yield {"response": "は"}
    yield {"response": "騎士"}
    yield {"done": True, "done_reason": "stop", "eval_count": 100}


async def _stub_stream_qa_raises(prompt, **kwargs):
    if False:
        yield {}  # async generator にするための yield
    raise RuntimeError("simulated upstream error")


def test_post_qa_streams_tokens_and_saves_history(client, search_setup, monkeypatch):
    from routers.novel_db import qa as router_mod
    monkeypatch.setattr(router_mod, "stream_qa", _stub_stream_qa_ok)

    with client.stream(
        "POST",
        "/api/novel_db/qa",
        json={"question": "デュークはどんな人物?", "scope": {"type": "all"}},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events: list[dict] = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    # token イベント + done イベント
    tokens = [e for e in events if "token" in e]
    dones = [e for e in events if e.get("done")]
    assert len(tokens) == 3
    assert len(dones) == 1
    assert dones[0]["done_reason"] == "stop"
    assert dones[0]["eval_count"] == 100
    history_id = dones[0]["history_id"]

    # 履歴に保存されている
    detail = client.get(f"/api/novel_db/qa/history/{history_id}").json()
    assert detail["answer"] == "デュークは騎士"
    assert detail["done_reason"] == "stop"


def test_post_qa_validation_empty_question(client, search_setup):
    res = client.post(
        "/api/novel_db/qa",
        json={"question": "", "scope": {"type": "all"}},
    )
    assert res.status_code == 422


def test_post_qa_validation_oversized_question(client, search_setup):
    res = client.post(
        "/api/novel_db/qa",
        json={"question": "あ" * 501, "scope": {"type": "all"}},
    )
    assert res.status_code == 422


def test_post_qa_returns_503_when_rebuild_running(client, search_setup, monkeypatch):
    from services.novel_db.job_queue import job_queue
    monkeypatch.setattr(job_queue, "_is_running", True, raising=False)
    res = client.post(
        "/api/novel_db/qa",
        json={"question": "Q", "scope": {"type": "all"}},
    )
    assert res.status_code == 503


# ---------------------------------------------------------------------------
# 履歴
# ---------------------------------------------------------------------------

def test_get_qa_history_empty_initially(client, search_setup):
    res = client.get("/api/novel_db/qa/history")
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_get_qa_history_after_qa_call(client, search_setup, monkeypatch):
    from routers.novel_db import qa as router_mod
    monkeypatch.setattr(router_mod, "stream_qa", _stub_stream_qa_ok)

    with client.stream(
        "POST",
        "/api/novel_db/qa",
        json={"question": "Q1", "scope": {"type": "all"}},
    ) as resp:
        # 全イベントを消化する
        for _ in resp.iter_lines():
            pass

    res = client.get("/api/novel_db/qa/history")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["question"] == "Q1"
    assert body["items"][0]["done_reason"] == "stop"


def test_get_qa_history_detail_returns_404(client, search_setup):
    res = client.get("/api/novel_db/qa/history/99999")
    assert res.status_code == 404


def test_delete_qa_history_returns_204(client, search_setup, monkeypatch):
    from routers.novel_db import qa as router_mod
    monkeypatch.setattr(router_mod, "stream_qa", _stub_stream_qa_ok)

    # 1 件作る
    with client.stream(
        "POST", "/api/novel_db/qa",
        json={"question": "Q", "scope": {"type": "all"}},
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                if event.get("done"):
                    history_id = event["history_id"]

    res = client.delete(f"/api/novel_db/qa/history/{history_id}")
    assert res.status_code == 204

    # 削除後は 404
    assert client.get(f"/api/novel_db/qa/history/{history_id}").status_code == 404


def test_delete_qa_history_returns_404_for_missing(client, search_setup):
    res = client.delete("/api/novel_db/qa/history/99999")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 履歴 book フィルタ (§7.5 book パラメータ)
# ---------------------------------------------------------------------------

def _make_qa(client, monkeypatch, question: str, scope: dict) -> int:
    """QA を 1 件作成して history_id を返すヘルパー。"""
    from routers.novel_db import qa as router_mod
    monkeypatch.setattr(router_mod, "stream_qa", _stub_stream_qa_ok)
    history_id = None
    with client.stream("POST", "/api/novel_db/qa", json={"question": question, "scope": scope}) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev.get("done"):
                    history_id = ev["history_id"]
    return history_id


def test_get_qa_history_book_filter_returns_only_matching(client, search_setup, monkeypatch):
    """book パラメータを指定すると、その書籍への質問のみ返る。"""
    _make_qa(client, monkeypatch, "Q-book1", {"type": "book", "id": "book-1"})
    _make_qa(client, monkeypatch, "Q-all", {"type": "all"})

    res = client.get("/api/novel_db/qa/history", params={"book": "book-1"})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["question"] == "Q-book1"


def test_get_qa_history_book_filter_empty_when_no_match(client, search_setup, monkeypatch):
    """一致する書籍への質問がない場合は空リストを返す。"""
    _make_qa(client, monkeypatch, "Q-all", {"type": "all"})

    res = client.get("/api/novel_db/qa/history", params={"book": "nonexistent-book"})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_get_qa_history_without_book_filter_returns_all(client, search_setup, monkeypatch):
    """book パラメータなしの場合は全件返す（既存動作に変更なし）。"""
    _make_qa(client, monkeypatch, "Q-book1", {"type": "book", "id": "book-1"})
    _make_qa(client, monkeypatch, "Q-all", {"type": "all"})

    res = client.get("/api/novel_db/qa/history")
    assert res.status_code == 200
    assert res.json()["total"] == 2
