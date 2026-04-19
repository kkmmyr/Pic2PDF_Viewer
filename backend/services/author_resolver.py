"""
author_resolver.py — タイトルからサークル名を推定するサービス。

web_extract (Gemma 4 ツール) を使い、Web検索 + Gemma でサークル名を取得する。
ソース種別に応じてクエリを切り替えることで汎用的に利用できる。
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


def _ensure_web_extract():
    """web_extract モジュールをインポートして返す。失敗時は None。"""
    if GEMMA_TOOL_DIR not in sys.path:
        sys.path.insert(0, GEMMA_TOOL_DIR)
    try:
        from web_extract import web_extract, searxng_search  # type: ignore[import]
        return web_extract, searxng_search
    except ImportError:
        return None, None


def resolve_author(title: str, source: str) -> str:
    """
    Web検索 + Gemma でタイトルからサークル名/著者名を推定する。

    Args:
        title: 拡張子なしのファイル名（書籍タイトル）
        source: 'generated' | 'kindle' | 'novel'

    Returns:
        サークル名/著者名文字列。取得失敗時は '作者不明'。
    """
    web_extract, _ = _ensure_web_extract()
    if web_extract is None:
        return "作者不明"

    config = _QUERY_CONFIG.get(source, _QUERY_CONFIG["generated"])
    query = config["query_template"].format(title=title)
    extract_target = f'「{title}」' + config["extract_target_suffix"]

    result = web_extract(query, extract_target, language="ja")
    return result.strip() if result and result.strip() else "作者不明"


def resolve_author_debug(title: str, source: str) -> dict:
    """
    resolve_author の各ステップを可視化するデバッグ用関数。
    SearXNG の検索結果と Gemma の応答を個別に返す。
    """
    web_extract, searxng_search = _ensure_web_extract()
    if web_extract is None:
        return {"error": "web_extract モジュールをインポートできません。GEMMA_TOOL_DIR を確認してください。"}

    config = _QUERY_CONFIG.get(source, _QUERY_CONFIG["generated"])
    query = config["query_template"].format(title=title)
    extract_target = f'「{title}」' + config["extract_target_suffix"]

    snippets = searxng_search(query, num_results=5, language="ja")
    gemma_result = web_extract(query, extract_target, language="ja") if snippets else ""

    return {
        "title": title,
        "source": source,
        "query": query,
        "extract_target": extract_target,
        "searxng_hit": bool(snippets),
        "searxng_snippets": snippets[:500] if snippets else "",
        "gemma_raw": gemma_result,
        "final": gemma_result.strip() if gemma_result and gemma_result.strip() else "作者不明",
    }
