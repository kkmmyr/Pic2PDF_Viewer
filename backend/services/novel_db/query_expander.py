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

詳細は docs/01_要件定義/機能追加候補.md B-11 / 同設計書 §7.4 を参照。
"""
from __future__ import annotations

from local_llm import LLMError

from config import (
    NOVEL_DB_QA_EXPAND_MODEL,
    NOVEL_DB_QA_EXPAND_N,
)

from ._llm_backend import QUERY_BACKEND

_EXPAND_PROMPT = """次の質問に対し、小説の本文を全文検索 / 意味検索するための短い検索クエリを {n} 個生成してください。

ルール:
- 各クエリは異なる切り口（場面 / キャラ / 行動 / 関係性 / 時期 など）で書く
- 各クエリは 10〜20 字程度のキーワード列
- 元のキーワードを含めても可
- 前置きや番号付けは不要
- 1 行 1 クエリ、合計 {n} 行のみ出力

質問: {question}

検索クエリ（{n} 行）:"""

_TIMEOUT_SEC = 60

# 短答型（150 字程度）。temperature は多様性を少し上げる
_OPTIONS = {
    "temperature": 0.3,
    "repeat_penalty": 1.2,
    "num_predict": 256,
    "num_ctx": 4096,
}



def expand_query(
    question: str,
    *,
    n: int = NOVEL_DB_QA_EXPAND_N,
    model: str = NOVEL_DB_QA_EXPAND_MODEL,
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
        response = QUERY_BACKEND.ask(prompt, model=model, options=_OPTIONS).strip()
    except LLMError:
        return [question]

    expansions = _parse_expansions(response, target_n=n - 1)
    # 元の質問を先頭に置き、展開クエリを後ろに追加。重複は除く
    result: list[str] = [question.strip()]
    for q in expansions:
        if q and q not in result:
            result.append(q)
        if len(result) >= n:
            break
    return result


def _parse_expansions(response: str, *, target_n: int) -> list[str]:
    """LLM の応答テキストから検索クエリリストを抽出する。

    想定形式:
        ベルナード 弁護士 法廷
        ソレス王子 裁判編 真犯人
        ベルナード レティ 連携 推理

    各行のノイズ（番号付け「1.」「・」「-」、前置き「検索クエリ:」など）は除去する。
    """
    if not response:
        return []
    out: list[str] = []
    for raw_line in response.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        # 番号付け / 箇条書き記号を除去
        for prefix_pattern in (
            ".", "．", ":", "：", "、", " ",
        ):
            # "1." / "1．" / "1:" / "1：" / "1、" などを剥がす
            if line and len(line) >= 2 and line[0].isdigit() and line[1] in prefix_pattern:
                line = line[2:].lstrip()
                break
        # 番号 + 空白（"1 ..."）も剥がす
        if line and line[0].isdigit():
            for i, c in enumerate(line):
                if not (c.isdigit() or c in ".．:：、 "):
                    line = line[i:].lstrip()
                    break
        # 「-」「・」「*」「>」 などの先頭記号を除去
        while line and line[0] in "-・*>＞→»→ 　":
            line = line[1:].lstrip()
        # 前置きラベルを除去
        for label in ("検索クエリ", "クエリ", "Query", "query"):
            for sep in (":", "：", " "):
                lab_sep = label + sep
                if line.startswith(lab_sep):
                    line = line[len(lab_sep):].lstrip()
                    break
        # 引用符類を剥がす
        line = line.strip("「」『』\"'")
        # 長すぎる行（説明文っぽい）はスキップ
        if not line or len(line) > 60:
            continue
        out.append(line)
        if len(out) >= target_n:
            break
    return out
