"""Kindle enrichment source fileの発見・parse・差分記録。"""

from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from utils.dt import jst_now

KINDLE_INFO_FILES = {
    "Kindle.UnifiedLibraryIndex.CustomerRelationshipIndex_FE.csv": "acquisition_dates",
    "Kindle.UnifiedLibraryIndex.CustomerGenres_FE.csv": "genres",
    "Kindle.UnifiedLibraryIndex.CustomerAuthorNameRelationship_FE.csv": "authors",
    "Kindle.SagaSeriesInfra.CollectionRightsDatastore.csv": "volumes",
    "Kindle.reading-insights-sessions_with_adjustments.csv": "reading",
    "whispersync.csv": "last_read",
    "Kindle.Devices.autoMarkAsRead.csv": "completed",
}
AUTOBUY_FILENAME = "kindle-series-autobuy.json"
_NA_VALUES = {"", "not available", "not applicable"}


def source_root() -> Path:
    raw = config.AMAZON_DATA_DIR
    if not raw:
        raise ValueError("AMAZON_DATA_DIR が設定されていません")
    root = Path(raw).resolve()
    if not root.is_dir():
        raise ValueError("設定された AMAZON_DATA_DIR が見つかりません")
    return root


def find_exact(filename: str) -> list[Path]:
    root = source_root()
    return sorted(
        (path.resolve() for path in root.rglob(filename) if path.is_file() and root in path.resolve().parents),
        key=lambda path: str(path).casefold(),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "cp932", "utf-8"):
        try:
            with path.open("r", encoding=encoding, newline="") as source:
                return list(csv.DictReader(source))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path.name} の文字コードを判定できません")


def clean(value: object) -> str | None:
    text = str(value or "").strip()
    return None if text.casefold() in _NA_VALUES else text


def timestamp(value: object) -> str | None:
    text = clean(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def record_file(
    conn: Any,
    kind: str,
    path: Path,
    digest: str,
    count: int,
) -> None:
    conn.execute(
        """
        INSERT INTO imported_files(
            source_kind,filename,sha256,imported_at,record_count,status
        ) VALUES (?,?,?,?,?,'success')
        """,
        (kind, path.name, digest, jst_now().isoformat(), count),
    )


def is_imported(conn: Any, kind: str, path: Path, digest: str) -> bool:
    return (
        conn.execute(
            """
            SELECT 1 FROM imported_files
            WHERE source_kind=? AND filename=? AND sha256=?
            """,
            (kind, path.name, digest),
        ).fetchone()
        is not None
    )
