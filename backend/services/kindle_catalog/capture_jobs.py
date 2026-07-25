"""Linux 正本の Kindle キャプチャジョブと inbox 取込。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import config
from config import get_dirs_by_source
from services.kindle_catalog.connection import with_db
from services.meta_store import update_meta_locked
from utils.dt import jst_now
from utils.logger import get_logger

logger = get_logger(__name__)

ACTIVE_STATUSES = (
    "claimed",
    "locating_book",
    "downloading",
    "positioning",
    "waiting_user",
    "capturing",
    "awaiting_files",
)
_AGENT_TRANSITIONS = {
    "claimed": {"locating_book", "waiting_user", "failed"},
    "locating_book": {"downloading", "positioning", "failed"},
    "downloading": {"positioning", "failed"},
    "positioning": {"capturing", "failed"},
    "waiting_user": {"capturing", "failed"},
    "capturing": {"awaiting_files", "failed"},
    "awaiting_files": {"failed"},
}
_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _row_dict(row) -> dict:
    return dict(row)


def _job_with_identity(conn: sqlite3.Connection, job_id: str) -> dict:
    row = conn.execute(
        """
        SELECT
            cj.*,
            b.title,
            b.title_normalized,
            s.name AS series_name,
            bs.volume_number,
            bs.volume_label
        FROM capture_jobs cj
        JOIN books b ON b.asin=cj.asin
        LEFT JOIN book_series bs ON bs.asin=b.asin
        LEFT JOIN series s ON s.id=bs.series_id
        WHERE cj.id=?
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        raise ValueError("キャプチャジョブが見つかりません")
    job = _row_dict(row)
    authors = conn.execute(
        """
        SELECT a.name
        FROM book_authors ba
        JOIN authors a ON a.id=ba.author_id
        WHERE ba.asin=?
        ORDER BY ba.sort_order, ba.id
        """,
        (job["asin"],),
    ).fetchall()
    job["identity"] = {
        "asin": job["asin"],
        "title": job["title"],
        "title_normalized": job["title_normalized"],
        "authors": [author["name"] for author in authors],
        "series_name": job["series_name"],
        "volume_number": job["volume_number"],
        "volume_label": job["volume_label"],
    }
    return job


def _recover_stale(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    timeout_seconds: int,
) -> list[str]:
    if timeout_seconds <= 0:
        raise ValueError("heartbeat timeout は 1 秒以上で指定してください")
    cutoff = (now - timedelta(seconds=timeout_seconds)).isoformat()
    placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
    rows = conn.execute(
        f"""
        SELECT id
        FROM capture_jobs
        WHERE status IN ({placeholders})
          AND COALESCE(heartbeat_at, claimed_at, requested_at) < ?
        ORDER BY requested_at
        """,
        (*ACTIVE_STATUSES, cutoff),
    ).fetchall()
    job_ids = [row["id"] for row in rows]
    if not job_ids:
        return []
    completed_at = now.isoformat()
    conn.execute(
        f"""
        UPDATE capture_jobs SET
            status='failed',
            completed_at=?,
            error_code='agent_heartbeat_timeout',
            error_message='キャプチャエージェントの heartbeat が期限切れです'
        WHERE status IN ({placeholders})
          AND COALESCE(heartbeat_at, claimed_at, requested_at) < ?
        """,
        (completed_at, *ACTIVE_STATUSES, cutoff),
    )
    logger.warning("Recovered %d stale Kindle capture job(s)", len(job_ids))
    return job_ids


def create(asin: str, source: str, direction: str, expected_screens: int | None) -> dict:
    if source not in {"comic", "novel"}:
        raise ValueError("source は comic または novel です")
    if direction not in {"left", "right"}:
        raise ValueError("direction は left または right です")
    with with_db() as conn:
        book = conn.execute("SELECT asin FROM books WHERE asin=?", (asin,)).fetchone()
        if book is None:
            raise ValueError("指定 ASIN は Kindle カタログに存在しません")
        existing = conn.execute(
            """
            SELECT 1 FROM capture_jobs
            WHERE asin=? AND status IN (
                'queued','claimed','locating_book','downloading','positioning',
                'waiting_user','capturing','awaiting_files'
            )
            """,
            (asin,),
        ).fetchone()
        if existing:
            raise ValueError("この書籍には未完了のキャプチャジョブがあります")
        job_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO capture_jobs(
                id,asin,source,status,direction,expected_screens,requested_at
            ) VALUES (?,?,?,'queued',?,?,?)
            """,
            (job_id, asin, source, direction, expected_screens, jst_now().isoformat()),
        )
        row = conn.execute("SELECT * FROM capture_jobs WHERE id=?", (job_id,)).fetchone()
    return _row_dict(row)


def list_jobs(limit: int = 100) -> list[dict]:
    with with_db() as conn:
        rows = conn.execute(
            """
            SELECT cj.*, b.title
            FROM capture_jobs cj JOIN books b ON b.asin=cj.asin
            ORDER BY cj.requested_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_dict(row) for row in rows]


