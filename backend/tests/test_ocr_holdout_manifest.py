from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "maintenance"
sys.path.insert(0, str(_SCRIPT_DIR))
import ocr_holdout_ledger as holdout_ledger  # noqa: E402
import ocr_holdout_manifest as holdout  # noqa: E402


def _fixture(tmp_path: Path) -> tuple[dict, dict, dict]:
    terms = [f"固有名詞{index}" for index in range(10)]
    reference = "".join(term * 5 for term in terms)
    entries = []
    corpus_entries = []
    for index in range(20):
        package = tmp_path / f"qa-package-{index}.json"
        package.write_text(json.dumps({"entry": index}), encoding="utf-8")
        image_sha = f"{index + 1:064x}"
        entries.append(
            {
                "entry_id": index + 1,
                "run_id": 100 + index,
                "page_no": 1,
                "series_id": f"series-{index % 3}",
                "qa_package": package.name,
                "proper_nouns": terms if index == 0 else [],
            }
        )
        corpus_entries.append(
            {
                "id": index + 1,
                "run_id": 100 + index,
                "page_no": 1,
                "image_sha256": image_sha,
                "page_type": "narrative",
                "layout_type": "normal_prose",
                "reference_text": reference if index == 0 else "本文",
                "state": "verified",
            }
        )
    spec = {
        "holdout_id": "fresh-holdout",
        "purpose": "b35_final",
        "selection": {
            "method": "quality_blind",
            "input_sha256": "a" * 64,
        },
        "entries": entries,
    }
    corpus = {"entries": corpus_entries}
    policy = {
        "schema_version": 1,
        "corpus": {},
        "quality": {
            "min_proper_noun_terms": 10,
            "min_proper_noun_expected_occurrences": 50,
        },
        "proper_nouns": [],
    }
    return spec, corpus, policy


def test_formal_manifest_verifies_all_packages_and_corpus(tmp_path: Path) -> None:
    spec, corpus, policy = _fixture(tmp_path)
    manifest = holdout.build_formal_manifest(
        spec,
        corpus,
        policy,
        package_root=tmp_path,
        sealed_at="2026-08-17T00:00:00Z",
    )

    result = holdout.verify_formal_manifest(
        manifest,
        corpus,
        policy,
        package_root=tmp_path,
    )

    assert result == {
        "manifest_sha256": manifest["manifest_sha256"],
        "entry_count": 20,
        "series_count": 3,
        "normal_prose_count": 20,
        "proper_noun_terms": 10,
        "proper_noun_expected_occurrences": 50,
    }


def test_formal_manifest_rejects_two_series(tmp_path: Path) -> None:
    spec, corpus, policy = _fixture(tmp_path)
    for entry in spec["entries"]:
        entry["series_id"] = f"series-{entry['entry_id'] % 2}"

    with pytest.raises(ValueError, match="3 series"):
        holdout.build_formal_manifest(
            spec,
            corpus,
            policy,
            package_root=tmp_path,
            sealed_at="2026-08-17T00:00:00Z",
        )


def test_formal_manifest_rejects_19_pages_and_proper_noun_shortage(
    tmp_path: Path,
) -> None:
    spec, corpus, policy = _fixture(tmp_path)
    spec["entries"].pop()
    with pytest.raises(ValueError, match="20 normal prose"):
        holdout.build_formal_manifest(
            spec,
            corpus,
            policy,
            package_root=tmp_path,
            sealed_at="2026-08-17T00:00:00Z",
        )

    spec, corpus, policy = _fixture(tmp_path)
    spec["entries"][0]["proper_nouns"] = ["固有名詞0"]
    with pytest.raises(ValueError, match="proper noun terms"):
        holdout.build_formal_manifest(
            spec,
            corpus,
            policy,
            package_root=tmp_path,
            sealed_at="2026-08-17T00:00:00Z",
        )


