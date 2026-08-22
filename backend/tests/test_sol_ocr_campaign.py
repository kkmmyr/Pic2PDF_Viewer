from __future__ import annotations

import hashlib
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest
from PIL import Image

from services.novel_db.sol_ocr_campaign import (
    CHECKER_ARTIFACT_V2_SCHEMA_VERSION,
    PAGE_ARTIFACT_SCHEMA_VERSION,
    PAGE_CANDIDATE_V2_SCHEMA_VERSION,
    RESOLVED_ARTIFACT_V2_SCHEMA_VERSION,
    SOL_MODEL,
    SOL_PROMPT_VERSION,
    build_checker_v2_artifact,
    build_page_candidate_v2_artifact,
    build_resolved_v2_artifact,
    create_manifest,
    create_pilot_manifest,
    export_pilot_images,
    load_checker_v2_artifact,
    load_page_artifact,
    load_page_candidate_v2_artifact,
    load_pilot_manifest,
    load_resolved_v2_artifact,
    validate_checker_v2_artifact,
    validate_page_artifact,
    validate_page_candidate_pair,
    validate_page_candidate_v2_artifact,
    validate_resolved_v2_artifact,
    verify_manifest,
)


def _make_image(path: Path, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 30), color).save(path)


def _make_canonical_db(path: Path, book_name: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE books (id INTEGER PRIMARY KEY, name TEXT NOT NULL);"
            "CREATE TABLE pages (id INTEGER PRIMARY KEY, book_id INTEGER, page_no INTEGER);"
        )
        conn.execute("INSERT INTO books (id, name) VALUES (1, ?)", (book_name,))
        conn.executemany("INSERT INTO pages (book_id, page_no) VALUES (1, ?)", [(1,), (2,)])


def test_create_manifest_excludes_debug_images_and_partitions_whole_books(tmp_path: Path) -> None:
    images_root = tmp_path / "images"
    _make_image(images_root / "既存OCR本" / "001.png", "white")
    _make_image(images_root / "既存OCR本" / "002.png", "black")
    _make_image(images_root / "既存OCR本" / "008_debug_vis.png", "red")
    _make_image(images_root / "画像のみ本" / "001.png", "blue")
    db_path = tmp_path / "novel.db"
    _make_canonical_db(db_path, "既存OCR本")

    manifest = create_manifest(
        images_root=images_root,
        db_path=db_path,
        output_dir=tmp_path / "campaigns",
        campaign_id="sol-20260819",
        worker_count=2,
        created_at="2026-08-19T12:00:00+09:00",
    )

    assert manifest["summary"] == {
        "book_count": 2,
        "page_count": 3,
        "canonical_book_count": 1,
        "canonical_page_count": 2,
        "image_only_book_count": 1,
    }
    existing = next(book for book in manifest["books"] if book["book_name"] == "既存OCR本")
    assert [page["image_path"] for page in existing["pages"]] == ["既存OCR本/001.png", "既存OCR本/002.png"]
    assigned = [book["book_name"] for partition in manifest["partitions"] for book in partition["books"]]
    assert sorted(assigned) == ["既存OCR本", "画像のみ本"]
    assert len(assigned) == len(set(assigned))

    manifest_path = tmp_path / "campaigns" / "sol-20260819" / "manifest.json"
    verified = verify_manifest(manifest_path, images_root)
    assert verified["manifest_sha256"] == manifest["manifest_sha256"]
    for worker_id in ("worker-1", "worker-2"):
        partition = json.loads((manifest_path.parent / f"{worker_id}.json").read_text(encoding="utf-8"))
        assert partition["manifest_sha256"] == manifest["manifest_sha256"]


def test_verify_manifest_rejects_changed_image(tmp_path: Path) -> None:
    images_root = tmp_path / "images"
    image_path = images_root / "本" / "001.png"
    _make_image(image_path, "white")
    create_manifest(
        images_root=images_root,
        output_dir=tmp_path / "campaigns",
        campaign_id="sol-test",
        worker_count=1,
        created_at="2026-08-19T12:00:00+09:00",
    )
    _make_image(image_path, "black")

    with pytest.raises(ValueError, match=r"source image (?:size )?changed"):
        verify_manifest(tmp_path / "campaigns" / "sol-test" / "manifest.json", images_root)


