"""
author_resolver.py — タイトルからサークル名を推定するサービス。

generated ソースの検索フロー:
  1. DLsite 直接検索 (dlsite.com/maniax を HTTP フェッチ)
  2. FANZA 直接検索 (dmm.co.jp/dc/doujin を HTTP フェッチ)
  3. SearXNG site: フィルタ (dmm.co.jp OR dlsite.com 限定検索)
  4. SearXNG 汎用クエリ (サークル 同人誌)
kindle / novel ソースは 4 のみ。

各ステップの実装と判定ヘルパーは `services.author_steps` に分離済み。
本ファイルはオーケストレーション（フォールバック順序）と debug 用の集約のみ持つ。
"""
# ステップ実装と定数を re-export（テストの monkeypatch 互換のためモジュール属性として保持）
from services.author_steps import (  # noqa: F401
    _DIRECT_HTTP_SITES,
    _MAX_AUTHOR_LEN,
    _extract_circle_from_page,
    _http_step,
    _sanitize_author,
    _searxng_filter_step,
    _searxng_generic_step,
    _try_direct_sites,
    _try_dlsite,
    _try_fanza,
)
from services.gemma_client import import_web_extract_tools


def resolve_author(title: str, source: str) -> str:
    """
    Web検索 + Gemma でタイトルからサークル名/著者名を推定する。

    generated ソースは以下の順で試み、成功した時点で返す:
      1. DLsite 直接検索
      2. FANZA 直接検索
      3. SearXNG site: フィルタ
      4. SearXNG 汎用クエリ（最終フォールバック）

    kindle / novel ソースは 4 のみ。

    Returns:
        サークル名/著者名文字列。取得失敗時は '作者不明'。
    """
    web_extract, searxng_search, fetch_url, call_ollama = import_web_extract_tools()
    if web_extract is None:
        return "作者不明"

    if source == "generated":
        if fetch_url and call_ollama:
            author = _try_dlsite(title, fetch_url, call_ollama)
            if author:
                return author
            author = _try_fanza(title, fetch_url, call_ollama)
            if author:
                return author
        author = _try_direct_sites(title, web_extract)
        if author:
            return author

    return _searxng_generic_step(title, source, web_extract, searxng_search)[0]


def resolve_author_debug(title: str, source: str) -> dict:
    """resolve_author の各ステップを可視化するデバッグ用関数。"""
    web_extract, searxng_search, fetch_url, call_ollama = import_web_extract_tools()
    if web_extract is None:
        return {"error": "Gemma ツールをインポートできません。GEMMA_TOOL_DIR を確認してください。"}

    result: dict = {"title": title, "source": source}

    if source == "generated":
        # ステップ 1/2: DLsite → FANZA 直接 HTTP フェッチ
        if fetch_url and call_ollama:
            for site_name, url_template in _DIRECT_HTTP_SITES:
                final, debug = _http_step(site_name, url_template, title, fetch_url, call_ollama)
                result.update(debug)
                if final:
                    result["final"] = final
                    result["used_step"] = f"{site_name}_direct"
                    return result

        # ステップ 3: SearXNG site: フィルタ
        final, debug = _searxng_filter_step(title, web_extract, searxng_search)
        result.update(debug)
        if final:
            result["final"] = final
            result["used_step"] = "searxng_site_filter"
            return result

    # ステップ 4: SearXNG 汎用クエリ
    final, debug = _searxng_generic_step(title, source, web_extract, searxng_search)
    result.update(debug)
    result["final"] = final
    result["used_step"] = "searxng_generic"
    return result
