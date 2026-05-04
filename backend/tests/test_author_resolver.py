"""
services.author_resolver のユニットテスト。

実行方法:
    cd backend
    uv run pytest tests/test_author_resolver.py -v
"""
import json
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import services.author_resolver as ar


class TestSanitizeAuthor:
    def test_normal_name_preserved(self):
        assert ar._sanitize_author("サークル名") == "サークル名"

    def test_strips_whitespace(self):
        assert ar._sanitize_author("  サークル名  ") == "サークル名"

    def test_empty_string_returns_unknown(self):
        assert ar._sanitize_author("") == "作者不明"

    def test_none_string_returns_unknown(self):
        assert ar._sanitize_author("None") == "作者不明"

    def test_url_rejected(self):
        assert ar._sanitize_author("https://dlsite.com") == "作者不明"
        assert ar._sanitize_author("http://example.com/circle") == "作者不明"

    def test_dlsite_brand_rejected(self):
        assert ar._sanitize_author("DLsite exclusive") == "作者不明"

    def test_dmm_brand_rejected(self):
        assert ar._sanitize_author("DMM合同会社") == "作者不明"

    def test_fanza_brand_rejected(self):
        assert ar._sanitize_author("FANZA同人") == "作者不明"

    def test_too_long_rejected(self):
        assert ar._sanitize_author("a" * 81) == "作者不明"

    def test_exactly_max_length_preserved(self):
        name = "あ" * ar._MAX_AUTHOR_LEN
        assert ar._sanitize_author(name) == name

    def test_json_fragment_rejected(self):
        assert ar._sanitize_author('{"result": "サークル"}') == "作者不明"

    def test_int_input_does_not_crash(self):
        # Gemma が稀に数値型を返した場合に AttributeError で落ちないことを保証
        result = ar._sanitize_author(123)
        assert isinstance(result, str)

    def test_none_input_returns_unknown(self):
        assert ar._sanitize_author(None) == "作者不明"

    def test_no_result_phrase_rejected(self):
        assert ar._sanitize_author("条件に一致する作品は見つかりませんでした") == "作者不明"
        assert ar._sanitize_author("該当する作品が見つかりません") == "作者不明"

    def test_pure_numeric_rejected(self):
        # Gemma が「該当なし」の sentinel として "-1" や "0" を返すケース
        assert ar._sanitize_author("-1") == "作者不明"
        assert ar._sanitize_author("0") == "作者不明"
        assert ar._sanitize_author("123") == "作者不明"
        assert ar._sanitize_author("3.14") == "作者不明"


class TestExtractCircleFromPage:
    """_extract_circle_from_page のテスト（call_ollama をモック）。"""

    def _make_ollama(self, response: dict | None):
        """call_ollama のモック。response=None で空文字列を返す。"""
        def _mock(prompt, response_format=None, source=""):
            if response is None:
                return ""
            return json.dumps(response)
        return _mock

    def test_extracts_result_field(self):
        mock = self._make_ollama({"result": "テストサークル"})
        assert ar._extract_circle_from_page("ページ内容", "タイトル", mock) == "テストサークル"

    def test_empty_dict_returns_empty(self):
        mock = self._make_ollama({})
        assert ar._extract_circle_from_page("ページ内容", "タイトル", mock) == ""

    def test_ollama_error_returns_empty(self):
        def error_ollama(prompt, response_format=None, source=""):
            return "[エラー] タイムアウト"
        assert ar._extract_circle_from_page("ページ内容", "タイトル", error_ollama) == ""

    def test_empty_page_text_returns_empty(self):
        mock = self._make_ollama({"result": "サークル"})
        assert ar._extract_circle_from_page("", "タイトル", mock) == ""

    def test_ollama_returns_empty_string_returns_empty(self):
        mock = self._make_ollama(None)
        assert ar._extract_circle_from_page("ページ内容", "タイトル", mock) == ""


class TestTryDlsite:
    """_try_dlsite のテスト（fetch_url と call_ollama をモック）。"""

    def test_success_returns_circle_name(self):
        def fetch(url, max_chars=4000):
            return "検索結果: 作品タイトル | サークル名: テストサークル | DLsite"
        def ollama(prompt, response_format=None, source=""):
            return json.dumps({"result": "テストサークル"})
        assert ar._try_dlsite("作品タイトル", fetch, ollama) == "テストサークル"

    def test_fetch_failure_returns_empty(self):
        def fetch(url, max_chars=4000):
            return ""
        def ollama(prompt, response_format=None, source=""):
            return json.dumps({"result": "サークル"})
        assert ar._try_dlsite("タイトル", fetch, ollama) == ""

    def test_brand_name_in_result_returns_empty(self):
        def fetch(url, max_chars=4000):
            return "DLsite検索結果"
        def ollama(prompt, response_format=None, source=""):
            return json.dumps({"result": "DLsite公式"})
        assert ar._try_dlsite("タイトル", fetch, ollama) == ""

    def test_url_contains_encoded_title(self):
        captured_url = []
        def fetch(url, max_chars=4000):
            captured_url.append(url)
            return ""
        ar._try_dlsite("テストタイトル", fetch, lambda *a, **k: "")
        assert "dlsite.com" in captured_url[0]
        assert "%E3%83%86%E3%82%B9%E3%83%88" in captured_url[0]  # "テスト" の URL エンコード


