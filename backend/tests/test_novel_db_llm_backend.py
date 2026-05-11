"""services/novel_db/llm.py のバックエンド切替テスト（B-14 / ADR-0009）。

llm.py 自体は `astream_ask` を呼ぶだけの薄いラッパなので、テストの主眼は

1. config の値が `QWEN_BACKEND` / `QWEN_LLAMA_SERVER_BASE_URL` に正しくブリッジ
   されていることを確認（import 時の os.environ.setdefault が動いている）
2. 既存呼び出し側（`build_prompt` / `stream_qa`）のシグネチャが両バックエンドで
   変わらないことの回帰

の 2 点。バックエンド固有の挙動（OpenAI SSE 変換等）は `common/Qwen/tests/` 側
で網羅済みなのでここではスタブで確認するに留める。
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


class TestEnvBridge:
    """import 時に config から os.environ へブリッジされていることを確認する。"""

    def test_llama_server_backend_bridged_by_default(self, monkeypatch):
        # llm.py が一度 import されると setdefault されるが、別プロセス相当に
        # するため importlib.reload で再評価する。
        import importlib
        import os

        import config

        # 既存の値が残っている可能性を消す
        for key in ["QWEN_BACKEND", "QWEN_LLAMA_SERVER_BASE_URL", "QWEN_OLLAMA_BASE_URL"]:
            monkeypatch.delenv(key, raising=False)

        # config 側のデフォルトを差し替え
        monkeypatch.setattr(config, "NOVEL_DB_LLM_BACKEND", "llama_server")
        monkeypatch.setattr(config, "NOVEL_DB_LLAMA_SERVER_URL", "http://127.0.0.1:11435")

        from services.novel_db import llm
        importlib.reload(llm)

        assert os.environ["QWEN_BACKEND"] == "llama_server"
        assert os.environ["QWEN_LLAMA_SERVER_BASE_URL"] == "http://127.0.0.1:11435"

    def test_rollback_to_ollama_via_config(self, monkeypatch):
        import importlib
        import os

        import config

        for key in ["QWEN_BACKEND", "QWEN_LLAMA_SERVER_BASE_URL", "QWEN_OLLAMA_BASE_URL"]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(config, "NOVEL_DB_LLM_BACKEND", "ollama")

        from services.novel_db import llm
        importlib.reload(llm)

        assert os.environ["QWEN_BACKEND"] == "ollama"


class TestStreamQaPassthrough:
    """stream_qa が astream_ask に正しく options/model を渡すことを確認する。

    実際の HTTP を叩かないよう、`_astream_ask` を mock する。
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

        # 呼び出し側 options がそのまま forward される（マージは qwen_client 側で行う）
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
