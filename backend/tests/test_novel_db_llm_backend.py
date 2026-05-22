"""services/novel_db/llm.py の委譲テスト。

Phase 74 で `_llm_backend.py` を廃止。Backend は各サービスファイル内で直接
インライン構築されるため、テストは `_astream_ask` / `astream_chat` の
monkeypatch と `build_prompt` 安定性確認に絞る。
"""
from __future__ import annotations

import pytest


class TestStreamQaPassthrough:
    """`stream_qa` が `_astream_ask` 経由で options/model を正しく渡すことを確認。

    実際の HTTP を叩かないよう `llm._astream_ask` を mock する
    （Backend 実体の動作は common/llm/tests/ で網羅）。
    """

    @pytest.mark.asyncio
    async def test_stream_qa_uses_default_options_and_model(self, monkeypatch):
        from services.novel_db import llm

        captured: dict = {}

        async def fake_astream_ask(prompt, *, model=None, options=None, timeout=None):
            captured["prompt"] = prompt
            captured["model"] = model
            captured["options"] = options
            captured["timeout"] = timeout
            yield {"response": "ok", "done": False}
            yield {"response": "", "done": True, "eval_count": 2}

        monkeypatch.setattr(llm, "_astream_ask", fake_astream_ask)

        events = []
        async for event in llm.stream_qa("question?"):
            events.append(event)

        assert captured["prompt"] == "question?"
        assert captured["model"] == llm.NOVEL_DB_LLM_MODEL
        # デフォルト options（LLM_OPTIONS）が渡されている
        assert captured["options"]["temperature"] == 0.2
        assert captured["options"]["num_ctx"] == llm.NOVEL_DB_QA_NUM_CTX
        assert events[0]["response"] == "ok"
        assert events[-1]["done"] is True

    @pytest.mark.asyncio
    async def test_stream_qa_accepts_custom_options(self, monkeypatch):
        from services.novel_db import llm

        captured: dict = {}

        async def fake_astream_ask(prompt, *, model=None, options=None, timeout=None):
            captured["options"] = options
            yield {"response": "", "done": True}

        monkeypatch.setattr(llm, "_astream_ask", fake_astream_ask)

        async for _ in llm.stream_qa("q", options={"temperature": 0.9}):
            pass

        # 呼び出し側 options がそのまま forward される（マージは Backend 側で行う）
        assert captured["options"] == {"temperature": 0.9}


class TestBuildPromptStability:
    """B-14 で build_prompt のシグネチャ・出力が変わっていないことの回帰確認。"""

    def test_book_scope_omits_book_name_in_header(self):
        from services.novel_db.prompt_builder import build_prompt
        from services.novel_db.search import Scope, SearchHit

        hits = [
            SearchHit(
                book_name="Book A", page_no=5, snippet="本文",
                has_highlight=False, image_url=None, rrf_score=1.0,
                main_characters=["太郎"],
            ),
        ]
        prompt = build_prompt(
            "Q?", hits, Scope(type="book", id="Book A"),
        )
        # book scope なので [page N, 主要登場人物: ...] になり書名は含まれない
        assert "[page 5" in prompt
        assert "主要登場人物: 太郎" in prompt

    def test_summaries_block_for_all_scope(self):
        from services.novel_db.prompt_builder import build_prompt
        from services.novel_db.search import Scope, SearchHit

        hits = [
            SearchHit(
                book_name="Book A", page_no=1, snippet="x",
                has_highlight=False, image_url=None, rrf_score=1.0,
                main_characters=[],
            ),
        ]
        prompt = build_prompt(
            "Q?", hits, Scope(type="all"),
            book_summaries={"Book A": "あらすじ"},
        )
        assert "【書籍俯瞰サマリ】" in prompt
        assert "■ Book A" in prompt
        assert "あらすじ" in prompt