def claim(agent_id: str) -> dict | None:
    """transaction 内の条件付き UPDATE で次の1件だけを claim する。"""
    with with_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        now = jst_now()
        _recover_stale(
            conn,
            now=now,
            timeout_seconds=config.KINDLE_CAPTURE_HEARTBEAT_TIMEOUT_SEC,
        )
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        active = conn.execute(
            f"""
            SELECT id FROM capture_jobs
            WHERE agent_id=? AND status IN ({placeholders})
            """,
            (agent_id, *ACTIVE_STATUSES),
        ).fetchone()
        if active:
            conn.execute(
                "UPDATE capture_jobs SET heartbeat_at=? WHERE id=?",
                (now.isoformat(), active["id"]),
            )
            return _job_with_identity(conn, active["id"])
        queued = conn.execute(
            "SELECT id FROM capture_jobs WHERE status='queued' ORDER BY requested_at LIMIT 1"
        ).fetchone()
        if queued is None:
            return None
        now_value = now.isoformat()
        updated = conn.execute(
            """
            UPDATE capture_jobs
            SET status='claimed',agent_id=?,claimed_at=?,heartbeat_at=?
            WHERE id=? AND status='queued'
            """,
            (agent_id, now_value, now_value, queued["id"]),
        ).rowcount
        if updated != 1:
            return None
        return _job_with_identity(conn, queued["id"])


def heartbeat(job_id: str, agent_id: str) -> dict:
    """agent 所有の active job の heartbeat を更新する。"""
    with with_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status,agent_id FROM capture_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError("キャプチャジョブが見つかりません")
        if row["agent_id"] != agent_id:
            raise ValueError("このエージェントが claim したジョブではありません")
        if row["status"] not in ACTIVE_STATUSES:
            raise ValueError("heartbeat を更新できるジョブ状態ではありません")
        heartbeat_at = jst_now().isoformat()
        updated = conn.execute(
            """
            UPDATE capture_jobs SET heartbeat_at=?
            WHERE id=? AND agent_id=? AND status=?
            """,
            (heartbeat_at, job_id, agent_id, row["status"]),
        ).rowcount
        if updated != 1:
            raise ValueError("heartbeat の更新に失敗しました")
    return {
        "job_id": job_id,
        "status": row["status"],
        "heartbeat_at": heartbeat_at,
    }


