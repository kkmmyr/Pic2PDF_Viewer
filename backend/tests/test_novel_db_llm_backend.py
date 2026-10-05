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
                book_name="Book A",
                page_no=5,
                snippet="本文",
                has_highlight=False,
                image_url=None,
                rrf_score=1.0,
                main_characters=["太郎"],
            ),
        ]
        prompt = build_prompt(
            "Q?",
            hits,
            Scope(type="book", id="Book A"),
        )
        # book scope なので [page N, 主要登場人物: ...] になり書名は含まれない
        assert "[page 5" in prompt
        assert "主要登場人物: 太郎" in prompt

    def test_summaries_block_for_all_scope(self):
        from services.novel_db.prompt_builder import build_prompt
        from services.novel_db.search import Scope, SearchHit

        hits = [
            SearchHit(
                book_name="Book A",
                page_no=1,
                snippet="x",
                has_highlight=False,
                image_url=None,
                rrf_score=1.0,
                main_characters=[],
            ),
        ]
        prompt = build_prompt(
            "Q?",
            hits,
            Scope(type="all"),
            book_summaries={"Book A": "あらすじ"},
        )
        assert "【書籍俯瞰サマリ】" in prompt
        assert "■ Book A" in prompt
        assert "あらすじ" in prompt


def test_qa_options_omit_unspecified_presence_and_preserve_defaults(monkeypatch):
    from services.novel_db import llm

    monkeypatch.setattr(llm.novel_db_settings, "NOVEL_DB_QA_REPEAT_PENALTY", 1.2)
    monkeypatch.setattr(llm.novel_db_settings, "NOVEL_DB_QA_PRESENCE_PENALTY", None)
    assert llm._qa_options() == {
        "temperature": 0.2,
        "repeat_penalty": 1.2,
        "num_predict": 4096,
        "num_ctx": llm.NOVEL_DB_QA_NUM_CTX,
    }


@pytest.mark.parametrize("method", ["qa", "chat"])
async def test_explicit_zero_reaches_final_mlx_body_without_affecting_provider_defaults(monkeypatch, method):
    from local_llm import BackendConfig, MlxBackend

    from services.novel_db import llm
    from services.novel_db.llm_provider import _QWEN_MLX_DEFAULT_OPTIONS, NovelLlmProvider

    monkeypatch.setattr(llm.novel_db_settings, "NOVEL_DB_QA_REPEAT_PENALTY", 1.05)
    monkeypatch.setattr(llm.novel_db_settings, "NOVEL_DB_QA_PRESENCE_PENALTY", 0.0)
    options = llm._qa_options()
    monkeypatch.setattr(llm, "LLM_OPTIONS", options)
    backend = MlxBackend(
        BackendConfig(base_url="http://test-mlx", model="model", default_options=_QWEN_MLX_DEFAULT_OPTIONS)
    )
    provider = NovelLlmProvider(qwen=backend, gemma=backend, query=backend, verifier=backend)
    captured = []

    async def fake_http(body, timeout=None):
        captured.append(body)
        yield {"response": "answer", "done": False}
        yield {"response": "", "done": True}

    monkeypatch.setattr(backend, "_stream_body_async", fake_http)
    stream = (
        llm.stream_qa("question", provider=provider)
        if method == "qa"
        else llm.stream_chat([{"role": "user", "content": "question"}], provider=provider)
    )
    events = [event async for event in stream]
    assert events[0]["response"] == "answer"
    assert captured[0]["presence_penalty"] == options["presence_penalty"] == 0.0
    assert captured[0]["repetition_penalty"] == options["repeat_penalty"] == 1.05
    assert captured[0]["temperature"] == options["temperature"] == 0.2
    assert captured[0]["max_tokens"] == options["num_predict"] == 4096
    assert _QWEN_MLX_DEFAULT_OPTIONS["presence_penalty"] == 1.5
    assert _QWEN_MLX_DEFAULT_OPTIONS["repeat_penalty"] == 1.2


async def test_stream_chat_preserves_custom_options(monkeypatch):
    from services.novel_db import llm

    seen = []
    options = {"presence_penalty": 0.0, "repeat_penalty": 1.05}

    async def fake_chat(messages, *, model=None, options=None, timeout=None):
        seen.append(options)
        yield {"response": "", "done": True}

    monkeypatch.setattr(llm, "astream_chat", fake_chat)
    async for _ in llm.stream_chat([{"role": "user", "content": "question"}], options=options):
        pass
    assert seen == [options]
    assert seen[0] is options
