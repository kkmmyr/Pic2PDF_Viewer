from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from services.novel_db.connection import with_db
from services.novel_db.migrations import upgrade_head
from services.novel_db.sol_ocr_campaign import (
    PAGE_ARTIFACT_SCHEMA_VERSION,
    SOL_MODEL,
    SOL_PROMPT_VERSION,
    build_checker_v2_artifact,
    build_page_candidate_v2_artifact,
    build_resolved_v2_artifact,
)
from services.novel_db.sol_ocr_import import (
    build_pilot_comparison_report,
    build_pilot_review_package,
    import_pilot_artifacts,
    import_resolved_v2_bundles,
)


def _v2_import_bundle(
    tmp_path: Path,
    *,
    purpose: str = "formal",
    verdict: str = "pass",
    canonical_eligible: bool = True,
    selection: str | None = "b",
    prompt_sha256: str = "c" * 64,
    candidate_a_text: str = "始A終",
    processed_at: str = "2026-08-20T00:00:00+09:00",
) -> tuple[Path, dict[str, object], dict[str, object], tuple[Path, Path, Path, Path]]:
    images_root = tmp_path / "images"
    image_path = images_root / "v2-import-book" / "001.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 30), "white").save(image_path)
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    sample = {
        "sample_id": "pilot-v2-import-001",
        "book_name": "v2-import-book",
        "page_no": 1,
        "image_path": "v2-import-book/001.png",
        "image_sha256": image_sha256,
    }
    pilot = {
        "campaign_id": "sol-v2-import",
        "manifest_sha256": "a" * 64,
        "pilot_sha256": "b" * 64,
        "samples": [sample],
    }
    campaign = {"books": [{"book_name": sample["book_name"], "page_count": 1, "pages": [{"page_no": 1}]}]}

    def candidate(candidate_id: str, text: str, session: str, worker: str) -> dict[str, object]:
        return build_page_candidate_v2_artifact(
            {
                "sample_id": sample["sample_id"],
                "book_name": sample["book_name"],
                "page_no": sample["page_no"],
                "image_sha256": sample["image_sha256"],
                "candidate_id": candidate_id,
                "producer_session_id": session,
                "worker_id": worker,
                "model": SOL_MODEL,
                "prompt_sha256": prompt_sha256,
                "policy_sha256": "d" * 64,
                "processed_at": processed_at,
                "visual_column_count": 1,
                "columns": [
                    {
                        "column_id": "C001",
                        "reading_order": 1,
                        "strip_id": "S001",
                        "start_anchor": "始",
                        "end_anchor": "終",
                        "text": text,
                        "block_type": "body",
                        "ruby": [],
                        "uncertainties": [],
                    }
                ],
                "strip_evidence": [{"strip_id": "S001", "column_ids": ["C001"]}],
                "text": text,
                "transcription_notes": [],
            },
            pilot_manifest=pilot,
            purpose=purpose,
        )

    candidate_a = candidate("a", candidate_a_text, "session-a", "worker-a")
    candidate_b = candidate("b", "始B終", "session-b", "worker-b")
    checker = build_checker_v2_artifact(
        {
            "sample_id": sample["sample_id"],
            "session_id": "session-checker",
            "worker_id": "worker-checker",
            "candidate_coverage": {"a": "complete", "b": "complete"},
            "reading_order": "pass",
            "major_errors": [],
            "selection": selection,
            "verdict": verdict,
            "reason": "independent checker result",
            "checked_at": "2026-08-20T00:01:00+09:00",
        },
        candidate_a=candidate_a,
        candidate_b=candidate_b,
    )
    resolved = build_resolved_v2_artifact(
        candidate_a=candidate_a,
        candidate_b=candidate_b,
        checker=checker,
        canonical_eligible=canonical_eligible,
        resolved_at="2026-08-20T00:02:00+09:00",
    )
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    paths = (
        artifact_dir / "candidate-a.json",
        artifact_dir / "candidate-b.json",
        artifact_dir / "checker.json",
        artifact_dir / "resolved.json",
    )
    for path, artifact in zip(paths, (candidate_a, candidate_b, checker, resolved), strict=True):
        path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    return images_root, campaign, pilot, paths