class TestTryFanza:
    """_try_fanza のテスト（fetch_url と call_ollama をモック）。"""

    def test_success_returns_circle_name(self):
        def fetch(url, max_chars=4000):
            return "検索結果: 作品名 / サークル: 銀河サークル"
        def ollama(prompt, response_format=None, source=""):
            return json.dumps({"result": "銀河サークル"})
        assert ar._try_fanza("作品名", fetch, ollama) == "銀河サークル"

    def test_fetch_failure_returns_empty(self):
        assert ar._try_fanza("タイトル", lambda u, **k: "", lambda *a, **k: "") == ""

    def test_url_contains_dmm_domain(self):
        captured_url = []
        def fetch(url, max_chars=4000):
            captured_url.append(url)
            return ""
        ar._try_fanza("テスト", fetch, lambda *a, **k: "")
        assert "dmm.co.jp" in captured_url[0]


class TestResolveAuthorFallbackOrder:
    """resolve_author のフォールバック優先順位テスト（import_web_extract_tools をモック）。"""

    def _patch_tools(self, monkeypatch, dlsite_result="", fanza_result="", direct_result="", generic_result="作者不明"):
        """各ステップの返り値を設定して import_web_extract_tools をモックする。"""
        def fake_web_extract(query, extract_target, **kwargs):
            if "site:" in query:
                return direct_result
            return generic_result

        def fake_fetch(url, max_chars=4000):
            return "ページテキスト" if url else ""

        def fake_ollama(prompt, response_format=None, source=""):
            if "dlsite" in prompt.lower() or ("ページ" in prompt and dlsite_result):
                return json.dumps({"result": dlsite_result}) if dlsite_result else "{}"
            return json.dumps({"result": fanza_result}) if fanza_result else "{}"

        monkeypatch.setattr(ar, "import_web_extract_tools", lambda: (fake_web_extract, None, fake_fetch, fake_ollama))
        monkeypatch.setattr(ar, "_try_dlsite", lambda title, f, c: dlsite_result)
        monkeypatch.setattr(ar, "_try_fanza", lambda title, f, c: fanza_result)
        monkeypatch.setattr(ar, "_try_direct_sites", lambda title, w: direct_result)

    def test_dlsite_wins_when_successful(self, monkeypatch):
        self._patch_tools(monkeypatch, dlsite_result="DLサークル", fanza_result="FANZAサークル")
        assert ar.resolve_author("タイトル", "generated") == "DLサークル"

    def test_fanza_used_when_dlsite_fails(self, monkeypatch):
        self._patch_tools(monkeypatch, dlsite_result="", fanza_result="FANZAサークル")
        assert ar.resolve_author("タイトル", "generated") == "FANZAサークル"

    def test_direct_sites_used_when_both_fail(self, monkeypatch):
        self._patch_tools(monkeypatch, dlsite_result="", fanza_result="", direct_result="直接サークル")
        assert ar.resolve_author("タイトル", "generated") == "直接サークル"

    def test_generic_fallback_when_all_direct_fail(self, monkeypatch):
        def fake_web_extract(query, extract_target, **kwargs):
            return "汎用サークル"
        monkeypatch.setattr(ar, "import_web_extract_tools", lambda: (fake_web_extract, None, lambda u, **k: "", lambda *a, **k: "{}"))
        monkeypatch.setattr(ar, "_try_dlsite", lambda *a: "")
        monkeypatch.setattr(ar, "_try_fanza", lambda *a: "")
        monkeypatch.setattr(ar, "_try_direct_sites", lambda *a: "")
        assert ar.resolve_author("タイトル", "generated") == "汎用サークル"

    def test_kindle_skips_direct_steps(self, monkeypatch):
        """kindle ソースは DLsite/FANZA を試みず汎用クエリのみ使う。"""
        dlsite_called = []
        monkeypatch.setattr(ar, "_try_dlsite", lambda *a: dlsite_called.append(1) or "")
        monkeypatch.setattr(ar, "_try_fanza", lambda *a: dlsite_called.append(1) or "")

        def fake_web_extract(query, extract_target, **kwargs):
            return "漫画著者"
        monkeypatch.setattr(ar, "import_web_extract_tools", lambda: (fake_web_extract, None, None, None))

        result = ar.resolve_author("タイトル", "kindle")
        assert result == "漫画著者"
        assert len(dlsite_called) == 0

    def test_tools_unavailable_returns_unknown(self, monkeypatch):
        monkeypatch.setattr(ar, "import_web_extract_tools", lambda: (None, None, None, None))
        assert ar.resolve_author("タイトル", "generated") == "作者不明"
