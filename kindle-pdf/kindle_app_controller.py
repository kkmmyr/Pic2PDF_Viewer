"""Microsoft Store 版 Kindle の検索・取得・先頭移動を自動化する。"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import subprocess
import time
import unicodedata
from _ctypes import COMError
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pyautogui
import uiautomation as auto
from PIL import Image, ImageChops, ImageStat

logger = logging.getLogger(__name__)

_PAGE_FINGERPRINT_SIZE = (64, 64)
_PAGE_CHANGE_MEAN_THRESHOLD = 1.0


@dataclass(frozen=True)
class BookIdentity:
    asin: str
    title: str
    title_normalized: str | None = None
    authors: tuple[str, ...] = ()
    series_name: str | None = None
    volume_number: float | None = None
    volume_label: str | None = None

    @classmethod
    def from_job(cls, job: dict) -> BookIdentity:
        raw = job.get("identity") or {}
        return cls(
            asin=str(raw.get("asin") or job["asin"]),
            title=str(raw.get("title") or job.get("title") or ""),
            title_normalized=raw.get("title_normalized"),
            authors=tuple(str(value) for value in raw.get("authors") or ()),
            series_name=raw.get("series_name"),
            volume_number=raw.get("volume_number"),
            volume_label=raw.get("volume_label"),
        )


@dataclass(frozen=True)
class BookCandidate:
    asin: str | None
    title: str
    authors: tuple[str, ...] = ()
    series_name: str | None = None
    volume_number: float | None = None
    volume_label: str | None = None
    card: object | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ControllerConfig:
    window_title: str = "Kindle"
    window_class_name: str = "Microsoft.UI.Windowing.Window"
    control_search_depth: int = 30
    control_timeout_seconds: float = 10.0
    screen_transition_seconds: float = 2.0
    download_timeout_seconds: float = 1800.0
    download_poll_seconds: float = 2.0
    download_stable_checks: int = 3
    reader_timeout_seconds: float = 30.0
    page_change_timeout_seconds: float = 5.0
    page_stable_seconds: float = 2.0
    start_boundary_checks: int = 3
    positioning_timeout_seconds: float = 3600.0

    @property
    def content_root(self) -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "LOCALAPPDATA を取得できないためKindle保存先を確認できません",
            )
        return (
            Path(local_app_data)
            / "Packages"
            / "AMZNKindle.AmazonKindleReadingApp_m1sc522ngdk36"
            / "LocalState"
            / "Classic"
            / "Content"
        )


class KindleControllerError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def normalize_identity_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def visual_frames_differ(left: Image.Image, right: Image.Image) -> bool:
    """読書領域の縮小画像を比較し、ページ内容が変化したか判定する。"""
    left_gray = left.convert("L").resize(_PAGE_FINGERPRINT_SIZE)
    right_gray = right.convert("L").resize(_PAGE_FINGERPRINT_SIZE)
    difference = ImageChops.difference(left_gray, right_gray)
    return ImageStat.Stat(difference).mean[0] >= _PAGE_CHANGE_MEAN_THRESHOLD


def _same_optional_text(left: str | None, right: str | None) -> bool:
    return bool(left and right) and normalize_identity_text(
        left
    ) == normalize_identity_text(right)


def candidate_matches_identity(
    identity: BookIdentity,
    candidate: BookCandidate,
) -> bool:
    """ASINを優先し、ASINなしの場合だけ書誌の複合一致を許可する。"""
    if candidate.asin:
        return candidate.asin.casefold() == identity.asin.casefold()

    expected_titles = {
        normalize_identity_text(identity.title),
        normalize_identity_text(identity.title_normalized),
    }
    expected_titles.discard("")
    if normalize_identity_text(candidate.title) not in expected_titles:
        return False

    expected_authors = {
        normalize_identity_text(author) for author in identity.authors if author
    }
    candidate_authors = {
        normalize_identity_text(author) for author in candidate.authors if author
    }
    author_match = bool(expected_authors & candidate_authors)

    series_match = _same_optional_text(identity.series_name, candidate.series_name)
    volume_match = False
    if identity.volume_number is not None and candidate.volume_number is not None:
        volume_match = identity.volume_number == candidate.volume_number
    elif identity.volume_label and candidate.volume_label:
        volume_match = _same_optional_text(
            identity.volume_label, candidate.volume_label
        )

    return author_match or (series_match and volume_match)


def select_verified_candidate(
    identity: BookIdentity,
    candidates: Sequence[BookCandidate],
) -> BookCandidate:
    matches = [
        candidate
        for candidate in candidates
        if candidate_matches_identity(identity, candidate)
    ]
    if not matches:
        error_code = "book_not_found" if not candidates else "book_identity_unverified"
        raise KindleControllerError(
            error_code,
            "Kindleライブラリで対象書籍を一意に照合できませんでした",
        )
    if len(matches) > 1:
        raise KindleControllerError(
            "book_match_ambiguous",
            "Kindleライブラリで対象書籍の候補が複数見つかりました",
        )
    return matches[0]


def _parse_card_name(name: str) -> tuple[str, tuple[str, ...]]:
    title, separator, raw_authors = name.partition(" by ")
    if not separator:
        return name.strip(), ()
    author_text = re.sub(r",\s*新規$", "", raw_authors).strip()
    authors = tuple(
        value.strip() for value in re.split(r"[;/]", author_text) if value.strip()
    )
    return title.strip(), authors


class KindleAppController:
    def __init__(self, config: ControllerConfig | None = None) -> None:
        self.config = config or ControllerConfig()
        self.window: auto.Control | None = None

    @staticmethod
    def _is_process_running() -> bool:
        result = subprocess.run(
            [
                "tasklist",
                "/FI",
                "IMAGENAME eq Kindle.exe",
                "/FO",
                "CSV",
                "/NH",
            ],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return '"kindle.exe"' in result.stdout.casefold()

    def _ensure_process_running(self) -> None:
        if not self._is_process_running():
            raise KindleControllerError(
                "kindle_app_exited",
                "処理中にKindleアプリが終了しました",
            )

    def attach_running_app(self) -> None:
        if not self._is_process_running():
            raise KindleControllerError(
                "kindle_not_running",
                "Kindleアプリが起動していません",
            )
        window = auto.WindowControl(searchDepth=1, Name=self.config.window_title)
        if not window.Exists(
            self.config.control_timeout_seconds,
            0.5,
        ):
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleウィンドウを取得できませんでした",
            )
        if window.ClassName != self.config.window_class_name:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "対応していないKindleウィンドウが見つかりました",
            )
        try:
            window_handle = int(window.NativeWindowHandle)
        except (AttributeError, COMError, TypeError, ValueError) as exc:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleウィンドウの識別情報を取得できませんでした",
            ) from exc
        user32 = ctypes.windll.user32
        if window_handle <= 0 or not user32.IsWindow(window_handle):
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleウィンドウの識別情報が不正です",
            )
        user32.ShowWindow(window_handle, 9)
        user32.SetForegroundWindow(window_handle)
        time.sleep(self.config.screen_transition_seconds)
        self.window = window

    def _require_window(self) -> auto.Control:
        if self.window is None:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleウィンドウへ接続していません",
            )
        return self.window

    def _control_by_id(
        self,
        automation_id: str,
        *,
        timeout: float | None = None,
        found_index: int = 1,
    ) -> auto.Control | None:
        control = auto.Control(
            searchFromControl=self._require_window(),
            searchDepth=self.config.control_search_depth,
            foundIndex=found_index,
            AutomationId=automation_id,
        )
        try:
            if control.Exists(
                self.config.control_timeout_seconds if timeout is None else timeout,
                0.5,
            ):
                return control
        except COMError:
            logger.debug(
                "Kindle UI Automation control lookup failed transiently: %s",
                automation_id,
                exc_info=True,
            )
        return None

    def _search_edit(self, timeout: float | None = None) -> auto.Control | None:
        edit = auto.EditControl(
            searchFromControl=self._require_window(),
            searchDepth=self.config.control_search_depth,
            Name="検索ライブラリ",
        )
        try:
            if edit.Exists(
                self.config.control_timeout_seconds if timeout is None else timeout,
                0.5,
            ):
                return edit
        except COMError:
            logger.debug(
                "Kindle UI Automation search field lookup failed transiently",
                exc_info=True,
            )
        return None

    @staticmethod
    def _control_center(control: object) -> tuple[int, int]:
        try:
            bounds = control.BoundingRectangle
            left = int(bounds.left)
            top = int(bounds.top)
            right = int(bounds.right)
            bottom = int(bounds.bottom)
        except (AttributeError, COMError) as exc:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの操作対象の位置を取得できませんでした",
            ) from exc
        if right <= left or bottom <= top:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの操作対象の位置が不正です",
            )
        return ((left + right) // 2, (top + bottom) // 2)

    def _click_control(self, control: object) -> None:
        pyautogui.click(*self._control_center(control))

    @staticmethod
    def _toggle_is_on(control: object) -> bool:
        try:
            state = control.Element.GetCurrentPropertyValue(
                auto.PropertyId.ToggleToggleStateProperty
            )
        except (AttributeError, COMError, TypeError, ValueError):
            return False
        return int(state) == auto.ToggleState.On

    def reading_area_bounds(self) -> tuple[int, int, int, int]:
        """現在のReadingAreaを画面座標で返す。"""
        reading_area = self._control_by_id("ReadingArea", timeout=2.0)
        if reading_area is None:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの読書領域を取得できませんでした",
            )
        try:
            bounds = reading_area.BoundingRectangle
            result = (
                int(bounds.left),
                int(bounds.top),
                int(bounds.right),
                int(bounds.bottom),
            )
        except (AttributeError, COMError, TypeError, ValueError) as exc:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの読書領域の位置を取得できませんでした",
            ) from exc
        if result[0] >= result[2] or result[1] >= result[3]:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの読書領域の位置が不正です",
            )
        return result

    def capture_area_bounds(self, source: str) -> tuple[int, int, int, int]:
        """source別に保存対象となる読書領域を画面座標で返す。"""
        reading_left, reading_top, reading_right, reading_bottom = (
            self.reading_area_bounds()
        )
        if source == "comic":
            return (reading_left, reading_top, reading_right, reading_bottom)
        if source != "novel":
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの撮影領域種別が不正です",
            )

        top_chrome = self._control_by_id("TopChrome", timeout=2.0)
        footer = self._control_by_id("Footer", timeout=2.0)
        if top_chrome is None or footer is None:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの小説本文領域を取得できませんでした",
            )
        try:
            content_top = int(top_chrome.BoundingRectangle.bottom)
            content_bottom = int(footer.BoundingRectangle.top)
        except (AttributeError, COMError, TypeError, ValueError) as exc:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの小説本文領域の位置を取得できませんでした",
            ) from exc
        if not (reading_top <= content_top < content_bottom <= reading_bottom):
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの小説本文領域の位置が不正です",
            )
        return (reading_left, content_top, reading_right, content_bottom)

    def set_page_layout(self, source: str) -> None:
        """comicは2ページ、novelは1ページを選択して状態を検証する。"""
        option_ids = {
            "comic": "aaOption-Split",
            "novel": "aaOption-Single",
        }
        option_id = option_ids.get(source)
        if option_id is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleのページレイアウト種別が不正です",
            )

        reading_area = self._control_by_id("ReadingArea", timeout=2.0)
        if reading_area is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleの読書領域を取得できませんでした",
            )
        page_settings = self._control_by_id("aaMenuButton", timeout=0.5)
        if page_settings is None:
            self._click_control(reading_area)
            time.sleep(0.5)
            page_settings = self._control_by_id("aaMenuButton", timeout=2.0)
        if page_settings is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleのページ設定を開けませんでした",
            )

        menu_opened = False
        try:
            self._click_control(page_settings)
            menu_opened = True
            time.sleep(0.5)
            option = self._control_by_id(option_id, timeout=2.0)
            if option is None:
                if (
                    source == "novel"
                    and self._control_by_id("フォント-item", timeout=1.0) is not None
                ):
                    return
                raise KindleControllerError(
                    "positioning_failed",
                    "Kindleのページレイアウトを取得できませんでした",
                )
            if not self._toggle_is_on(option):
                self._click_control(option)

            deadline = time.monotonic() + self.config.control_timeout_seconds
            while time.monotonic() < deadline:
                option = self._control_by_id(option_id, timeout=0.5)
                if option is not None and self._toggle_is_on(option):
                    return
                time.sleep(0.25)
            raise KindleControllerError(
                "positioning_failed",
                "Kindleのページレイアウトを確認できませんでした",
            )
        finally:
            if menu_opened:
                close_button = self._control_by_id(
                    "CloseSideMenuHeaderButton",
                    timeout=1.0,
                )
                if close_button is not None:
                    self._click_control(close_button)
                else:
                    pyautogui.press("esc")
                time.sleep(0.25)
            if self._control_by_id("aaMenuButton", timeout=0.5) is not None:
                reading_area = self._control_by_id("ReadingArea", timeout=1.0)
                if reading_area is not None:
                    self._click_control(reading_area)
                    time.sleep(0.25)

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
        self._click_control(back)
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
                    position = self._control_center(edit)
                    pyautogui.click(*position)
                    pyautogui.hotkey("ctrl", "a")
                    pyautogui.write(value, interval=0.02)
                    return
                except KindleControllerError:
                    logger.debug(
                        "Kindle search field position lookup failed transiently",
                        exc_info=True,
                    )
            time.sleep(0.5)
        raise KindleControllerError(
            "kindle_ui_unavailable",
            "Kindleのライブラリ検索欄を更新できませんでした",
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
            title, authors = _parse_card_name(card.Name)
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

    def _reading_area_image(self, *, timeout: float = 1.0) -> Image.Image | None:
        reading_area = self._control_by_id("ReadingArea", timeout=timeout)
        if reading_area is None:
            return None
        bounds = reading_area.BoundingRectangle
        width = int(bounds.right - bounds.left)
        height = int(bounds.bottom - bounds.top)
        if width <= 0 or height <= 0:
            return None
        try:
            return pyautogui.screenshot(
                region=(int(bounds.left), int(bounds.top), width, height)
            )
        except OSError:
            logger.exception("Kindle reading area screenshot failed")
            return None

    def go_to_start(
        self,
        *,
        direction: str,
        on_poll: Callable[[], None] | None = None,
    ) -> None:
        if direction not in {"left", "right"}:
            raise KindleControllerError(
                "positioning_failed",
                "ページ送り方向が不正です",
            )
        previous_page_key = "right" if direction == "left" else "left"
        self.wait_for_reader_stable()
        previous_frame = self._reading_area_image()
        if previous_frame is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleの読書領域を取得できませんでした",
            )
        deadline = time.monotonic() + self.config.positioning_timeout_seconds
        boundary_count = 0
        while time.monotonic() < deadline:
            self._ensure_process_running()
            if on_poll:
                on_poll()
            pyautogui.press(previous_page_key)
            time.sleep(self.config.page_stable_seconds)
            current_frame = self._reading_area_image()
            if current_frame is None:
                raise KindleControllerError(
                    "positioning_failed",
                    "Kindleの読書領域を取得できませんでした",
                )
            if visual_frames_differ(previous_frame, current_frame):
                boundary_count = 0
            else:
                boundary_count += 1
                if boundary_count >= self.config.start_boundary_checks:
                    return
            previous_frame = current_frame
        raise KindleControllerError(
            "positioning_failed",
            "Kindle書籍を期限内に先頭へ移動できませんでした",
        )