def test_pilot_import_is_manifest_bound_idempotent_and_compares_legacy(tmp_data_dir, tmp_path: Path) -> None:
    upgrade_head()
    book_name = "Sol pilot book"
    images_root = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"])
    image_path = images_root / book_name / "001.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (20, 30), "white").save(image_path)
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()

    with with_db() as conn, conn:
        book_id = int(
            conn.execute(
                "INSERT INTO books (name, pdf_path, images_dir, page_count) VALUES (?, '', ?, 1)",
                (book_name, str(image_path.parent)),
            ).lastrowid
        )
        legacy_run_id = int(
            conn.execute(
                "INSERT INTO ocr_runs "
                "(book_name, engine, model, source_page_count, state, qa_state) "
                "VALUES (?, 'legacy', 'pre-sol-snapshot', 1, 'completed', 'approved')",
                (book_name,),
            ).lastrowid
        )
        conn.execute(
            "INSERT INTO ocr_page_results "
            "(run_id, page_no, image_sha256, state, full_text, char_count, published_text) "
            "VALUES (?, 1, ?, 'passed', '旧本文', 3, '旧本文')",
            (legacy_run_id, image_sha256),
        )
        conn.execute(
            "INSERT INTO ocr_publications "
            "(book_id, run_id, action, actor, published_at) VALUES (?, ?, 'legacy_snapshot', 'test', 'now')",
            (book_id, legacy_run_id),
        )

    campaign = {
        "books": [
            {
                "book_name": book_name,
                "page_count": 1,
                "pages": [{"page_no": 1, "image_path": f"{book_name}/001.png", "image_sha256": image_sha256}],
            }
        ]
    }
    sample = {
        "sample_id": "pilot-001",
        "group": "canonical",
        "worker_id": "worker-1",
        "book_name": book_name,
        "page_no": 1,
        "image_path": f"{book_name}/001.png",
        "image_sha256": image_sha256,
    }
    pilot = {
        "campaign_id": "sol-test",
        "manifest_sha256": "a" * 64,
        "pilot_sha256": "b" * 64,
        "samples": [sample],
    }
    artifact = {
        "schema_version": PAGE_ARTIFACT_SCHEMA_VERSION,
        "campaign_id": "sol-test",
        "manifest_sha256": "a" * 64,
        "pilot_sha256": "b" * 64,
        "sample_id": "pilot-001",
        "worker_id": "worker-1",
        "model": SOL_MODEL,
        "prompt_version": SOL_PROMPT_VERSION,
        "book_name": book_name,
        "page_no": 1,
        "image_sha256": image_sha256,
        "text": "新本文",
        "transcription_notes": [],
        "processed_at": "2026-08-19T12:00:00+09:00",
    }
    artifact_path = tmp_path / "pilot-001.json"
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    kwargs = {
        "db_path": Path(tmp_data_dir["NOVEL_DB_PATH"]),
        "campaign_manifest": campaign,
        "pilot_manifest": pilot,
        "images_root": images_root,
        "artifact_paths": [artifact_path],
    }

    first = import_pilot_artifacts(**kwargs)
    second = import_pilot_artifacts(**kwargs)
    assert (first["inserted"], first["idempotent"]) == (1, 0)
    assert (second["inserted"], second["idempotent"]) == (0, 1)
    with with_db() as conn:
        row = conn.execute(
            "SELECT primary_text, external_text, published_text FROM ocr_page_results pr "
            "JOIN ocr_runs r ON r.id=pr.run_id WHERE r.engine='sol'"
        ).fetchone()
    assert tuple(row) == ("新本文", "旧本文", None)
    report = build_pilot_comparison_report(db_path=Path(tmp_data_dir["NOVEL_DB_PATH"]), pilot_manifest=pilot)
    assert report["summary"]["canonical_compared"] == 1
    assert report["summary"]["normalized_edit_rate_vs_legacy"] is not None
    review = build_pilot_review_package(db_path=Path(tmp_data_dir["NOVEL_DB_PATH"]), pilot_manifest=pilot)
    assert review["pages"][0]["sol_text"] == "新本文"
    assert review["pages"][0]["legacy_text"] == "旧本文"

    artifact["text"] = "競合本文"
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting Sol OCR artifact"):
        import_pilot_artifacts(**kwargs)