def test_pilot_selection_and_page_artifact_are_manifest_bound(tmp_path: Path) -> None:
    images_root = tmp_path / "images"
    books = []
    for canonical in (False, True):
        for book_index in range(19 if canonical else 8):
            book_name = f"{'canonical' if canonical else 'image'}-{book_index:02d}"
            pages = []
            for page_no in range(1, 4):
                image_path = images_root / book_name / f"{page_no:03d}.png"
                _make_image(image_path, "white")
                pages.append(
                    {
                        "page_no": page_no,
                        "image_path": f"{book_name}/{page_no:03d}.png",
                        "image_sha256": __import__("hashlib").sha256(image_path.read_bytes()).hexdigest(),
                        "size_bytes": image_path.stat().st_size,
                    }
                )
            books.append(
                {
                    "book_name": book_name,
                    "page_count": 3,
                    "canonical_page_count": 3 if canonical else 0,
                    "has_canonical_ocr": canonical,
                    "pages": pages,
                }
            )
    campaign = {
        "campaign_id": "sol-test",
        "manifest_sha256": "a" * 64,
        "books": books,
    }
    pilot_path = tmp_path / "pilot.json"
    pilot = create_pilot_manifest(campaign_manifest=campaign, output_path=pilot_path)
    assert pilot["summary"] == {"sample_count": 81, "image_only_samples": 24, "canonical_samples": 57}
    assert {sample["worker_id"] for sample in pilot["samples"]} == {"worker-1", "worker-2", "worker-3"}
    assert load_pilot_manifest(pilot_path)["pilot_sha256"] == pilot["pilot_sha256"]
    export_pilot_images(pilot_manifest=pilot, images_root=images_root, output_tar=tmp_path / "pilot.tar")

    with tarfile.open(tmp_path / "pilot.tar") as archive:
        assert len(archive.getnames()) == 81

    sample = pilot["samples"][0]
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": PAGE_ARTIFACT_SCHEMA_VERSION,
                "campaign_id": pilot["campaign_id"],
                "manifest_sha256": pilot["manifest_sha256"],
                "pilot_sha256": pilot["pilot_sha256"],
                "sample_id": sample["sample_id"],
                "worker_id": sample["worker_id"],
                "model": SOL_MODEL,
                "prompt_version": SOL_PROMPT_VERSION,
                "book_name": sample["book_name"],
                "page_no": sample["page_no"],
                "image_sha256": sample["image_sha256"],
                "text": "転記本文",
                "transcription_notes": [],
                "processed_at": "2026-08-19T12:00:00+09:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    artifact = load_page_artifact(artifact_path)
    assert validate_page_artifact(artifact, pilot_manifest=pilot, images_root=images_root) == sample

    artifact["image_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="image_sha256 mismatch"):
        validate_page_artifact(artifact, pilot_manifest=pilot, images_root=images_root)


def _with_digest(artifact: dict[str, object], field: str) -> dict[str, object]:
    artifact[field] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in artifact.items() if key != field},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return artifact


