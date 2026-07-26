import logging
import time
from _ctypes import COMError
from collections.abc import Callable

import pyautogui
from PIL import Image

from .models import (
    BookCandidate,
    BookIdentity,
    KindleControllerError,
    parse_card_name,
    select_verified_candidate,
    visual_frames_differ,
)
from .window import WindowController

logger = logging.getLogger(__name__)


class LibraryControllerMixin(WindowController):
    def open_library(self) -> None:
        self._ensure_process_running()
        if self._search_edit(timeout=1.0) is not None:
            return
        back = self._control_by_id("backButton", timeout=2.0)
        if back is None:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleのライブラリ画面または戻る操作を取得できませんでした",
            )
        self._activate_control_with_keyboard(back)
        deadline = time.monotonic() + self.config.reader_timeout_seconds
        while time.monotonic() < deadline:
            self._ensure_process_running()
            if self._search_edit(timeout=1.0) is not None:
                return
            time.sleep(0.5)
        raise KindleControllerError(
            "kindle_ui_unavailable",
            "Kindleのライブラリ画面へ戻れませんでした",
        )

    def search_book(self, identity: BookIdentity) -> BookCandidate:
        self.open_library()
        self._set_search_value(identity.asin)
        time.sleep(self.config.screen_transition_seconds)
        return select_verified_candidate(identity, self.collect_candidates(identity))

    def _set_search_value(self, value: str) -> None:
        deadline = time.monotonic() + self.config.control_timeout_seconds
        while time.monotonic() < deadline:
            edit = self._search_edit(timeout=0.5)
            if edit is not None:
                try:
                    # UI Automation の矩形と pyautogui の座標系は、表示倍率が異なる
                    # マルチモニター環境で一致しない場合がある。値の設定自体は通常の
                    # キーボード入力を維持し、フォーカスだけを control へ直接渡す。
                    edit.SetFocus()
                    pyautogui.hotkey("ctrl", "a")
                    pyautogui.write(value, interval=0.02)
                    time.sleep(0.1)
                    if str(edit.GetValuePattern().Value) == value:
                        return
                except (AttributeError, COMError, TypeError, ValueError):
                    logger.debug(
                        "Kindle search field focus or value verification failed transiently",
                        exc_info=True,
                    )
            time.sleep(0.5)
        raise KindleControllerError(
            "kindle_ui_unavailable",
            "Kindleのライブラリ検索欄を更新・確認できませんでした",
        )

    def collect_candidates(self, identity: BookIdentity) -> list[BookCandidate]:
        """ASIN固有AutomationIdだけを最大2件探索し、曖昧性を検出する。"""
        automation_id = f"library-more-menu-{identity.asin}"
        candidates: list[BookCandidate] = []
        for found_index in (1, 2):
            menu = self._control_by_id(
                automation_id,
                timeout=self.config.control_timeout_seconds
                if found_index == 1
                else 1.0,
                found_index=found_index,
            )
            if menu is None:
                continue
            card = menu.GetParentControl()
            while card is not None and card.AutomationId != "library-item-container":
                card = card.GetParentControl()
            if card is None:
                raise KindleControllerError(
                    "kindle_ui_unavailable",
                    "対象書籍カードの操作領域を取得できませんでした",
                )
            title, authors = parse_card_name(card.Name)
            candidates.append(
                BookCandidate(
                    asin=identity.asin,
                    title=title,
                    authors=authors,
                    card=card,
                )
            )
        logger.info(
            "Kindle candidate search completed: asin_suffix=%s count=%d",
            identity.asin[-4:],
            len(candidates),
        )
        return candidates

    def needs_download(self, candidate: BookCandidate) -> bool:
        if not candidate.asin:
            raise KindleControllerError(
                "book_identity_unverified",
                "ASINを確認できない候補はダウンロードできません",
            )
        return (
            self._control_by_id(
                f"download-button-{candidate.asin}",
                timeout=1.0,
            )
            is not None
        )

    def _content_snapshot(self, asin: str) -> tuple[int, int, int] | None:
        content_dir = self.config.content_root / f"{asin}_EBOK"
        if not content_dir.is_dir():
            return None
        files = [path for path in content_dir.rglob("*") if path.is_file()]
        suffixes = {path.suffix.casefold() for path in files}
        if ".azw" not in suffixes or ".voucher" not in suffixes:
            return None
        stats = [path.stat() for path in files]
        if not stats or any(stat.st_size <= 0 for stat in stats):
            return None
        return (
            len(stats),
            sum(stat.st_size for stat in stats),
            max(stat.st_mtime_ns for stat in stats),
        )

    def wait_for_download(
        self,
        candidate: BookCandidate,
        *,
        on_poll: Callable[[], None] | None = None,
    ) -> None:
        if not candidate.asin:
            raise KindleControllerError(
                "book_identity_unverified",
                "ASINを確認できない候補はダウンロードできません",
            )
        automation_id = f"download-button-{candidate.asin}"
        button = self._control_by_id(automation_id, timeout=2.0)
        started = button is not None
        if button is not None and "キャンセル" not in button.Name:
            self._click_control(button)
            time.sleep(1.0)

        deadline = time.monotonic() + self.config.download_timeout_seconds
        last_snapshot: tuple[int, int, int] | None = None
        stable_count = 0
        saw_downloading = False
        while time.monotonic() < deadline:
            self._ensure_process_running()
            if on_poll:
                on_poll()
            current_button = self._control_by_id(automation_id, timeout=0.5)
            if current_button is not None:
                if "キャンセル" in current_button.Name:
                    saw_downloading = True
                elif saw_downloading:
                    raise KindleControllerError(
                        "download_failed",
                        "Kindleのダウンロードが完了前に停止しました",
                    )
                stable_count = 0
                last_snapshot = None
            else:
                snapshot = self._content_snapshot(candidate.asin)
                if snapshot is not None and snapshot == last_snapshot:
                    stable_count += 1
                elif snapshot is not None:
                    stable_count = 1
                else:
                    stable_count = 0
                last_snapshot = snapshot
                if stable_count >= self.config.download_stable_checks:
                    return
                if not started and snapshot is None:
                    raise KindleControllerError(
                        "download_failed",
                        "Kindleのダウンロード状態と正式コンテンツを確認できません",
                    )
            time.sleep(self.config.download_poll_seconds)
        raise KindleControllerError(
            "download_timeout",
            "Kindle書籍のダウンロードが期限内に完了しませんでした",
        )

    def open_book(self, candidate: BookCandidate) -> None:
        if candidate.card is None:
            raise KindleControllerError(
                "book_identity_unverified",
                "本人照合済みの書籍カードを取得できませんでした",
            )
        self._click_control(candidate.card)
        self.wait_for_reader_stable()

    def wait_for_reader_stable(self) -> None:
        deadline = time.monotonic() + self.config.reader_timeout_seconds
        previous_frame: Image.Image | None = None
        stable_count = 0
        while time.monotonic() < deadline:
            self._ensure_process_running()
            back = self._control_by_id("backButton", timeout=0.5)
            frame = self._reading_area_image(timeout=0.5)
            if back is not None and frame is not None:
                if previous_frame is not None and not visual_frames_differ(
                    previous_frame,
                    frame,
                ):
                    stable_count += 1
                else:
                    stable_count = 1
                previous_frame = frame
                if stable_count >= 2:
                    return
            time.sleep(0.5)
        raise KindleControllerError(
            "kindle_ui_unavailable",
            "Kindleの読書画面が安定しませんでした",
        )
