"""
author_resolver.py — タイトルからサークル名を推定するサービス。

generated ソースの検索フロー:
  1. DLsite 直接検索 (dlsite.com/maniax を HTTP フェッチ)
  2. FANZA 直接検索 (dmm.co.jp/dc/doujin を HTTP フェッチ)
  3. SearXNG site: フィルタ (dmm.co.jp OR dlsite.com 限定検索)
  4. SearXNG 汎用クエリ (サークル 同人誌)
kindle / novel ソースは 4 のみ。
"""
import json
from urllib.parse import quote as _url_quote
from services.gemma_client import import_web_extract_tools

# ソース別の SearXNG 汎用クエリ設定
_QUERY_CONFIG: dict[str, dict[str, str]] = {
    "generated": {
        "query_template": '{title} サークル 同人誌',
        "extract_target_suffix": "のサークル名（なければ著者名）",
    },
    "kindle": {
        "query_template": '{title} 著者 漫画',
        "extract_target_suffix": "のサークル名または著者名",
    },
    "novel": {
        "query_template": '{title} 著者 小説',
        "extract_target_suffix": "のサークル名または著者名",
    },
}

# SearXNG site: フィルタクエリ（ステップ 3 フォールバック用）
_DIRECT_SITES_QUERY = '{title} site:dmm.co.jp OR site:dlsite.com'
_DIRECT_SITES_EXTRACT_SUFFIX = "のサークル名（なければ著者名）"

# 直接 HTTP フェッチする検索 URL（ステップ 1 / 2）
_DLSITE_SEARCH_URL = "https://www.dlsite.com/maniax/fsr/=/language/jp/keyword/{}/"
_FANZA_SEARCH_URL = "https://www.dmm.co.jp/dc/doujin/-/list/=/keyword={}/"

_INVALID_PATTERNS = (
    "dlsite",
    "dmm",
    "fanza",
    "http://",
    "https://",
    "site:",
    "{",
)
_MAX_AUTHOR_LEN = 80


def _sanitize_author(value: str) -> str:
    """
    Gemma が返した値が不正（URL・JSON・ブランド名・長文）な場合は '作者不明' を返す。
    正常な値はそのまま返す。
    """
    value = value.strip()
    if not value or value == "None":
        return "作者不明"
    if len(value) > _MAX_AUTHOR_LEN:
        return "作者不明"
    lower = value.lower()
    if any(pat in lower for pat in _INVALID_PATTERNS):
        return "作者不明"
    return value


def _extract_circle_from_page(page_text: str, title: str, call_ollama) -> str:
    """フェッチしたページテキストを Gemma に渡してサークル名を抽出する。
    取得できない場合は空文字を返す。
    """
    if not page_text:
        return ""
    prompt = (
        f"以下のページ内容から「{title}」のサークル名（なければ著者名）を抽出してください。\n\n"
        f"{page_text[:3000]}\n\n"
        f'JSONのみで回答してください: {{"result": "抽出した値"}}\n'
        f"情報が見つからない場合は: {{}}"
    )
    raw = call_ollama(prompt, response_format="json", source="author_resolver")
    if not raw or raw.startswith("[エラー]"):
        return ""
    try:
        parsed = json.loads(raw)
        return parsed.get("result", "") if parsed else ""
    except json.JSONDecodeError:
        return raw.strip()


def _try_dlsite(title: str, fetch_url, call_ollama) -> str:
    """DLsite 検索ページを直接 HTTP フェッチしてサークル名を取得する。
    取得できない場合は空文字を返す（呼び出し側がフォールバック）。
    """
    url = _DLSITE_SEARCH_URL.format(_url_quote(title))
    page_text = fetch_url(url, max_chars=3000)
    if not page_text:
        return ""
    result = _extract_circle_from_page(page_text, title, call_ollama)
    sanitized = _sanitize_author(result)
    return sanitized if sanitized != "作者不明" else ""


def _try_fanza(title: str, fetch_url, call_ollama) -> str:
    """FANZA 検索ページを直接 HTTP フェッチしてサークル名を取得する。
    取得できない場合は空文字を返す（呼び出し側がフォールバック）。
    """
    url = _FANZA_SEARCH_URL.format(_url_quote(title))
    page_text = fetch_url(url, max_chars=3000)
    if not page_text:
        return ""
    result = _extract_circle_from_page(page_text, title, call_ollama)
    sanitized = _sanitize_author(result)
    return sanitized if sanitized != "作者不明" else ""


def _try_direct_sites(title: str, web_extract) -> str:
    """SearXNG の site: フィルタで DLsite/FANZA を検索してサークル名を取得する。
    直接検索が失敗した場合のフォールバック。取得できない場合は空文字を返す。
    """
    query = _DIRECT_SITES_QUERY.format(title=title)
    extract_target = f'「{title}」' + _DIRECT_SITES_EXTRACT_SUFFIX
    result = web_extract(query, extract_target, language="ja")
    result = str(result).strip() if result is not None else ""
    sanitized = _sanitize_author(result)
    return sanitized if sanitized != "作者不明" else ""


