"""要約根拠検査用promptとLLM optionの正本。"""

from __future__ import annotations

from .llm_options import make_llm_options

GROUNDING_OPTIONS = make_llm_options(
    temperature=0.0,
    repeat_penalty=1.05,
    num_predict=4096,
    num_ctx=131072,
)

SUMMARY_GROUNDING_PROMPT = """小説『{book_name}』の{content_type}候補を、本文根拠だけで厳密に検査してください。

判定規則:
- supported: 主張の人物、行動、理由、結果、時系列、因果が候補ページ本文で確認できる。
- contradicted: 候補ページ本文と明確に矛盾する。似た出来事や別時点との混同も含む。
- unsupported: 候補ページだけでは主張の一部または全部を確認できない。
- supportedには候補ページ本文として全文提示された根拠ページを1件以上必ず付ける。
- candidate_pagesは主張ごとの検索優先ページである。別主張のcandidate_pagesであっても、
  候補ページ本文へ全文が提示され、当該主張を直接裏付けるページなら引用してよい。
- ページ番号付き書籍事実にだけ現れ、候補ページ本文へ全文が提示されていないページは引用しない。
- 本文にない一般知識、シリーズ後続巻、推測で補完しない。
{coverage_instruction}

検査対象の主張:
{claims}

候補ページ本文:
{evidence}

ページ根拠付き書籍事実:
{book_facts}

次のJSONオブジェクトだけを出力してください。コードフェンスや前置きは禁止です。
{{
  "claims": [
    {{
      "id": 1,
      "verdict": "supported",
      "evidence_pages": [12],
      "reason": "本文に基づく簡潔な判定理由"
    }}
  ],
  "coverage": {{
    "verdict": "pass",
    "missing_facts": [
      {{"pages": [30], "fact": "要約から欠落した主要事実"}}
    ]
  }}
}}

claimsには入力された全IDを昇順でちょうど1回ずつ含めてください。
coverage.verdictはpassまたはfail、missing_factsが空でなければ必ずfailにしてください。"""

SUMMARY_GROUNDING_REPAIR_PROMPT = """直前の小説要約根拠検査の応答は、次の出力契約エラーで受理できませんでした。

検証エラー:
{validation_error}

元の検査指示と入力:
{original_prompt}

受理できなかった応答:
{previous_response}

判定内容を推測で変更せず、元の検査指示に従う完全なJSONオブジェクトをもう一度出力してください。
- claimsには入力された全IDを昇順でちょうど1回ずつ含める。
- supportedのevidence_pagesは、元の候補ページ本文へ全文提示されたページだけから選ぶ。
- candidate_pagesは検索優先度であり、別主張の候補でも本文が全文提示されていれば引用してよい。
- 提示本文内で根拠を確認できなければ、書籍事実にあるだけの未提示ページを引用せずunsupportedにする。
- JSON以外の前置き、説明、コードフェンスは禁止する。"""
