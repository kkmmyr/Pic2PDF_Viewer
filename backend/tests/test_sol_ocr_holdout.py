from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from services.novel_db.sol_ocr_holdout import (
    B35_SCHEMA_VERSION,
    CAMPAIGN_SCHEMA_VERSION,
    PILOT_SCHEMA_VERSION,
    canonical_sha256,
    create_formal_holdout_manifest,
    export_formal_holdout_images,
    load_formal_holdout_manifest,
    open_formal_holdout,
    record_sealed_manifest,
    retire_formal_holdout_to_tuning,
    verify_formal_holdout_manifest,
)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _campaign(tmp_path: Path) -> tuple[Path, dict]:
    books = []
    for canonical in (False, True):
        for book_index in range(4):
            name = f"{'canonical' if canonical else 'image'}-{book_index}"
            pages = [
                {
                    "page_no": page_no,
                    "image_path": f"{name}/{page_no:03d}.png",
                    "image_sha256": f"{(book_index * 20 + page_no + (100 if canonical else 0)):064x}",
                    "size_bytes": 1,
                }
                for page_no in range(1, 11)
            ]
            books.append(
                {
                    "book_name": name,
                    "page_count": len(pages),
                    "canonical_page_count": len(pages) if canonical else 0,
                    "has_canonical_ocr": canonical,
                    "pages": pages,
                }
            )
    body = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_id": "sol-test",
        "books": books,
        "summary": {},
        "partitions": [],
    }
    campaign = {**body, "manifest_sha256": canonical_sha256(body)}
    path = tmp_path / "campaign.json"
    _write_json(path, campaign)
    return path, campaign


def _pilot(tmp_path: Path, campaign: dict) -> tuple[Path, dict]:
    image = campaign["books"][0]["pages"][4]
    body = {
        "schema_version": PILOT_SCHEMA_VERSION,
        "campaign_id": campaign["campaign_id"],
        "manifest_sha256": campaign["manifest_sha256"],
        "samples": [
            {
                "sample_id": "pilot-001",
                "book_name": "image-0",
                "page_no": 5,
                "image_sha256": image["image_sha256"],
            }
        ],
    }
    pilot = {**body, "pilot_sha256": canonical_sha256(body)}
    path = tmp_path / "pilot.json"
    _write_json(path, pilot)
    return path, pilot


def _b35(tmp_path: Path, campaign: dict) -> tuple[Path, dict]:
    image = campaign["books"][4]["pages"][5]
    body = {
        "schema_version": B35_SCHEMA_VERSION,
        "holdout_id": "b35",
        "purpose": "b35_final",
        "state": "sealed",
        "entries": [{"entry_id": 1, "page_no": 6, "image_sha256": image["image_sha256"]}],
    }
    b35 = {**body, "manifest_sha256": canonical_sha256(body)}
    path = tmp_path / "b35.json"
    _write_json(path, b35)
    return path, b35


def _create(tmp_path: Path) -> tuple[dict, Path, Path, Path]:
    campaign_path, campaign = _campaign(tmp_path)
    pilot_path, _ = _pilot(tmp_path, campaign)
    b35_path, _ = _b35(tmp_path, campaign)
    output_path = tmp_path / "fresh.json"
    manifest = create_formal_holdout_manifest(
        campaign_manifest_path=campaign_path,
        pilot_manifest_paths=[pilot_path],
        b35_manifest_path=b35_path,
        output_path=output_path,
        holdout_id="sol-fresh-v1",
        seed="seed-v1",
        prompt_sha256="a" * 64,
        policy_sha256="b" * 64,
        canonical_books=2,
        image_only_books=2,
        sealed_at="2026-08-20T00:00:00+00:00",
    )
    return manifest, campaign_path, pilot_path, b35_path


def test_fresh_holdout_is_deterministic_quality_blind_and_excludes_prior_samples(tmp_path: Path) -> None:
    first, campaign_path, pilot_path, b35_path = _create(tmp_path)
    second = create_formal_holdout_manifest(
        campaign_manifest_path=campaign_path,
        pilot_manifest_paths=[pilot_path],
        b35_manifest_path=b35_path,
        output_path=tmp_path / "fresh-second.json",
        holdout_id="sol-fresh-v1",
        seed="seed-v1",
        prompt_sha256="a" * 64,
        policy_sha256="b" * 64,
        canonical_books=2,
        image_only_books=2,
        sealed_at="2026-08-20T00:00:00+00:00",
    )

    assert first == second
    assert [sample["group"] for sample in first["samples"]].count("canonical") == 2
    assert [sample["group"] for sample in first["samples"]].count("image_only") == 2
    assert len({sample["book_name"] for sample in first["samples"]}) == 4
    assert all(2 <= sample["page_no"] <= 8 for sample in first["samples"])
    assert ("image-0", 5) not in {(sample["book_name"], sample["page_no"]) for sample in first["samples"]}
    b35_sha = json.loads(b35_path.read_text(encoding="utf-8"))["entries"][0]["image_sha256"]
    assert b35_sha not in {sample["image_sha256"] for sample in first["samples"]}
    assert (
        verify_formal_holdout_manifest(
            first,
            campaign_manifest_path=campaign_path,
            pilot_manifest_paths=[pilot_path],
            b35_manifest_path=b35_path,
        )["sample_count"]
        == 4
    )
    assert load_formal_holdout_manifest(tmp_path / "fresh.json") == first


