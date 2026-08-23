from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from services.novel_db.codex_reviewed_ocr import (
    IMPORTED_ENGINE,
    export_reviewed_run,
    load_reviewed_package,
    write_reviewed_package,
)
from services.novel_db.codex_reviewed_ocr_import import import_reviewed_package
from services.novel_db.connection import with_db
from services.novel_db.migrations import upgrade_head
from services.novel_db.ocr_qa_publication import approve_and_publish_run
from services.novel_db.qwen_dots_worker import (
    COMPOSITE_MODEL_REVISION,
    DOTS_ENGINE_VERSION,
    DOTS_MODEL_REVISION,
    DOTS_PROMPT_ID,
    DOTS_PROMPT_SHA256,
    QWEN_ENGINE_VERSION,
    QWEN_MODEL_REVISION,
    QWEN_PROMPT_ID,
    QWEN_PROMPT_SHA256,
)


def _raw_envelope(primary_text: str, external_text: str, selection_reason: str) -> str:
    return json.dumps(
        {
            "schema": "qwen35-dots-page-v1",
            "selection_reason": selection_reason,
            "primary": {
                "text": primary_text,
                "raw_output": "<div>primary raw</div>",
                "provenance": {
                    "model_revision": QWEN_MODEL_REVISION,
                    "model_fingerprint": "a" * 64,
                    "engine_version": QWEN_ENGINE_VERSION,
                    "prompt_id": QWEN_PROMPT_ID,
                    "prompt_sha256": QWEN_PROMPT_SHA256,
                },
            },
            "external": {
                "text": external_text,
                "raw_output": "[]",
                "provenance": {
                    "model_revision": DOTS_MODEL_REVISION,
                    "model_fingerprint": "c" * 64,
                    "engine_version": DOTS_ENGINE_VERSION,
                    "prompt_id": DOTS_PROMPT_ID,
                    "prompt_sha256": DOTS_PROMPT_SHA256,
                },
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _resign(package: dict) -> None:
    unsigned = {key: value for key, value in package.items() if key != "package_sha256"}
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    package["package_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()


def _seed_reviewed_run(tmp_data_dir) -> tuple[Path, Path, int, str]:
    upgrade_head()
    db_path = Path(tmp_data_dir["NOVEL_DB_PATH"])
    images_root = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"])
    book_name = "Codex reviewed book"
    book_dir = images_root / book_name
    book_dir.mkdir(parents=True)
    image_hashes: list[str] = []
    for page_no, color in ((1, "white"), (2, "gray")):
        image_path = book_dir / f"{page_no:03}.png"
        Image.new("RGB", (20, 30), color).save(image_path)
        image_hashes.append(hashlib.sha256(image_path.read_bytes()).hexdigest())

    with with_db() as conn, conn:
        book_id = int(
            conn.execute(
                "INSERT INTO books (name, pdf_path, images_dir, page_count, ocr_done_at) "
                "VALUES (?, '', ?, 2, datetime('now', '+9 hours'))",
                (book_name, str(book_dir)),
            ).lastrowid
        )
        conn.execute(
            "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count, page_type, index_eligible) "
            "VALUES (?, 1, ?, '旧本文一', 4, 'narrative', 1)",
            (book_id, str(book_dir / "001.png")),
        )
        conn.execute(
            "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count, page_type, index_eligible) "
            "VALUES (?, 2, ?, '', 0, 'illustration', 0)",
            (book_id, str(book_dir / "002.png")),
        )
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
        run_id = int(
            conn.execute(
                "INSERT INTO ocr_runs "
                "(book_name, engine, model, source_page_count, state, qa_state) "
                "VALUES (?, 'qwen35_dots_review_v1', ?, 2, 'awaiting_qa', 'pending')",
                (book_name, COMPOSITE_MODEL_REVISION),
            ).lastrowid
        )
        page_rows = [
            (
                1,
                image_hashes[0],
                "候補本文",
                _raw_envelope("候補本文", "別候補本文", "qwen_clean"),
                json.dumps(["review_assisted_composite", "selection_reason:qwen_clean"]),
                "approved",
                None,
                "narrative",
                1,
                "normal_prose",
                "候補本文",
                "別候補本文",
                "codex",
                "補正本文",
                "qwen_clean",
            ),
            (
                2,
                image_hashes[1],
                "",
                _raw_envelope("", "", "dots_image_only_review_required"),
                json.dumps(
                    [
                        "review_assisted_composite",
                        "selection_reason:dots_image_only_review_required",
                    ]
                ),
                "not_required",
                None,
                "illustration",
                0,
                "image_only",
                "",
                "",
                "external",
                None,
                "dots_image_only_review_required",
            ),
        ]
        for row in page_rows:
            conn.execute(
                "INSERT INTO ocr_page_results "
                "(run_id, page_no, image_sha256, state, full_text, char_count, raw_output, block_count, "
                "quality_flags_json, attempt_count, qa_state, qa_note, reviewed_at, page_type, index_eligible, "
                "layout_type, primary_text, external_text, selected_engine, corrected_text, selection_reason) "
                "VALUES (?, ?, ?, 'passed', ?, ?, ?, 0, ?, 2, ?, ?, datetime('now', '+9 hours'), ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    row[0],
                    row[1],
                    row[2],
                    len(row[2]),
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                    row[8],
                    row[9],
                    row[10],
                    row[11],
                    row[12],
                    row[13],
                    row[14],
                ),
            )
    return db_path, images_root, run_id, book_name


def _canonical_rows(book_name: str) -> list[tuple]:
    with with_db() as conn:
        rows = conn.execute(
            "SELECT p.page_no, p.full_text, p.page_type, p.index_eligible "
            "FROM pages p JOIN books b ON b.id=p.book_id WHERE b.name=? ORDER BY p.page_no",
            (book_name,),
        ).fetchall()
    return [tuple(row) for row in rows]


def test_reviewed_package_round_trip_is_idempotent_and_uses_existing_publication(tmp_data_dir, tmp_path: Path) -> None:
    db_path, images_root, source_run_id, book_name = _seed_reviewed_run(tmp_data_dir)
    before = _canonical_rows(book_name)
    package = export_reviewed_run(
        db_path=db_path,
        run_id=source_run_id,
        reviewer="codex",
        review_note="Codex source images and candidate differences reviewed",
    )
    package_path = tmp_path / "reviewed-package.json"
    write_reviewed_package(package_path, package)
    assert package["pages"][0]["qa_note"].startswith("owner image review accepted;")
    assert [page["review_method"] for page in package["pages"]] == ["owner_image_review", "machine_audit"]

    first = import_reviewed_package(
        db_path=db_path,
        images_root=images_root,
        package=load_reviewed_package(package_path),
    )
    second = import_reviewed_package(db_path=db_path, images_root=images_root, package=package)
    assert (first["inserted"], first["idempotent"]) == (2, 0)
    assert (second["run_id"], second["inserted"], second["idempotent"]) == (first["run_id"], 0, 2)
    assert _canonical_rows(book_name) == before

    with with_db() as conn:
        imported = conn.execute(
            "SELECT engine, state, qa_state FROM ocr_runs WHERE id=?",
            (first["run_id"],),
        ).fetchone()
    assert tuple(imported) == (IMPORTED_ENGINE, "awaiting_qa", "pending")

    approve_and_publish_run(first["run_id"], "codex", "reviewed package publication")
    assert _canonical_rows(book_name) == [(1, "補正本文", "narrative", 1), (2, "", "illustration", 0)]


def test_reviewed_package_rejects_tampering_before_database_changes(tmp_data_dir) -> None:
    db_path, images_root, source_run_id, _book_name = _seed_reviewed_run(tmp_data_dir)
    package = export_reviewed_run(
        db_path=db_path,
        run_id=source_run_id,
        reviewer="codex",
        review_note="reviewed",
    )
    package["pages"][0]["corrected_text"] = "改変本文"

    with pytest.raises(ValueError, match="package digest mismatch"):
        import_reviewed_package(db_path=db_path, images_root=images_root, package=package)
    with with_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM ocr_runs WHERE engine=?", (IMPORTED_ENGINE,)).fetchone()[0]
    assert count == 0


def test_reviewed_package_rejects_changed_production_image_before_database_changes(tmp_data_dir) -> None:
    db_path, images_root, source_run_id, book_name = _seed_reviewed_run(tmp_data_dir)
    package = export_reviewed_run(
        db_path=db_path,
        run_id=source_run_id,
        reviewer="codex",
        review_note="reviewed",
    )
    Image.new("RGB", (20, 30), "black").save(images_root / book_name / "001.png")

    with pytest.raises(ValueError, match="production image SHA-256 mismatch: page 1"):
        import_reviewed_package(db_path=db_path, images_root=images_root, package=package)
    with with_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM ocr_runs WHERE engine=?", (IMPORTED_ENGINE,)).fetchone()[0]
    assert count == 0


def test_reviewed_package_rejects_missing_page_even_with_recomputed_digest(tmp_data_dir) -> None:
    db_path, images_root, source_run_id, _book_name = _seed_reviewed_run(tmp_data_dir)
    package = export_reviewed_run(
        db_path=db_path,
        run_id=source_run_id,
        reviewer="codex",
        review_note="reviewed",
    )
    package["pages"].pop()
    _resign(package)

    with pytest.raises(ValueError, match="page count mismatch"):
        import_reviewed_package(db_path=db_path, images_root=images_root, package=package)
    with with_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM ocr_runs WHERE engine=?", (IMPORTED_ENGINE,)).fetchone()[0]
    assert count == 0


def test_reviewed_package_rejects_prompt_mismatch_even_with_recomputed_digest(tmp_data_dir) -> None:
    db_path, images_root, source_run_id, _book_name = _seed_reviewed_run(tmp_data_dir)
    package = export_reviewed_run(
        db_path=db_path,
        run_id=source_run_id,
        reviewer="codex",
        review_note="reviewed",
    )
    envelope = json.loads(package["pages"][0]["raw_output"])
    envelope["primary"]["provenance"]["prompt_sha256"] = "e" * 64
    package["pages"][0]["raw_output"] = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    _resign(package)

    with pytest.raises(ValueError, match="primary prompt_sha256 mismatch"):
        import_reviewed_package(db_path=db_path, images_root=images_root, package=package)
    with with_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM ocr_runs WHERE engine=?", (IMPORTED_ENGINE,)).fetchone()[0]
    assert count == 0


def test_reviewed_package_rejects_mixed_model_fingerprints(tmp_data_dir) -> None:
    db_path, images_root, source_run_id, _book_name = _seed_reviewed_run(tmp_data_dir)
    package = export_reviewed_run(
        db_path=db_path,
        run_id=source_run_id,
        reviewer="codex",
        review_note="reviewed",
    )
    envelope = json.loads(package["pages"][1]["raw_output"])
    envelope["external"]["provenance"]["model_fingerprint"] = "f" * 64
    package["pages"][1]["raw_output"] = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    _resign(package)

    with pytest.raises(ValueError, match="mixes model fingerprints"):
        import_reviewed_package(db_path=db_path, images_root=images_root, package=package)
    with with_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM ocr_runs WHERE engine=?", (IMPORTED_ENGINE,)).fetchone()[0]
    assert count == 0


def test_reviewed_export_rejects_unresolved_page(tmp_data_dir) -> None:
    db_path, _images_root, source_run_id, _book_name = _seed_reviewed_run(tmp_data_dir)
    with with_db() as conn, conn:
        conn.execute(
            "UPDATE ocr_page_results SET qa_state='required' WHERE run_id=? AND page_no=1",
            (source_run_id,),
        )

    with pytest.raises(ValueError, match="unresolved QA state"):
        export_reviewed_run(
            db_path=db_path,
            run_id=source_run_id,
            reviewer="codex",
            review_note="reviewed",
        )


def test_reviewed_import_rejects_second_pending_package(tmp_data_dir) -> None:
    db_path, images_root, source_run_id, _book_name = _seed_reviewed_run(tmp_data_dir)
    first_package = export_reviewed_run(
        db_path=db_path,
        run_id=source_run_id,
        reviewer="codex",
        review_note="first review",
    )
    second_package = export_reviewed_run(
        db_path=db_path,
        run_id=source_run_id,
        reviewer="codex",
        review_note="second review",
    )
    import_reviewed_package(db_path=db_path, images_root=images_root, package=first_package)

    with pytest.raises(ValueError, match="already awaiting publication"):
        import_reviewed_package(db_path=db_path, images_root=images_root, package=second_package)
