from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).parents[1] / "eval_ornith_mlx_gate_b2.py"
SPEC = importlib.util.spec_from_file_location("eval_ornith_mlx_gate_b2", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not load evaluator module: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

_language_leaks = MODULE._language_leaks
_semantic_checks = MODULE._semantic_checks


def _fact(
    page: int,
    subject: str,
    action: str,
    reason: str = "",
    characters: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "page": page,
        "subject": subject,
        "action": action,
        "reason_or_result": reason,
        "canonical_characters": characters or [],
    }


def test_language_leaks_distinguishes_japanese_and_chinese_glyphs() -> None:
    assert not _language_leaks([_fact(1, "皓茉莉花", "黒曜城へ入った")])

    leaks = _language_leaks([_fact(1, "芳子星", "黑曜城へ进入した")])

    assert any("simplified chars=" in leak and "进" in leak for leak in leaks)
    assert any("simplified chars=" in leak and "黑" in leak for leak in leaks)


def test_semantic_checks_reject_observed_gate_b3_regressions() -> None:
    facts = [
        _fact(
            8,
            "珀陽",
            "戦争をするかしないかについて考えた",
            "白楼国を平和にしたくて働いたが答えを今出せていない",
            ["珀陽"],
        ),
        _fact(
            18,
            "珀陽",
            "御史台の見張りを説明した",
            "皓茉莉花は芳子星の科挙試験の推薦人だから",
            ["珀陽", "皓茉莉花", "芳子星"],
        ),
        _fact(
            25,
            "新人文官",
            "皓茉莉花へわざとぶつかった",
            "四日かけた準備を効かせるため",
        ),
        _fact(
            26,
            "華副三司使",
            "望来現と同一人物かを議論した",
            characters=["苑翔景", "望来現"],
        ),
    ]

    checks = _semantic_checks(facts)

    assert not checks["page_8_matsurika_worries_about_war"]
    assert not checks["page_8_hakuyo_does_not_inherit_matsurika_reason"]
    assert not checks["page_18_kosei_is_matsurika_recommender"]
    assert not checks["page_18_recommender_relation_not_reversed"]
    assert not checks["page_25_26_new_clerk_reason_not_matsurika_plan"]
    assert not checks["page_26_hua_role_not_mapped_to_shokei"]


def test_semantic_checks_accept_corrected_relationship_directions() -> None:
    facts = [
        _fact(
            8,
            "皓茉莉花",
            "戦争をするかしないかの答えを考え続けた",
            characters=["皓茉莉花"],
        ),
        _fact(
            18,
            "珀陽",
            "皓茉莉花へ御史台の見張りを説明した",
            "科挙試験の推薦人である芳子星の証拠を消す疑いがあるため",
            ["珀陽", "皓茉莉花", "芳子星"],
        ),
        _fact(
            26,
            "新人文官",
            "上司の命令で皓茉莉花へぶつかった",
            characters=["皓茉莉花"],
        ),
        _fact(
            26,
            "華副三司使",
            "望来現と暗茉莉花が同一人物かを議論した",
            characters=["望来現", "皓茉莉花"],
        ),
    ]

    checks = _semantic_checks(facts)

    assert checks["page_8_matsurika_worries_about_war"]
    assert checks["page_8_hakuyo_does_not_inherit_matsurika_reason"]
    assert checks["page_18_kosei_is_matsurika_recommender"]
    assert checks["page_18_recommender_relation_not_reversed"]
    assert checks["page_25_26_new_clerk_reason_not_matsurika_plan"]
    assert checks["page_26_hua_role_not_mapped_to_shokei"]