def update_state(
    job_id: str,
    agent_id: str,
    state: str,
    *,
    captured_screens: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict:
    if captured_screens is not None and captured_screens < 0:
        raise ValueError("captured_screens は 0 以上で指定してください")
    if state == "failed" and not error_code:
        raise ValueError("failed への遷移には error_code が必要です")
    with with_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM capture_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("キャプチャジョブが見つかりません")
        if row["agent_id"] != agent_id:
            raise ValueError("このエージェントが claim したジョブではありません")
        if state not in _AGENT_TRANSITIONS.get(row["status"], set()):
            raise ValueError(f"許可されていない状態遷移です: {row['status']} -> {state}")
        now = jst_now().isoformat()
        started_at = now if state == "capturing" else row["started_at"]
        completed_at = now if state == "failed" else row["completed_at"]
        screen_count = row["captured_screens"] if captured_screens is None else captured_screens
        updated_count = conn.execute(
            """
            UPDATE capture_jobs SET
                status=?,started_at=?,completed_at=?,captured_screens=?,
                error_code=?,error_message=?,heartbeat_at=?
            WHERE id=? AND agent_id=? AND status=?
            """,
            (
                state,
                started_at,
                completed_at,
                screen_count,
                error_code,
                error_message,
                now,
                job_id,
                agent_id,
                row["status"],
            ),
        ).rowcount
        if updated_count != 1:
            raise ValueError("キャプチャジョブの状態更新に失敗しました")
        updated = conn.execute("SELECT * FROM capture_jobs WHERE id=?", (job_id,)).fetchone()
    return _row_dict(updated)


def _safe_title(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip().rstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("書籍タイトルを安全な保存名へ変換できません")
    return cleaned[:180]


def _validate_ready_dir(job: dict, ready_dir: Path) -> tuple[dict, list[Path]]:
    if not ready_dir.is_dir() or ready_dir.is_symlink():
        raise ValueError("完了済み capture package が見つかりません")
    manifest_path = ready_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("manifest.json がありません")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("job_id", "asin", "source", "files"):
        if key not in manifest:
            raise ValueError(f"manifest の必須項目がありません: {key}")
    if manifest["job_id"] != job["id"] or manifest["asin"] != job["asin"] or manifest["source"] != job["source"]:
        raise ValueError("manifest とキャプチャジョブが一致しません")
    declared = manifest["files"]
    if not isinstance(declared, list) or not 1 <= len(declared) <= config.ZIP_MAX_ENTRIES:
        raise ValueError("manifest のファイル件数が不正です")
    image_dir = ready_dir / "images"
    if not image_dir.is_dir() or image_dir.is_symlink():
        raise ValueError("images ディレクトリがありません")
    files: list[Path] = []
    total_size = 0
    declared_names: set[str] = set()
    for item in declared:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("manifest files の形式が不正です")
        name = item["name"]
        if Path(name).name != name or Path(name).suffix.casefold() not in _ALLOWED_EXTENSIONS:
            raise ValueError("許可されていない画像ファイル名です")
        file_path = image_dir / name
        if not file_path.is_file() or file_path.is_symlink():
            raise ValueError("manifest に記載された画像がありません")
        size = file_path.stat().st_size
        if size > config.ZIP_MAX_PER_FILE_BYTES:
            raise ValueError("画像ファイルのサイズ上限を超えています")
        total_size += size
        if total_size > config.ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError("capture package の合計サイズ上限を超えています")
        expected_hash = item.get("sha256")
        if expected_hash:
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError("画像ファイルの SHA-256 が一致しません")
        declared_names.add(name)
        files.append(file_path)
    actual_names = {
        path.name for path in image_dir.iterdir() if path.is_file() and path.suffix.casefold() in _ALLOWED_EXTENSIONS
    }
    if actual_names != declared_names:
        raise ValueError("manifest と images のファイル一覧が一致しません")
    return manifest, files


def complete(job_id: str, agent_id: str) -> dict:
    """`<job_id>.ready` を検証し、正式領域へ atomic publish する。"""
    inbox = Path(config.KINDLE_CAPTURE_INBOX_DIR)
    ready_dir = inbox / f"{job_id}.ready"
    with with_db() as conn:
        row = conn.execute(
            """
            SELECT cj.*, b.title
            FROM capture_jobs cj JOIN books b ON b.asin=cj.asin
            WHERE cj.id=?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError("キャプチャジョブが見つかりません")
        job = _row_dict(row)
    if job["agent_id"] != agent_id or job["status"] != "awaiting_files":
        raise ValueError("完了報告できるジョブ状態ではありません")
    _manifest, files = _validate_ready_dir(job, ready_dir)

    title = _safe_title(job["title"])
    target_base = Path(get_dirs_by_source(job["source"])["img"]).resolve()
    target_base.mkdir(parents=True, exist_ok=True)
    target = (target_base / title).resolve()
    if not target.is_relative_to(target_base):
        raise ValueError("正式配置先が不正です")
    if target.exists():
        raise ValueError("同名の Pic2PDFViewer 画像書籍が既にあります")
    staging = target_base / f".{job_id}.partial"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    processed_dir = inbox / "processed"
    processed_package = processed_dir / job_id
    archived = False
    previous_meta_entry: dict | None = None
    try:
        for source_file in files:
            shutil.copy2(source_file, staging / source_file.name)
        os.replace(staging, target)

        book_id = f"{title}.pdf"

        def _apply(data):
            nonlocal previous_meta_entry
            previous_meta_entry = deepcopy(data.get(book_id))
            entry = data.setdefault(book_id, {"authors": []})
            entry["asin"] = job["asin"]

        update_meta_locked(job["source"], _apply)
        processed_dir.mkdir(parents=True, exist_ok=True)
        if processed_package.exists():
            raise ValueError("同じジョブの処理済み package が既にあります")
        os.replace(ready_dir, processed_package)
        archived = True
        with with_db() as conn:
            completed_at = jst_now().isoformat()
            updated = conn.execute(
                """
                UPDATE capture_jobs SET
                    status='succeeded',completed_at=?,heartbeat_at=?,
                    book_id=?,captured_screens=?
                WHERE id=? AND status='awaiting_files' AND agent_id=?
                """,
                (
                    completed_at,
                    completed_at,
                    book_id,
                    len(files),
                    job_id,
                    agent_id,
                ),
            ).rowcount
            if updated != 1:
                raise ValueError("キャプチャジョブの完了更新に失敗しました")
    except Exception:
        if previous_meta_entry is not None or target.is_dir():

            def _restore(data):
                if previous_meta_entry is None:
                    data.pop(book_id, None)
                else:
                    data[book_id] = previous_meta_entry

            update_meta_locked(job["source"], _restore)
        if archived and processed_package.exists() and not ready_dir.exists():
            os.replace(processed_package, ready_dir)
        if staging.is_dir():
            shutil.rmtree(staging)
        if target.is_dir():
            shutil.rmtree(target)
        raise
    return {
        "job_id": job_id,
        "status": "succeeded",
        "source": job["source"],
        "book_id": book_id,
        "captured_screens": len(files),
    }
