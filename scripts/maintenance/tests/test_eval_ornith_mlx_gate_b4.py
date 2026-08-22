from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).parents[1] / "eval_ornith_mlx_gate_b4.py"
SPEC = importlib.util.spec_from_file_location("eval_ornith_mlx_gate_b4", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not load evaluator module: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

_build_schema = MODULE._build_schema
_semantic_checks = MODULE._semantic_checks
_validate_records = MODULE._validate_records


def _record(
    page: int,
    evidence: str,
    subject: str,
    claim: str,
) -> dict[str, Any]:
    return {
        "page": page,
        "evidence": evidence,
        "subject_span": subject,
        "claim": claim,
    }


def test_schema_restricts_each_request_to_one_page() -> None:
    schema = _build_schema(18)
    records = schema["properties"]["evidence_records"]
    item = records["items"]

    assert records["maxItems"] == 4
    assert item["additionalProperties"] is False
    assert item["properties"]["page"]["enum"] == [18]
    assert item["properties"]["evidence"]["maxLength"] == 360


def test_validator_rejects_modified_quote_and_subject_outside_quote() -> None:
    source = "茉莉花は、白楼国を平和にしたくてがんばった。"
    parsed = {
        "evidence_records": [
            _record(
                8,
                "茉莉花は、白楼国を平和にしたくて努力した。",
                "珀陽",
                "茉莉花は白楼国の平和を望んだ。",
            )
        ]
    }

    records, issues = _validate_records(parsed, page=8, source_text=source)

    assert len(records) == 1
    assert "record 1: evidence is not an exact source span" in issues
    assert "record 1: subject_span is not inside evidence" in issues


def test_semantic_checks_reject_observed_relationship_regressions() -> None:
    records = [
        _record(
            8,
            "珀陽は今、色々な情報を集めて、どうするかを考えている最中だろう。",
            "珀陽",
            "珀陽は白楼国を平和にしたくて戦争に葛藤した。",
        ),
        _record(
            18,
            "君は科挙試験の推薦人である子星のために、脱獄を手伝っていた証拠を消そうとするかもしれない。",
            "君",
            "茉莉花は子星の科挙試験の推薦人である。",
        ),
        _record(
            25,
            "年若い文官が、何度も必死に頭を下げてくる。",
            "年若い文官",
            "年若い文官は四日かけた準備のため茉莉花にぶつかった。",
        ),
        _record(
            26,
            "華副三司使と来現は、新人文官の言葉に顔を見合わせた。",
            "華副三司使",
            "苑翔景は暗茉莉花が別人かを疑った。",
        ),
    ]

    checks = _semantic_checks(records)

    assert not checks["page_8_matsurika_owns_war_conflict"]
    assert not checks["page_8_hakuyo_does_not_inherit_conflict"]
    assert not checks["page_18_kosei_is_matsurika_recommender"]
    assert not checks["page_18_recommender_relation_not_reversed"]
    assert not checks["page_25_clerk_does_not_inherit_four_day_reason"]
    assert not checks["no_hua_role_to_shokei_mapping"]


def test_semantic_checks_accept_evidence_grounded_relationships() -> None:
    records = [
        _record(
            8,
            "茉莉花は、白楼国を平和にしたくてがんばったのであって、戦争をしたくてがんばったわけではない。",
            "茉莉花",
            "茉莉花は白楼国の平和を望み、戦争を望んでいない。",
        ),
        _record(
            10,
            "子星は、穏やかに笑った。人の心は難しく、唯一で完璧な正答はない。",
            "子星",
            "子星は人の心に唯一で完璧な正答はないと述べた。",
        ),
        _record(
            10,
            "珀陽は言葉に詰まった。『……なら、私は両方好きってことにする』",
            "珀陽",
            "珀陽は両方好きだと答えた。",
        ),
        _record(
            18,
            "珀陽は言った。『茉莉花。申し訳ないけれど、君にはしばらく国外にいてもらう』",
            "珀陽",
            "珀陽は茉莉花をしばらく国外へ出すと告げた。",
        ),
        _record(
            18,
            "君は科挙試験の推薦人である子星のために、証拠を消そうとするかもしれない。",
            "子星",
            "子星は茉莉花の科挙試験の推薦人である。",
        ),
        _record(
            25,
            "年若い文官が茉莉花の肩に勢いよくぶつかった。",
            "年若い文官",
            "年若い文官が茉莉花にぶつかった。",
        ),
        _record(
            26,
            "新人文官は、女性文官に急いでいるふりをしてぶつかれと命じられた。",
            "新人文官",
            "新人文官は女性文官にぶつかるよう命じられた。",
        ),
        _record(
            26,
            "華副三司使は、暗茉莉花があのときと同一人物に見えると述べた。",
            "華副三司使",
            "華副三司使たちは暗茉莉花が同一人物か違う人間かを疑った。",
        ),
        _record(
            27,
            "来現と華副三司使は、暗茉莉花が別人かもしれないと頭を抱えた。",
            "来現",
            "来現たちは暗茉莉花が別人かを疑った。",
        ),
        _record(
            27,
            "来現が許可を出し、犀輿は荷物を探るため部屋を出た。",
            "来現",
            "来現は犀輿に荷物を探る許可を出した。",
        ),
    ]

    assert all(_semantic_checks(records).values())
