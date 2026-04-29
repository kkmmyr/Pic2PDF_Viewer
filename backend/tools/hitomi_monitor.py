"""hitomi.la NOZOMI 監視 CLI。

Windows Task Scheduler から `python -m tools.hitomi_monitor` で単発実行する。
詳細は docs/03_詳細設計/hitomi新着監視設計書.md §10 を参照。

終了コード:
  0: 全成功
  1: 部分失敗（一部作者で例外）
  2: 致命的失敗（state.json 等の I/O エラー）
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# backend/ をパス追加してパッケージ参照を解決
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.hitomi import metadata, nozomi, state_store, watchlist  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "hitomi"
GALLERY_URL_TEMPLATE = "https://hitomi.la/galleries/{id}.html"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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
        checked = checked.replace(tzinfo=timezone.utc)
    return checked > threshold


def build_arrival_item(
    gallery_id: int,
    entry: watchlist.WatchlistEntry,
    meta: dict,
    *,
    now_iso: str | None = None,
) -> state_store.ArrivalItem:
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
        "dismissed": False,
    }


def main(
    data_dir: Path = DATA_DIR,
    *,
    min_age_hours: float | None = None,
) -> int:
    """監視スクリプトのエントリポイント。

    Args:
        data_dir: backend/data/hitomi/ 相当のディレクトリ
        min_age_hours: 指定すると `checked_at` が `now - min_age_hours` より
            新しい作者をスキップする。None なら常に全作者を処理する（CLI / Task
            Scheduler 既定の挙動）。
    """
    print(f"[hitomi_monitor] start: data_dir={data_dir}, min_age_hours={min_age_hours}")

    try:
        state = state_store.load_state(data_dir)
        entries = watchlist.load_watchlist(data_dir)
    except Exception as e:
        print(f"[hitomi_monitor] FATAL: 初期ロード失敗: {e}", file=sys.stderr)
        return 2

    threshold: datetime | None = None
    if min_age_hours is not None and min_age_hours > 0:
        threshold = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)

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
        return 0

    errors: list[str] = []
    new_items: list[state_store.ArrivalItem] = []
    skipped = 0

    for entry in entries:
        key = f"{entry['normalized']}:{entry['language']}"

        # 直近取得済みならスキップ（state.artists[key] を更新しない）
        prev_artist = state.get("artists", {}).get(key, {})
        if should_skip_artist(prev_artist.get("checked_at"), threshold):
            print(f"[hitomi_monitor] {key}: skipped (recently checked)")
            skipped += 1
            continue

        try:
            ids = nozomi.fetch_nozomi_head(
                entry["normalized"], entry["language"], count=20
            )
        except nozomi.HitomiError as e:
            msg = f"{key}: NOZOMI fetch failed: {e}"
            print(f"[hitomi_monitor] WARN: {msg}", file=sys.stderr)
            errors.append(msg)
            continue

        if not ids:
            print(f"[hitomi_monitor] {key}: NOZOMI is empty, skip")
            continue

        prev_top = prev_artist.get("top_id")
        unseen = nozomi.diff_unseen_ids(ids, prev_top)

        new_for_artist = 0
        for gid in unseen:
            try:
                meta = metadata.fetch_metadata(gid)
            except (nozomi.HitomiError, metadata.HitomiMetadataError) as e:
                msg = f"{key}: metadata fetch failed for id={gid}: {e}"
                print(f"[hitomi_monitor] WARN: {msg}", file=sys.stderr)
                errors.append(msg)
                continue
            new_items.append(build_arrival_item(gid, entry, meta))
            new_for_artist += 1

        state.setdefault("artists", {})[key] = {
            "top_id": ids[0],
            "checked_at": _now_iso(),
        }
        print(f"[hitomi_monitor] {key}: top={ids[0]}, new={new_for_artist}")

    try:
        added = state_store.merge_new_items(data_dir, new_items)
        purged = state_store.purge_expired(data_dir, threshold_days=30)
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

    print(
        f"[hitomi_monitor] done: 新着 {added} 件追加, "
        f"{purged} 件 purge, {skipped} 件 skip, エラー {len(errors)} 件"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