def test_pilot_import_rejects_incomplete_artifact_set_before_db_changes(tmp_data_dir, tmp_path: Path) -> None:
    upgrade_head()
    db_path = Path(tmp_data_dir["NOVEL_DB_PATH"])
    images_root = tmp_path / "images"
    book_dir = images_root / "Book"
    book_dir.mkdir(parents=True)
    image_paths = []
    for page_no in (1, 2):
        image_path = book_dir / f"{page_no:03d}.png"
        Image.new("RGB", (8, 8), "white").save(image_path)
        image_paths.append(image_path)

    pages = [
        {
            "page_no": page_no,
            "image_path": f"Book/{page_no:03d}.png",
            "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "size_bytes": image_path.stat().st_size,
        }
        for page_no, image_path in enumerate(image_paths, start=1)
    ]
    campaign = {
        "campaign_id": "campaign",
        "manifest_sha256": "a" * 64,
        "books": [{"book_name": "Book", "page_count": 2, "pages": pages}],
    }
    samples = [
        {
            "sample_id": f"pilot-{page_no:03d}",
            "group": "image_only",
            "worker_id": "worker-1",
            "book_name": "Book",
            "page_no": page_no,
            "image_path": f"Book/{page_no:03d}.png",
            "image_sha256": pages[page_no - 1]["image_sha256"],
        }
        for page_no in (1, 2)
    ]
    pilot = {
        "campaign_id": "campaign",
        "manifest_sha256": "a" * 64,
        "pilot_sha256": "b" * 64,
        "samples": samples,
    }
    artifact = {
        "schema_version": PAGE_ARTIFACT_SCHEMA_VERSION,
        "campaign_id": "campaign",
        "manifest_sha256": "a" * 64,
        "pilot_sha256": "b" * 64,
        "sample_id": "pilot-001",
        "worker_id": "worker-1",
        "model": SOL_MODEL,
        "prompt_version": SOL_PROMPT_VERSION,
        "book_name": "Book",
        "page_no": 1,
        "image_sha256": pages[0]["image_sha256"],
        "text": "本文",
        "transcription_notes": [],
        "processed_at": "2026-08-19T12:00:00+09:00",
    }
    artifact_path = tmp_path / "pilot-001.json"
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="sample set mismatch"):
        import_pilot_artifacts(
            db_path=db_path,
            campaign_manifest=campaign,
            pilot_manifest=pilot,
            images_root=images_root,
            artifact_paths=[artifact_path],
        )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ocr_runs WHERE engine='sol'").fetchone()[0] == 0


def test_v2_import_stages_complete_bundle_with_a_b_and_checker_selection(tmp_data_dir, tmp_path: Path) -> None:
    upgrade_head()
    images_root, campaign, pilot, bundle = _v2_import_bundle(tmp_path)
    kwargs = {
        "db_path": Path(tmp_data_dir["NOVEL_DB_PATH"]),
        "campaign_manifest": campaign,
        "pilot_manifest": pilot,
        "images_root": images_root,
        "bundle_paths": [bundle],
    }

    first = import_resolved_v2_bundles(**kwargs)
    second = import_resolved_v2_bundles(**kwargs)

    assert (first["inserted"], first["idempotent"]) == (1, 0)
    assert (second["inserted"], second["idempotent"]) == (0, 1)
    with with_db() as conn:
        row = conn.execute(
            "SELECT pr.primary_text, pr.external_text, pr.full_text, pr.selected_engine, pr.state, pr.qa_state, "
            "pr.published_text, pr.index_eligible, pr.raw_output FROM ocr_page_results pr "
            "JOIN ocr_runs r ON r.id=pr.run_id WHERE r.engine='sol'"
        ).fetchone()
    assert tuple(row[:8]) == ("始A終", "始B終", "始B終", "external", "passed", "not_required", None, 0)
    envelope = json.loads(str(row[8]))
    assert set(envelope) == {"schema_version", "candidate_a", "candidate_b", "checker", "resolved", "sha256"}
    assert envelope["sha256"]["resolved"] == envelope["resolved"]["resolved_sha256"]


