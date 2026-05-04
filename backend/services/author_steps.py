"""
author_steps.py — 著者推定の各ステップ純関数群と定数。

`author_resolver.py` から分離した、依存ツール（fetch_url / call_ollama / web_extract /
searxng_search）を引数で受け取り `(final, debug)` を返す純関数群。
公開 API は `author_resolver` 側に残し、ここはステップの実装と判定ヘルパーのみ持つ。
"""
import json
from urllib.parse import quote as _url_quote

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

# SearXNG site: フィルタクエリ（ステップ 3）
_DIRECT_SITES_QUERY = '{title} site:dmm.co.jp OR site:dlsite.com'
_DIRECT_SITES_EXTRACT_SUFFIX = "のサークル名（なければ著者名）"

# 直接 HTTP フェッチする検索サイト（ステップ 1 / 2）
_DLSITE_URL_TEMPLATE = "https://www.dlsite.com/maniax/fsr/=/language/jp/keyword/{}/"
_FANZA_URL_TEMPLATE = "https://www.dmm.co.jp/dc/doujin/-/list/=/keyword={}/"

_DIRECT_HTTP_SITES = [
    ("dlsite", _DLSITE_URL_TEMPLATE),
    ("fanza",  _FANZA_URL_TEMPLATE),
]

_INVALID_PATTERNS = (
    "dlsite",
    "dmm",
    "fanza",
    "http://",
    "https://",
    "site:",
    "{",
    "見つかりません",
)
_MAX_AUTHOR_LEN = 80


def _sanitize_author(value) -> str:
    """
    Gemma が返した値が不正（URL・JSON・ブランド名・長文・「該当なし」文言）な場合は
    '作者不明' を返す。正常な値はそのまま返す。Gemma が稀に数値型を返すケースに備え、
    入力を str() で正規化してから判定する。
    """
    if value is None:
        return "作者不明"
    value = str(value).strip()
    if not value or value == "None":
        return "作者不明"
    if len(value) > _MAX_AUTHOR_LEN:
        return "作者不明"
    # 純数値文字列（"-1", "0", "123" 等）は Gemma が「該当なし」の sentinel として
    # 返してしまうケース。サークル名としても出現しないため一律で無効扱い。
    if value.lstrip("-+").replace(".", "", 1).isdigit():
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


# ---------------------------------------------------------------------------
# 各ステップ: (final, debug) を返す純関数群
# ---------------------------------------------------------------------------

def _http_step(
    site_name: str, url_template: str, title: str, fetch_url, call_ollama,
) -> tuple[str, dict]:
    """直接 HTTP フェッチで指定 site のサークル名を抽出。"""
    url = url_template.format(_url_quote(title))
    page_text = fetch_url(url, max_chars=3000)
    raw = _extract_circle_from_page(page_text, title, call_ollama) if page_text else ""
    sanitized = _sanitize_author(raw)
    final = sanitized if sanitized != "作者不明" else ""
    return final, {
        f"{site_name}_url": url,
        f"{site_name}_fetched": bool(page_text),
        f"{site_name}_raw": raw,
        f"{site_name}_result": final,
    }


def _searxng_filter_step(title: str, web_extract, searxng_search) -> tuple[str, dict]:
    """SearXNG site: フィルタで DLsite/FANZA を検索する。

    `searxng_search=None` の場合（resolve_author 通常パス）は snippets を取らず
    web_extract のみ呼ぶ。`searxng_search` 指定時（debug パス）は両方呼ぶ。
    """
    query = _DIRECT_SITES_QUERY.format(title=title)
    target = f'「{title}」' + _DIRECT_SITES_EXTRACT_SUFFIX
    if searxng_search is not None:
        snippets = searxng_search(query, num_results=5, language="ja")
        gemma_raw = web_extract(query, target, language="ja") if snippets else ""
    else:
        snippets = None
        gemma_raw = web_extract(query, target, language="ja")
    raw_str = str(gemma_raw).strip() if gemma_raw is not None else ""
    sanitized = _sanitize_author(raw_str)
    final = sanitized if sanitized != "作者不明" else ""
    debug: dict = {
        "direct_query": query,
        "direct_gemma_raw": gemma_raw,
        "direct_result": final,
    }
    if snippets is not None:
        debug["direct_searxng_hit"] = bool(snippets)
        debug["direct_searxng_snippets"] = snippets[:500] if snippets else ""
    return final, debug


def _searxng_generic_step(title: str, source: str, web_extract, searxng_search) -> tuple[str, dict]:
    """SearXNG 汎用クエリで検索する（最終フォールバック）。

    `searxng_search=None` の場合は snippets を取らず web_extract のみ呼ぶ。
    """
    config = _QUERY_CONFIG.get(source, _QUERY_CONFIG["generated"])
    query = config["query_template"].format(title=title)
    target = f'「{title}」' + config["extract_target_suffix"]
    if searxng_search is not None:
        snippets = searxng_search(query, num_results=5, language="ja")
        gemma_raw = web_extract(query, target, language="ja") if snippets else ""
    else:
        snippets = None
        gemma_raw = web_extract(query, target, language="ja")
    raw_str = str(gemma_raw).strip() if gemma_raw is not None else ""
    final = _sanitize_author(raw_str) if raw_str else "作者不明"
    debug: dict = {
        "query": query,
        "extract_target": target,
        "gemma_raw": gemma_raw,
    }
    if snippets is not None:
        debug["searxng_hit"] = bool(snippets)
        debug["searxng_snippets"] = snippets[:500] if snippets else ""
    return final, debug


# ---------------------------------------------------------------------------
# 個別ステップの薄いラッパー（テスト・デバッグから個別利用するため公開）
# ---------------------------------------------------------------------------

def _try_dlsite(title: str, fetch_url, call_ollama) -> str:
    return _http_step("dlsite", _DLSITE_URL_TEMPLATE, title, fetch_url, call_ollama)[0]


def _try_fanza(title: str, fetch_url, call_ollama) -> str:
    return _http_step("fanza", _FANZA_URL_TEMPLATE, title, fetch_url, call_ollama)[0]


def _try_direct_sites(title: str, web_extract) -> str:
    return _searxng_filter_step(title, web_extract, None)[0]