def test_fresh_holdout_rejects_manifest_or_exclusion_tampering(tmp_path: Path) -> None:
    manifest, campaign_path, pilot_path, b35_path = _create(tmp_path)
    tampered = {**manifest, "seed": "changed"}
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_formal_holdout_manifest(
            tampered,
            campaign_manifest_path=campaign_path,
            pilot_manifest_paths=[pilot_path],
            b35_manifest_path=b35_path,
        )

    b35 = json.loads(b35_path.read_text(encoding="utf-8"))
    b35["entries"][0]["image_sha256"] = "f" * 64
    _write_json(b35_path, b35)
    with pytest.raises(ValueError, match="B-35 formal manifest digest mismatch"):
        verify_formal_holdout_manifest(
            manifest,
            campaign_manifest_path=campaign_path,
            pilot_manifest_paths=[pilot_path],
            b35_manifest_path=b35_path,
        )

    with pytest.raises(ValueError, match="B-35 formal manifest is missing"):
        create_formal_holdout_manifest(
            campaign_manifest_path=campaign_path,
            pilot_manifest_paths=[pilot_path],
            b35_manifest_path=tmp_path / "absent-b35.json",
            output_path=tmp_path / "never.json",
            holdout_id="no-b35",
            seed="seed-v1",
            prompt_sha256="a" * 64,
            policy_sha256="b" * 64,
            canonical_books=1,
            image_only_books=1,
            sealed_at="2026-08-20T00:00:00+00:00",
        )


def test_fresh_holdout_ledger_is_one_way_and_rejects_reopen(tmp_path: Path) -> None:
    manifest, _, _, _ = _create(tmp_path)
    ledger_path = tmp_path / "ledger.json"
    record_sealed_manifest(ledger_path, manifest, operator="tester", occurred_at="2026-08-20T00:00:01+00:00")
    open_formal_holdout(
        ledger_path,
        manifest,
        operator="tester",
        reason="one-time formal evaluation",
        occurred_at="2026-08-20T00:00:02+00:00",
    )
    with pytest.raises(ValueError, match="already opened"):
        open_formal_holdout(ledger_path, manifest, operator="tester", reason="retry")
    retire_formal_holdout_to_tuning(
        ledger_path,
        manifest,
        operator="tester",
        reason="quality gate failed",
        occurred_at="2026-08-20T00:00:03+00:00",
    )
    with pytest.raises(ValueError, match="already retired"):
        retire_formal_holdout_to_tuning(ledger_path, manifest, operator="tester", reason="retry")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert [event["state"] for event in ledger["events"]] == ["sealed", "opened", "retired_to_tuning"]


def test_fresh_holdout_export_requires_opened_ledger_and_revalidates_images(tmp_path: Path) -> None:
    campaign_path, campaign = _campaign(tmp_path)
    images_root = tmp_path / "images"
    for book in campaign["books"]:
        for page in book["pages"]:
            payload = f"{book['book_name']}:{page['page_no']}".encode()
            image_path = images_root / page["image_path"]
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(payload)
            page["image_sha256"] = hashlib.sha256(payload).hexdigest()
    campaign_body = {key: value for key, value in campaign.items() if key != "manifest_sha256"}
    campaign = {**campaign_body, "manifest_sha256": canonical_sha256(campaign_body)}
    _write_json(campaign_path, campaign)
    pilot_path, _ = _pilot(tmp_path, campaign)
    b35_path, _ = _b35(tmp_path, campaign)
    manifest = create_formal_holdout_manifest(
        campaign_manifest_path=campaign_path,
        pilot_manifest_paths=[pilot_path],
        b35_manifest_path=b35_path,
        output_path=tmp_path / "fresh.json",
        holdout_id="sol-fresh-export-v1",
        seed="seed-v1",
        prompt_sha256="a" * 64,
        policy_sha256="b" * 64,
        canonical_books=2,
        image_only_books=2,
        sealed_at="2026-08-20T00:00:00+00:00",
    )
    ledger_path = tmp_path / "ledger.json"
    output_tar = tmp_path / "holdout.tar"

    with pytest.raises(ValueError, match="must be opened"):
        export_formal_holdout_images(
            manifest=manifest,
            ledger_path=ledger_path,
            images_root=images_root,
            output_tar=output_tar,
        )

    record_sealed_manifest(ledger_path, manifest, operator="tester")
    open_formal_holdout(ledger_path, manifest, operator="tester", reason="formal evaluation")
    export_formal_holdout_images(
        manifest=manifest,
        ledger_path=ledger_path,
        images_root=images_root,
        output_tar=output_tar,
    )
    with tarfile.open(output_tar) as archive:
        assert sorted(member.name for member in archive.getmembers()) == sorted(
            f"images/{sample['image_path']}" for sample in manifest["samples"]
        )

    retire_formal_holdout_to_tuning(ledger_path, manifest, operator="tester", reason="done")
    with pytest.raises(ValueError, match="must be opened"):
        export_formal_holdout_images(
            manifest=manifest,
            ledger_path=ledger_path,
            images_root=images_root,
            output_tar=tmp_path / "second.tar",
        )