def _v2_bundle(
    tmp_path: Path,
) -> tuple[
    Path,
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    images_root = tmp_path / "images"
    image_path = images_root / "v2-book" / "001.png"
    _make_image(image_path, "white")
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    sample = {
        "sample_id": "pilot-v2-001",
        "book_name": "v2-book",
        "page_no": 1,
        "image_path": "v2-book/001.png",
        "image_sha256": image_sha256,
    }
    pilot = {
        "campaign_id": "sol-v2",
        "manifest_sha256": "a" * 64,
        "pilot_sha256": "b" * 64,
        "samples": [sample],
    }
    common = {
        "campaign_id": pilot["campaign_id"],
        "manifest_sha256": pilot["manifest_sha256"],
        "pilot_sha256": pilot["pilot_sha256"],
        "purpose": "formal",
        "model": SOL_MODEL,
        "prompt_sha256": "c" * 64,
        "policy_sha256": "d" * 64,
        "sample_id": sample["sample_id"],
        "book_name": sample["book_name"],
        "page_no": sample["page_no"],
        "image_sha256": sample["image_sha256"],
    }
    candidate_a = _with_digest(
        {
            "schema_version": PAGE_CANDIDATE_V2_SCHEMA_VERSION,
            **common,
            "session_id": "session-a",
            "worker_id": "worker-a",
            "candidate_id": "a",
            "coverage": [
                {
                    "column_id": "right-column",
                    "order": 1,
                    "strip_id": "strip-1",
                    "start_anchor": "始",
                    "end_anchor": "終",
                    "text": "始本文終",
                    "block_type": "body",
                    "ruby": [],
                    "uncertainties": [],
                }
            ],
            "text": "始本文終",
            "transcription_notes": [],
            "processed_at": "2026-08-19T23:00:00+09:00",
        },
        "candidate_sha256",
    )
    candidate_b = _with_digest(
        {
            "schema_version": PAGE_CANDIDATE_V2_SCHEMA_VERSION,
            **common,
            "session_id": "session-b",
            "worker_id": "worker-b",
            "candidate_id": "b",
            "coverage": [
                {
                    "column_id": "right-column",
                    "order": 1,
                    "strip_id": "strip-1",
                    "start_anchor": "始",
                    "end_anchor": "終",
                    "text": "始本文終",
                    "block_type": "body",
                    "ruby": [],
                    "uncertainties": [],
                }
            ],
            "text": "始本文終",
            "transcription_notes": ["読めないルビなし"],
            "processed_at": "2026-08-19T23:01:00+09:00",
        },
        "candidate_sha256",
    )
    checker = _with_digest(
        {
            "schema_version": CHECKER_ARTIFACT_V2_SCHEMA_VERSION,
            **common,
            "session_id": "session-checker",
            "worker_id": "worker-checker",
            "candidate_a_sha256": candidate_a["candidate_sha256"],
            "candidate_b_sha256": candidate_b["candidate_sha256"],
            "candidate_coverage": {"a": "complete", "b": "complete"},
            "reading_order": "pass",
            "major_errors": [],
            "selection": "a",
            "verdict": "pass",
            "reason": "A/Bとも列coverageと読順を満たすためAを選択。",
            "checked_at": "2026-08-19T23:02:00+09:00",
        },
        "checker_sha256",
    )
    resolved = _with_digest(
        {
            "schema_version": RESOLVED_ARTIFACT_V2_SCHEMA_VERSION,
            **{key: value for key, value in common.items() if key != "model"},
            "candidate_a_sha256": candidate_a["candidate_sha256"],
            "candidate_b_sha256": candidate_b["candidate_sha256"],
            "checker_sha256": checker["checker_sha256"],
            "canonical_eligible": True,
            "resolved_at": "2026-08-19T23:03:00+09:00",
        },
        "resolved_sha256",
    )
    return images_root, pilot, candidate_a, candidate_b, checker, resolved


def test_v2_artifacts_are_self_hashed_bound_and_canonical_eligible(tmp_path: Path) -> None:
    images_root, pilot, candidate_a, candidate_b, checker, resolved = _v2_bundle(tmp_path)
    paths = {
        "candidate-a.json": candidate_a,
        "candidate-b.json": candidate_b,
        "checker.json": checker,
        "resolved.json": resolved,
    }
    for filename, artifact in paths.items():
        (tmp_path / filename).write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

    loaded_a = load_page_candidate_v2_artifact(tmp_path / "candidate-a.json")
    loaded_b = load_page_candidate_v2_artifact(tmp_path / "candidate-b.json")
    loaded_checker = load_checker_v2_artifact(tmp_path / "checker.json")
    loaded_resolved = load_resolved_v2_artifact(tmp_path / "resolved.json")

    assert (
        validate_page_candidate_v2_artifact(loaded_a, pilot_manifest=pilot, images_root=images_root)
        == pilot["samples"][0]
    )
    validate_page_candidate_pair(loaded_a, loaded_b)
    validate_checker_v2_artifact(loaded_checker, candidate_a=loaded_a, candidate_b=loaded_b)
    assert (
        validate_resolved_v2_artifact(
            loaded_resolved,
            candidate_a=loaded_a,
            candidate_b=loaded_b,
            checker=loaded_checker,
            pilot_manifest=pilot,
            images_root=images_root,
        )
        == pilot["samples"][0]
    )


def test_v2_raw_candidate_is_normalized_with_column_evidence(tmp_path: Path) -> None:
    _, pilot, candidate_a, _, _, _ = _v2_bundle(tmp_path)
    raw = {
        "sample_id": candidate_a["sample_id"],
        "book_name": candidate_a["book_name"],
        "page_no": candidate_a["page_no"],
        "image_sha256": candidate_a["image_sha256"],
        "candidate_id": "a",
        "producer_session_id": "session-a",
        "worker_id": "worker-a",
        "model": SOL_MODEL,
        "prompt_sha256": candidate_a["prompt_sha256"],
        "policy_sha256": candidate_a["policy_sha256"],
        "processed_at": candidate_a["processed_at"],
        "visual_column_count": 1,
        "columns": [
            {
                "column_id": "C001",
                "reading_order": 1,
                "strip_id": "S001",
                "start_anchor": "始",
                "end_anchor": "終",
                "text": "始本文終",
                "block_type": "body",
                "ruby": [],
                "uncertainties": [],
            }
        ],
        "strip_evidence": [{"strip_id": "S001", "column_ids": ["C001"]}],
        "text": "始本文終",
        "transcription_notes": "列coverage確認済み",
    }

    normalized = build_page_candidate_v2_artifact(raw, pilot_manifest=pilot, purpose="tuning")

    assert normalized["coverage"][0]["text"] == "始本文終"
    assert normalized["purpose"] == "tuning"
    assert normalized["transcription_notes"] == ["列coverage確認済み"]
    assert normalized["candidate_sha256"]


def test_v2_raw_checker_and_resolved_envelope_are_self_hashed(tmp_path: Path) -> None:
    _, _, candidate_a, candidate_b, _, _ = _v2_bundle(tmp_path)
    raw_checker = {
        "sample_id": candidate_a["sample_id"],
        "session_id": "session-checker",
        "worker_id": "worker-checker",
        "candidate_coverage": {"a": "complete", "b": "incomplete"},
        "reading_order": "pass",
        "major_errors": [],
        "selection": "a",
        "verdict": "pass",
        "reason": "Aだけが全列を保持した。",
        "checked_at": "2026-08-19T23:02:00+09:00",
    }

    checker = build_checker_v2_artifact(raw_checker, candidate_a=candidate_a, candidate_b=candidate_b)
    resolved = build_resolved_v2_artifact(
        candidate_a=candidate_a,
        candidate_b=candidate_b,
        checker=checker,
        canonical_eligible=True,
        resolved_at="2026-08-19T23:03:00+09:00",
    )

    assert checker["checker_sha256"]
    assert resolved["canonical_eligible"] is True
    assert resolved["resolved_sha256"]


def test_v2_artifacts_fail_closed_for_session_and_coverage_proof(tmp_path: Path) -> None:
    images_root, pilot, candidate_a, candidate_b, checker, resolved = _v2_bundle(tmp_path)
    candidate_b["session_id"] = candidate_a["session_id"]
    _with_digest(candidate_b, "candidate_sha256")
    checker["candidate_b_sha256"] = candidate_b["candidate_sha256"]
    _with_digest(checker, "checker_sha256")
    resolved["candidate_b_sha256"] = candidate_b["candidate_sha256"]
    resolved["checker_sha256"] = checker["checker_sha256"]
    _with_digest(resolved, "resolved_sha256")

    with pytest.raises(ValueError, match="different sessions"):
        validate_resolved_v2_artifact(
            resolved,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            checker=checker,
            pilot_manifest=pilot,
            images_root=images_root,
        )

    _, pilot, candidate_a, candidate_b, checker, resolved = _v2_bundle(tmp_path / "incomplete")
    checker["candidate_coverage"]["a"] = "incomplete"
    _with_digest(checker, "checker_sha256")
    resolved["checker_sha256"] = checker["checker_sha256"]
    _with_digest(resolved, "resolved_sha256")
    with pytest.raises(ValueError, match="canonical eligibility"):
        validate_resolved_v2_artifact(
            resolved,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            checker=checker,
            pilot_manifest=pilot,
            images_root=tmp_path / "incomplete" / "images",
        )


def test_v2_artifact_schema_rejects_tampered_digest_and_invalid_anchors(tmp_path: Path) -> None:
    _, _, candidate_a, _, _, _ = _v2_bundle(tmp_path)
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate_a, ensure_ascii=False), encoding="utf-8")
    candidate_a["text"] = "始tampered終"
    candidate_path.write_text(json.dumps(candidate_a, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_page_candidate_v2_artifact(candidate_path)

    candidate_a["coverage"][0]["start_anchor"] = "存在しないanchor"
    _with_digest(candidate_a, "candidate_sha256")
    candidate_path.write_text(json.dumps(candidate_a, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="anchor is absent"):
        load_page_candidate_v2_artifact(candidate_path)
