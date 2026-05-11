"""services/novel_db/llm.py + _llm_backend.py のバックエンド構築 / 委譲テスト。

A-3（local_llm 移行）以降は env var bridge ではなく `BackendConfig` を引数渡し
する設計。テストの主眼は

1. `_llm_backend.build_qwen_backend()` が `config.NOVEL_DB_LLM_BACKEND` に応じて
   `LlamaServerBackend` / `OllamaBackend` を返すこと
2. 既存呼び出し側（`build_prompt` / `stream_qa`）のシグネチャが両バックエンドで
   変わらないことの回帰

の 2 点。バックエンド固有の挙動（OpenAI SSE 変換等）は `common/llm/tests/` 側
で網羅済みなのでここではスタブで確認するに留める。
"""
from __future__ import annotations

import pytest
from local_llm import LlamaServerBackend, LLMError, OllamaBackend

import config
from services.novel_db import _llm_backend


class TestBuildQwenBackend:
    """`_llm_backend.build_qwen_backend()` が config に従って正しい Backend を返す。"""

    def test_llama_server_backend_by_default(self, monkeypatch):
        monkeypatch.setattr(config, "NOVEL_DB_LLM_BACKEND", "llama_server")
        monkeypatch.setattr(config, "NOVEL_DB_LLAMA_SERVER_URL", "http://test:11435")
        monkeypatch.setattr(config, "NOVEL_DB_LLM_MODEL", "qwen3.6-iq4xs")

        backend = _llm_backend.build_qwen_backend()
        assert isinstance(backend, LlamaServerBackend)
        assert backend.config.base_url == "http://test:11435"
        assert backend.config.model == "qwen3.6-iq4xs"

    def test_rollback_to_ollama_via_config(self, monkeypatch):
        monkeypatch.setattr(config, "NOVEL_DB_LLM_BACKEND", "ollama")
        monkeypatch.setattr(config, "NOVEL_DB_OLLAMA_BASE_URL", "http://test:11434")

        backend = _llm_backend.build_qwen_backend()
        assert isinstance(backend, OllamaBackend)
        assert backend.config.base_url == "http://test:11434"

    def test_unknown_backend_raises(self, monkeypatch):
        monkeypatch.setattr(config, "NOVEL_DB_LLM_BACKEND", "vllm")

        with pytest.raises(LLMError, match="unknown NOVEL_DB_LLM_BACKEND"):
            _llm_backend.build_qwen_backend()


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
        from services.novel_db.llm import build_prompt
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
        from services.novel_db.llm import build_prompt
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
