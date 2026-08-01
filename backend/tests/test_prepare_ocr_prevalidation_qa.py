from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "prepare_ocr_prevalidation_qa.py"
SPEC = importlib.util.spec_from_file_location("prepare_ocr_prevalidation_qa", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
prevalidation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prevalidation)


def test_candidate_similarity_handles_whitespace_only_differences() -> None:
    assert prevalidation.candidate_similarity("本文\nです", "本文 です") == 1


def test_validate_selected_page_rejects_non_narrative() -> None:
    with pytest.raises(ValueError, match="narrative"):
        prevalidation.validate_selected_page(
            {
                "qa_state": "approved",
                "page_type": "toc",
                "layout_type": "normal_prose",
            }
        )


def test_build_priority_queue_combines_similarity_and_gap_reasons() -> None:
    package = [
        {
            "run_id": 4,
            "page_no": 24,
            "image_sha256": "a",
            "candidate_similarity": 0.85,
        },
        {
            "run_id": 8,
            "page_no": 39,
            "image_sha256": "b",
            "candidate_similarity": 0.98,
        },
        {
            "run_id": 13,
            "page_no": 23,
            "image_sha256": "c",
            "candidate_similarity": 0.99,
        },
    ]
    merges = [
        {"run_id": 4, "page_no": 24, "proposal_count": 1},
        {"run_id": 8, "page_no": 39, "proposal_count": 1},
        {"run_id": 13, "page_no": 23, "proposal_count": 0},
    ]

    queue = prevalidation.build_priority_queue(package, merges, similarity_threshold=0.94)

    assert [(item["run_id"], item["page_no"]) for item in queue] == [(4, 24), (8, 39)]
    assert queue[0]["reasons"] == [
        "candidate_similarity_below_threshold",
        "anchored_gap_proposal",
    ]


def test_queue_identity_sha256_changes_when_page_set_changes() -> None:
    original = [
        {"run_id": 4, "page_no": 24, "image_sha256": "a"},
        {"run_id": 8, "page_no": 39, "image_sha256": "b"},
    ]
    same = [dict(item) for item in original]
    changed = [dict(item) for item in original]
    changed[1]["page_no"] = 40

    assert prevalidation.queue_identity_sha256(original) == (prevalidation.queue_identity_sha256(same))
    assert prevalidation.queue_identity_sha256(original) != (prevalidation.queue_identity_sha256(changed))


def test_verify_queue_document_rejects_identity_mismatch() -> None:
    queue = [{"run_id": 4, "page_no": 24, "image_sha256": "a"}]
    document = {
        "queue_count": 1,
        "queue_identity_sha256": "wrong",
        "queue": queue,
    }

    with pytest.raises(ValueError, match="identity mismatch"):
        prevalidation.verify_queue_document(document)

    document["queue_identity_sha256"] = prevalidation.queue_identity_sha256(queue)
    assert prevalidation.verify_queue_document(document) == {
        "queue_count": 1,
        "queue_identity_sha256": document["queue_identity_sha256"],
    }