def test_v2_import_tuning_is_never_publishable(tmp_data_dir, tmp_path: Path) -> None:
    upgrade_head()
    images_root, campaign, pilot, bundle = _v2_import_bundle(tmp_path, purpose="tuning", selection="a")

    import_resolved_v2_bundles(
        db_path=Path(tmp_data_dir["NOVEL_DB_PATH"]),
        campaign_manifest=campaign,
        pilot_manifest=pilot,
        images_root=images_root,
        bundle_paths=[bundle],
    )

    with with_db() as conn:
        row = conn.execute(
            "SELECT state, full_text, selected_engine, qa_state, published_text, index_eligible, quality_flags_json "
            "FROM ocr_page_results"
        ).fetchone()
    assert tuple(row[:6]) == ("needs_review", "始A終", "primary", "pending", None, 0)
    assert "sol_ocr_v2_tuning_not_publishable" in json.loads(str(row[6]))


def test_v2_import_nonpass_is_held_for_review(tmp_data_dir, tmp_path: Path) -> None:
    upgrade_head()
    images_root, campaign, pilot, bundle = _v2_import_bundle(
        tmp_path,
        verdict="needs_review",
        canonical_eligible=False,
        selection=None,
    )

    import_resolved_v2_bundles(
        db_path=Path(tmp_data_dir["NOVEL_DB_PATH"]),
        campaign_manifest=campaign,
        pilot_manifest=pilot,
        images_root=images_root,
        bundle_paths=[bundle],
    )

    with with_db() as conn:
        row = conn.execute(
            "SELECT state, full_text, selected_engine, qa_state, quality_flags_json FROM ocr_page_results"
        ).fetchone()
    assert tuple(row[:4]) == ("needs_review", None, "unresolved", "pending")
    assert "sol_ocr_v2_needs_review" in json.loads(str(row[4]))


def test_v2_import_separates_revisions_and_rejects_changed_envelopes(tmp_data_dir, tmp_path: Path) -> None:
    upgrade_head()
    db_path = Path(tmp_data_dir["NOVEL_DB_PATH"])
    images_root, campaign, pilot, bundle = _v2_import_bundle(tmp_path / "first")
    common = {
        "db_path": db_path,
        "campaign_manifest": campaign,
        "pilot_manifest": pilot,
        "images_root": images_root,
    }
    import_resolved_v2_bundles(**common, bundle_paths=[bundle])

    _, _, _, changed_bundle = _v2_import_bundle(tmp_path / "changed", processed_at="2026-08-20T00:03:00+09:00")
    with pytest.raises(ValueError, match="conflicting Sol OCR v2 envelope"):
        import_resolved_v2_bundles(**common, bundle_paths=[changed_bundle])

    revision_images, revision_campaign, revision_pilot, revision_bundle = _v2_import_bundle(
        tmp_path / "revision",
        prompt_sha256="e" * 64,
    )
    import_resolved_v2_bundles(
        db_path=db_path,
        campaign_manifest=revision_campaign,
        pilot_manifest=revision_pilot,
        images_root=revision_images,
        bundle_paths=[revision_bundle],
    )
    with with_db() as conn:
        models = conn.execute("SELECT model FROM ocr_runs WHERE engine='sol' ORDER BY model").fetchall()
    assert len(models) == 2
    assert models[0][0] != models[1][0]


def test_v2_import_rejects_incomplete_explicit_selection_before_db_changes(tmp_data_dir, tmp_path: Path) -> None:
    upgrade_head()
    db_path = Path(tmp_data_dir["NOVEL_DB_PATH"])
    images_root, campaign, pilot, bundle = _v2_import_bundle(tmp_path)
    expected_samples = [
        pilot["samples"][0],
        {
            **pilot["samples"][0],
            "sample_id": "pilot-v2-import-002",
        },
    ]
    pilot = {**pilot, "samples": expected_samples}

    with pytest.raises(ValueError, match="bundle sample set mismatch"):
        import_resolved_v2_bundles(
            db_path=db_path,
            campaign_manifest=campaign,
            pilot_manifest=pilot,
            images_root=images_root,
            bundle_paths=[bundle],
            expected_samples=expected_samples,
        )
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ocr_runs WHERE engine='sol'").fetchone()[0] == 0
