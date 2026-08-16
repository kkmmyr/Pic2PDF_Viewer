"""B-11 Query Expansion: ユーザー質問を gemma4:e4b で複数の検索クエリに展開する。

QA エンドポイントでハイブリッド検索を実行する前に、軽量 LLM で「異なる切り口の
検索クエリ N 個」を生成し、元の質問と合わせて hybrid_search を多角的に走らせる
ことで、抽象質問・関係質問の retrieval recall を改善する。

LLM 選定:
- 短答型タスク（150 字程度のキーワード列を出力）なので gemma4:e4b で十分
- Qwen3.6:35b-a3b だと +30〜60 秒のペナルティだが、gemma4:e4b なら +3〜5 秒
- `NOVEL_DB_QA_EXPAND_MODEL` 環境変数で切替可

LLM 呼び出しは Phase B（2026-05-11）以降、共通モジュール `local_llm` の
`OllamaBackend` 経由に集約。

詳細は docs/log/計画/バックログ.md B-11 / docs/design/詳細設計/機能別/小説RAG_検索QA設計.md §3 を参照。
"""

from __future__ import annotations

from local_llm import LLMError

from config import (
    NOVEL_DB_QA_EXPAND_MODEL,
    NOVEL_DB_QA_EXPAND_N,
)

from .llm_options import make_llm_options
from .llm_provider import NovelLlmProvider, get_llm_provider
from .query_expansion_parser import parse_expansions

_EXPAND_PROMPT = """次の質問に対し、小説の本文を全文検索 / 意味検索するための短い検索クエリを {n} 個生成してください。

ルール:
- 各クエリは異なる切り口（場面 / キャラ / 行動 / 関係性 / 時期 など）で書く
- 各クエリは 10〜20 字程度のキーワード列
- 元のキーワードを含めても可
- 前置きや番号付けは不要
- 1 行 1 クエリ、合計 {n} 行のみ出力

質問: {question}

検索クエリ（{n} 行）:"""

# 短答型（150 字程度）。temperature は多様性を少し上げる
_OPTIONS = make_llm_options(temperature=0.3, repeat_penalty=1.2, num_predict=256, num_ctx=4096)


def expand_query(
    question: str,
    *,
    n: int = NOVEL_DB_QA_EXPAND_N,
    model: str = NOVEL_DB_QA_EXPAND_MODEL,
    provider: NovelLlmProvider | None = None,
) -> list[str]:
    """ユーザーの質問を `n` 個の検索クエリに展開して返す。

    元の質問 + 展開クエリ N-1 個 = 合計 N 個を返す（元質問は必ず含める）。
    LLM 呼び出しが失敗した場合は元の質問のみのリスト `[question]` を返す
    （後方互換: フォールバックで通常検索に縮退する）。

    Args:
        question: ユーザーの質問文
        n: 返却する合計クエリ数（既定 NOVEL_DB_QA_EXPAND_N = 3）
        model: 使用モデル（既定 NOVEL_DB_QA_EXPAND_MODEL = gemma4:e4b）

    Returns:
        検索に使うクエリリスト。先頭は必ず元の質問。
    """
    if not question or not question.strip():
        return [question]
    if n <= 1:
        return [question]

    prompt = _EXPAND_PROMPT.format(question=question.strip(), n=n - 1)
    try:
        backend = (provider or get_llm_provider()).query
        response = backend.ask(prompt, model=model, options=_OPTIONS).strip()
    except LLMError:
        return [question]

    expansions = parse_expansions(response, target_n=n - 1)
    # 元の質問を先頭に置き、展開クエリを後ろに追加。重複は除く
    result: list[str] = [question.strip()]
    for q in expansions:
        if q and q not in result:
            result.append(q)
        if len(result) >= n:
            break
    return result


def _parse_expansions(response: str, *, target_n: int) -> list[str]:
    """既存import向けfacade。新規コードは ``parse_expansions`` を参照する。"""
    return parse_expansions(response, target_n=target_n)
