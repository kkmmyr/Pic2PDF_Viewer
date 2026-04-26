"""
author_resolver.py — タイトルからサークル名を推定するサービス。

web_extract (Gemma 4 ツール) を使い、Web検索 + Gemma でサークル名を取得する。
ソース種別に応じてクエリを切り替えることで汎用的に利用できる。

generated ソースの検索フロー:
  1. DLsite / Fanza 直接検索 (site: フィルタ) → Snippet にサークル名が含まれることが多い
  2. ヒットしない場合は汎用クエリ（サークル 同人誌）にフォールバック
kindle / novel ソースは汎用クエリのみ。
"""
import sys
from config import GEMMA_TOOL_DIR

# ソース別の検索クエリ設定
# generated（同人誌）はサークル名のみ取得。kindle/novel は著者名（サークル概念がない）。
_QUERY_CONFIG: dict[str, dict[str, str]] = {
    "generated": {
        # ダブルクォート完全一致は日本語・特殊文字でヒットしないため使わない
        "query_template": '{title} サークル 同人誌',
        # extract_target には「何を抽出するか」だけ書く。命令文・フォールバック指示を含めると
        # _call_gemma の外側プロンプトと衝突し Gemma が誤動作する。
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

# generated ソース向け: DLsite / Fanza を site: フィルタで直接検索するクエリ
# Fanza のコンテンツは dmm.co.jp ドメインで提供されており、
# Snippet に「作品名(サークル名) - FANZA」形式でサークル名が含まれることが多い。
# DLsite の Snippet にはサークル名が入らないケースがあるため dmm.co.jp を優先する。
_DIRECT_SITES_QUERY = '{title} site:dmm.co.jp OR site:dlsite.com'
_DIRECT_SITES_EXTRACT_SUFFIX = "のサークル名（なければ著者名）"


def _ensure_web_extract():
    """web_extract モジュールをインポートして返す。失敗時は None。"""
    import os
    lib_dir = os.path.join(GEMMA_TOOL_DIR, "lib")
    for p in (GEMMA_TOOL_DIR, lib_dir):
        if p not in sys.path:
            sys.path.insert(0, p)

    # backend の config.py が sys.modules['config'] にキャッシュされているため、
    # web_extract が Gemma の config を読めず ImportError になる。
    # インポート時だけ backend config を退避し、完了後に復元する。
    # （web_extract は TIMEOUT_FETCH_URL をモジュール変数に取り込むため、
    #   復元後も正常に動作する）
    saved_config = sys.modules.pop("config", None)
    try:
        from web_extract import web_extract, searxng_search  # type: ignore[import]
        return web_extract, searxng_search
    except ImportError:
        return None, None
    finally:
        if saved_config is not None:
            sys.modules["config"] = saved_config


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
    if not value or value == "None":
        return "作者不明"
    if len(value) > _MAX_AUTHOR_LEN:
        return "作者不明"
    lower = value.lower()
    if any(pat in lower for pat in _INVALID_PATTERNS):
        return "作者不明"
    return value


def _try_direct_sites(title: str, web_extract) -> str:
    """
    DLsite / Fanza を site: フィルタで検索してサークル名を取得する。
    取得できなかった場合は空文字を返す（呼び出し側でフォールバック）。
    """
    query = _DIRECT_SITES_QUERY.format(title=title)
    extract_target = f'「{title}」' + _DIRECT_SITES_EXTRACT_SUFFIX
    result = web_extract(query, extract_target, language="ja")
    result = str(result).strip() if result is not None else ""
    sanitized = _sanitize_author(result)
    # 「作者不明」が返った場合はフォールバックさせる
    return sanitized if sanitized != "作者不明" else ""


def resolve_author(title: str, source: str) -> str:
    """
    Web検索 + Gemma でタイトルからサークル名/著者名を推定する。

    generated ソースは DLsite/Fanza 直接検索を先に試み、
    ヒットしない場合のみ汎用クエリにフォールバックする。

    Args:
        title: 拡張子なしのファイル名（書籍タイトル）
        source: 'generated' | 'kindle' | 'novel'

    Returns:
        サークル名/著者名文字列。取得失敗時は '作者不明'。
    """
    web_extract, _ = _ensure_web_extract()
    if web_extract is None:
        return "作者不明"

    # generated ソースは DLsite/Fanza 直接検索を優先
    if source == "generated":
        author = _try_direct_sites(title, web_extract)
        if author:
            return _sanitize_author(author)

    # フォールバック: 既存の汎用クエリ
    config = _QUERY_CONFIG.get(source, _QUERY_CONFIG["generated"])
    query = config["query_template"].format(title=title)
    extract_target = f'「{title}」' + config["extract_target_suffix"]

    result = web_extract(query, extract_target, language="ja")
    result_str = str(result).strip() if result is not None else ""
    return _sanitize_author(result_str) if result_str else "作者不明"


def resolve_author_debug(title: str, source: str) -> dict:
    """
    resolve_author の各ステップを可視化するデバッグ用関数。
    SearXNG の検索結果と Gemma の応答を個別に返す。
    """
    web_extract, searxng_search = _ensure_web_extract()
    if web_extract is None:
        return {"error": "web_extract モジュールをインポートできません。GEMMA_TOOL_DIR を確認してください。"}

    result = {
        "title": title,
        "source": source,
    }

    # generated ソースは DLsite/Fanza 直接検索ステップを追加
    if source == "generated":
        direct_query = _DIRECT_SITES_QUERY.format(title=title)
        direct_target = f'「{title}」' + _DIRECT_SITES_EXTRACT_SUFFIX
        direct_snippets = searxng_search(direct_query, num_results=5, language="ja")
        direct_gemma = web_extract(direct_query, direct_target, language="ja") if direct_snippets else ""
        direct_result = str(direct_gemma).strip() if direct_gemma is not None else ""

        result["direct_query"] = direct_query
        result["direct_searxng_hit"] = bool(direct_snippets)
        result["direct_searxng_snippets"] = direct_snippets[:500] if direct_snippets else ""
        result["direct_gemma_raw"] = direct_gemma
        result["direct_result"] = direct_result if direct_result and direct_result != "作者不明" else ""

        # 直接検索でサークル名が取れた場合はフォールバック不要
        if result["direct_result"]:
            result["final"] = result["direct_result"]
            result["used_fallback"] = False
            return result

    # 汎用クエリ（フォールバック or kindle/novel）
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
    result["final"] = gemma_str if gemma_str else "作者不明"

    if source == "generated":
        result["used_fallback"] = True

    return result
