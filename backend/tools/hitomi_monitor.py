"""hitomi.la NOZOMI 監視 CLI。

OS scheduler または手動操作から `python -m tools.hitomi_monitor` で単発実行する。
詳細は docs/design/詳細設計/機能別/hitomi新着監視設計書.md を参照。

終了コード:
  0: 全成功
  1: 部分失敗（一部作者で例外）
  2: 致命的失敗（state.json 等の I/O エラー）
  3: 別processが実行中
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

# backend/ をパス追加してパッケージ参照を解決
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import HITOMI_DATA_DIR as _hitomi_data_dir
from services.hitomi import arrival_store, metadata, notify, nozomi, process_lock, state_store, watchlist

DATA_DIR = Path(_hitomi_data_dir)
GALLERY_URL_TEMPLATE = "https://hitomi.la/galleries/{id}.html"


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def should_skip_artist(checked_at_str: str | None, threshold: datetime | None) -> bool:
    """`checked_at` が `threshold` より新しければスキップ判定 True。

    threshold が None（CLI 直接実行など）なら常に False。
    日付パース失敗時も False（安全側に倒して通常実行する）。
    """
    if threshold is None or not checked_at_str:
        return False
    try:
        checked = datetime.fromisoformat(checked_at_str)
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=UTC)
    return checked > threshold


def build_arrival_item(
    gallery_id: int,
    entry: watchlist.WatchlistEntry,
    meta: dict,
    *,
    now_iso: str | None = None,
) -> arrival_store.ArrivalItem:
    """ギャラリー ID + watchlist エントリ + メタから new_arrivals 用 item を組み立てる。"""
    files = meta.get("files") or []
    return {
        "id": gallery_id,
        "artist": entry["normalized"],
        "display_artist": entry["display_name"],
        "title": meta.get("title", ""),
        "language": meta.get("language", entry["language"]),
        "type": meta.get("type", ""),
        "page_count": len(files),
        "published_at": meta.get("date", ""),
        "discovered_at": now_iso or _now_iso(),
        "url": GALLERY_URL_TEMPLATE.format(id=gallery_id),
        "is_read": False,
    }


def _pending_gallery_ids(artist_state: state_store.ArtistState) -> list[int]:
    return [
        gallery_id
        for gallery_id in artist_state.get("pending_gallery_ids", [])
        if isinstance(gallery_id, int) and not isinstance(gallery_id, bool) and gallery_id > 0
    ]


def _fetch_artist_items(
    entry: watchlist.WatchlistEntry,
    candidate_ids: list[int],
    client: httpx.Client,
    key: str,
) -> tuple[list[arrival_store.ArrivalItem], list[str], list[int]]:
    new_items: list[arrival_store.ArrivalItem] = []
    errors: list[str] = []
    failed_ids: list[int] = []
    for gallery_id in candidate_ids:
        try:
            meta = metadata.fetch_metadata(gallery_id, client=client)
        except (nozomi.HitomiError, metadata.HitomiMetadataError) as e:
            msg = f"{key}: metadata fetch failed for id={gallery_id}: {e}"
            print(f"[hitomi_monitor] WARN: {msg}", file=sys.stderr)
            errors.append(msg)
            failed_ids.append(gallery_id)
            continue
        new_items.append(build_arrival_item(gallery_id, entry, meta))
    return new_items, errors, failed_ids


def _process_artist(
    entry: watchlist.WatchlistEntry,
    state: state_store.State,
    client: httpx.Client,
    *,
    threshold: datetime | None,
) -> tuple[list[arrival_store.ArrivalItem], list[str], int]:
    key = f"{entry['normalized']}:{entry['language']}"
    prev_artist = state.get("artists", {}).get(key, {})
    if should_skip_artist(prev_artist.get("checked_at"), threshold):
        print(f"[hitomi_monitor] {key}: skipped (recently checked)")
        return [], [], 1

    try:
        ids = nozomi.fetch_nozomi_head(
            entry["normalized"],
            entry["language"],
            count=20,
            client=client,
        )
    except nozomi.HitomiError as e:
        msg = f"{key}: NOZOMI fetch failed: {e}"
        print(f"[hitomi_monitor] WARN: {msg}", file=sys.stderr)
        return [], [msg], 0

    pending_ids = _pending_gallery_ids(prev_artist)
    if not ids and not pending_ids:
        print(f"[hitomi_monitor] {key}: NOZOMI is empty, skip")
        return [], [], 0

    prev_top = prev_artist.get("top_id")
    candidate_ids = list(dict.fromkeys([*nozomi.diff_unseen_ids(ids, prev_top), *pending_ids]))
    new_items, errors, failed_ids = _fetch_artist_items(entry, candidate_ids, client, key)
    next_artist_state: state_store.ArtistState = {
        "checked_at": _now_iso(),
        "pending_gallery_ids": failed_ids,
    }
    if ids:
        next_artist_state["top_id"] = ids[0]
    elif isinstance(prev_top, int):
        next_artist_state["top_id"] = prev_top
    state.setdefault("artists", {})[key] = next_artist_state
    print(
        f"[hitomi_monitor] {key}: top={next_artist_state.get('top_id')}, "
        f"new={len(new_items)}, pending={len(failed_ids)}"
    )
    return new_items, errors, 0


def _run_unlocked(
    data_dir: Path = DATA_DIR,
    *,
    threshold: datetime | None = None,
) -> int:
    """process間lock取得後の監視処理。

    Args:
        data_dir: backend/data/hitomi/ 相当のディレクトリ
        threshold: 指定すると `checked_at` が `threshold` より新しい作者をスキップする。
            None なら常に全作者を処理する（CLI / Task Scheduler 既定の挙動）。
    """
    print(f"[hitomi_monitor] start: data_dir={data_dir}, threshold={threshold}")

    try:
        state = state_store.load_state(data_dir)
        entries = watchlist.load_watchlist(data_dir)
        arrival_store.import_legacy_json(data_dir)
    except Exception as e:
        print(f"[hitomi_monitor] FATAL: 初期ロード失敗: {e}", file=sys.stderr)
        return 2

    if not entries:
        print("[hitomi_monitor] watchlist が空です。何もしません。")
        state["last_run_at"] = _now_iso()
        state["last_run_status"] = "ok"
        state["last_error"] = None
        state["last_run_stats"] = {"added": 0, "skipped": 0, "errors": 0}
        try:
            state_store.save_state(data_dir, state)
        except Exception as e:
            print(f"[hitomi_monitor] FATAL: state.json 書込失敗: {e}", file=sys.stderr)
            return 2
        notify.notify_run_result(added=0, skipped=0, errors=0)
        return 0

    errors: list[str] = []
    new_items: list[arrival_store.ArrivalItem] = []
    skipped = 0

    with httpx.Client(timeout=nozomi.DEFAULT_TIMEOUT) as client:
        for entry in entries:
            artist_items, artist_errors, artist_skipped = _process_artist(
                entry,
                state,
                client,
                threshold=threshold,
            )
            new_items.extend(artist_items)
            errors.extend(artist_errors)
            skipped += artist_skipped

    try:
        added = arrival_store.merge_new_items(new_items)
    except Exception as e:
        print(f"[hitomi_monitor] FATAL: arrivals 書込失敗: {e}", file=sys.stderr)
        return 2

    state["last_run_at"] = _now_iso()
    state["last_run_status"] = "partial" if errors else "ok"
    state["last_error"] = "; ".join(errors[:3]) if errors else None
    state["last_run_stats"] = {
        "added": added,
        "skipped": skipped,
        "errors": len(errors),
    }

    try:
        state_store.save_state(data_dir, state)
    except Exception as e:
        print(f"[hitomi_monitor] FATAL: state.json 書込失敗: {e}", file=sys.stderr)
        return 2

    print(f"[hitomi_monitor] done: 新着 {added} 件追加, {skipped} 件 skip, エラー {len(errors)} 件")
    notify.notify_run_result(added=added, skipped=skipped, errors=len(errors))
    return 1 if errors else 0


def main(
    data_dir: Path = DATA_DIR,
    *,
    threshold: datetime | None = None,
) -> int:
    """process間lockを取得して監視を1回実行する。"""
    try:
        with process_lock.monitor_process_lock(data_dir):
            return _run_unlocked(data_dir, threshold=threshold)
    except process_lock.MonitorAlreadyRunningError:
        print("[hitomi_monitor] already running", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"[hitomi_monitor] FATAL: lock操作失敗: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