def resolve_author(title: str, source: str) -> str:
    """
    Web検索 + Gemma でタイトルからサークル名/著者名を推定する。

    generated ソースは以下の順で試み、成功した時点で返す:
      1. DLsite 直接検索
      2. FANZA 直接検索
      3. SearXNG site: フィルタ（フォールバック）
      4. SearXNG 汎用クエリ（最終フォールバック）

    kindle / novel ソースは 4 のみ。

    Args:
        title: 拡張子なしのファイル名（書籍タイトル）
        source: 'generated' | 'kindle' | 'novel'

    Returns:
        サークル名/著者名文字列。取得失敗時は '作者不明'。
    """
    web_extract, _, fetch_url, call_ollama = import_web_extract_tools()
    if web_extract is None:
        return "作者不明"

    if source == "generated":
        # ステップ 1: DLsite 直接
        if fetch_url and call_ollama:
            author = _try_dlsite(title, fetch_url, call_ollama)
            if author:
                return author
            # ステップ 2: FANZA 直接
            author = _try_fanza(title, fetch_url, call_ollama)
            if author:
                return author
        # ステップ 3: SearXNG site: フィルタ
        author = _try_direct_sites(title, web_extract)
        if author:
            return author

    # ステップ 4: SearXNG 汎用クエリ（最終フォールバック / kindle / novel）
    config = _QUERY_CONFIG.get(source, _QUERY_CONFIG["generated"])
    query = config["query_template"].format(title=title)
    extract_target = f'「{title}」' + config["extract_target_suffix"]
    result = web_extract(query, extract_target, language="ja")
    result_str = str(result).strip() if result is not None else ""
    return _sanitize_author(result_str) if result_str else "作者不明"


def resolve_author_debug(title: str, source: str) -> dict:
    """
    resolve_author の各ステップを可視化するデバッグ用関数。
    DLsite/FANZA 直接検索・SearXNG の結果を個別に返す。
    """
    web_extract, searxng_search, fetch_url, call_ollama = import_web_extract_tools()
    if web_extract is None:
        return {"error": "Gemma ツールをインポートできません。GEMMA_TOOL_DIR を確認してください。"}

    result: dict = {"title": title, "source": source}

    if source == "generated":
        # ステップ 1: DLsite 直接
        if fetch_url and call_ollama:
            dlsite_url = _DLSITE_SEARCH_URL.format(_url_quote(title))
            dlsite_text = fetch_url(dlsite_url, max_chars=3000)
            dlsite_raw = _extract_circle_from_page(dlsite_text, title, call_ollama) if dlsite_text else ""
            dlsite_result = _sanitize_author(dlsite_raw)
            result["dlsite_url"] = dlsite_url
            result["dlsite_fetched"] = bool(dlsite_text)
            result["dlsite_raw"] = dlsite_raw
            result["dlsite_result"] = dlsite_result if dlsite_result != "作者不明" else ""

            if result["dlsite_result"]:
                result["final"] = result["dlsite_result"]
                result["used_step"] = "dlsite_direct"
                return result

            # ステップ 2: FANZA 直接
            fanza_url = _FANZA_SEARCH_URL.format(_url_quote(title))
            fanza_text = fetch_url(fanza_url, max_chars=3000)
            fanza_raw = _extract_circle_from_page(fanza_text, title, call_ollama) if fanza_text else ""
            fanza_result = _sanitize_author(fanza_raw)
            result["fanza_url"] = fanza_url
            result["fanza_fetched"] = bool(fanza_text)
            result["fanza_raw"] = fanza_raw
            result["fanza_result"] = fanza_result if fanza_result != "作者不明" else ""

            if result["fanza_result"]:
                result["final"] = result["fanza_result"]
                result["used_step"] = "fanza_direct"
                return result

        # ステップ 3: SearXNG site: フィルタ
        direct_query = _DIRECT_SITES_QUERY.format(title=title)
        direct_target = f'「{title}」' + _DIRECT_SITES_EXTRACT_SUFFIX
        direct_snippets = searxng_search(direct_query, num_results=5, language="ja")
        direct_gemma = web_extract(direct_query, direct_target, language="ja") if direct_snippets else ""
        direct_raw = str(direct_gemma).strip() if direct_gemma is not None else ""
        direct_sanitized = _sanitize_author(direct_raw)

        result["direct_query"] = direct_query
        result["direct_searxng_hit"] = bool(direct_snippets)
        result["direct_searxng_snippets"] = direct_snippets[:500] if direct_snippets else ""
        result["direct_gemma_raw"] = direct_gemma
        result["direct_result"] = direct_sanitized if direct_sanitized != "作者不明" else ""

        if result["direct_result"]:
            result["final"] = result["direct_result"]
            result["used_step"] = "searxng_site_filter"
            return result

    # ステップ 4: SearXNG 汎用クエリ
    config = _QUERY_CONFIG.get(source, _QUERY_CONFIG["generated"])
    query = config["query_template"].format(title=title)
    extract_target = f'「{title}」' + config["extract_target_suffix"]

    snippets = searxng_search(query, num_results=5, language="ja")
    gemma_result = web_extract(query, extract_target, language="ja") if snippets else ""

    result["query"] = query
    result["extract_target"] = extract_target
    result["searxng_hit"] = bool(snippets)
    result["searxng_snippets"] = snippets[:500] if snippets else ""
    result["gemma_raw"] = gemma_result
    gemma_str = str(gemma_result).strip() if gemma_result is not None else ""
    result["final"] = _sanitize_author(gemma_str) if gemma_str else "作者不明"
    result["used_step"] = "searxng_generic"

    return result