def test_formal_manifest_digest_is_deterministic(tmp_path: Path) -> None:
    spec, corpus, policy = _fixture(tmp_path)
    first = holdout.build_formal_manifest(
        spec,
        corpus,
        policy,
        package_root=tmp_path,
        sealed_at="2026-08-17T00:00:00Z",
    )
    second = holdout.build_formal_manifest(
        spec,
        corpus,
        policy,
        package_root=tmp_path,
        sealed_at="2026-08-17T00:00:00Z",
    )
    assert first == second


def test_formal_gate_policy_uses_manifest_scope_without_mutating_policy(
    tmp_path: Path,
) -> None:
    spec, corpus, policy = _fixture(tmp_path)
    policy["corpus"] = {
        "min_verified_pages": 20,
        "min_page_type_counts": {"toc": 4, "illustration": 4},
        "min_layout_type_counts": {"structured": 4},
        "min_layout_reference_chars": {"normal_prose": 4000},
    }
    policy["proper_nouns"] = [{"image_sha256": "f" * 64, "terms": ["別コーパス"]}]
    manifest = holdout.build_formal_manifest(
        spec,
        corpus,
        policy,
        package_root=tmp_path,
        sealed_at="2026-08-17T00:00:00Z",
    )

    effective = holdout.build_formal_gate_policy(manifest, policy)

    assert effective["corpus"]["min_page_type_counts"] == {}
    assert effective["corpus"]["min_layout_type_counts"] == {}
    assert effective["corpus"]["min_verified_pages"] == 20
    assert effective["corpus"]["min_layout_reference_chars"] == {"normal_prose": 4000}
    assert effective["proper_nouns"] == [
        {
            "image_sha256": manifest["entries"][0]["image_sha256"],
            "terms": [f"固有名詞{index}" for index in range(10)],
        }
    ]
    assert policy["corpus"]["min_page_type_counts"] == {
        "toc": 4,
        "illustration": 4,
    }
    assert policy["proper_nouns"] == [{"image_sha256": "f" * 64, "terms": ["別コーパス"]}]


def test_formal_manifest_rejects_package_change(tmp_path: Path) -> None:
    spec, corpus, policy = _fixture(tmp_path)
    manifest = holdout.build_formal_manifest(
        spec,
        corpus,
        policy,
        package_root=tmp_path,
        sealed_at="2026-08-17T00:00:00Z",
    )
    (tmp_path / "qa-package-0.json").write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="package digest"):
        holdout.verify_formal_manifest(
            manifest,
            corpus,
            policy,
            package_root=tmp_path,
        )


def test_ledger_opens_once_and_never_rolls_back(tmp_path: Path) -> None:
    spec, corpus, policy = _fixture(tmp_path)
    manifest = holdout.build_formal_manifest(
        spec,
        corpus,
        policy,
        package_root=tmp_path,
        sealed_at="2026-08-17T00:00:00Z",
    )
    ledger_path = tmp_path / "ledger.json"
    holdout_ledger.record_sealed_manifest(
        ledger_path,
        manifest,
        operator="tester",
        occurred_at="2026-08-17T00:00:01Z",
    )
    holdout.authorize_formal_holdout_open(
        manifest,
        corpus,
        policy,
        package_root=tmp_path,
        ledger_path=ledger_path,
        operator="tester",
        reason="one-time benchmark",
        occurred_at="2026-08-17T00:00:02Z",
    )

    with pytest.raises(ValueError, match="already opened"):
        holdout.authorize_formal_holdout_open(
            manifest,
            corpus,
            policy,
            package_root=tmp_path,
            ledger_path=ledger_path,
            operator="tester",
            reason="retry",
            occurred_at="2026-08-17T00:00:03Z",
        )

    holdout_ledger.retire_formal_holdout_to_tuning(
        ledger_path,
        manifest,
        operator="tester",
        reason="quality gate failed",
        occurred_at="2026-08-17T00:00:04Z",
    )
    with pytest.raises(ValueError, match="already retired"):
        holdout_ledger.retire_formal_holdout_to_tuning(
            ledger_path,
            manifest,
            operator="tester",
            reason="retry",
            occurred_at="2026-08-17T00:00:05Z",
        )

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert [event["state"] for event in ledger["events"]] == [
        "sealed",
        "opened",
        "retired_to_tuning",
    ]
