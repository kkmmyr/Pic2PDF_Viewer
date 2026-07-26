"""Microsoft Store版Kindle操作の後方互換facade。"""

import time

import pyautogui
import uiautomation as auto

from kindle_controller.library import LibraryControllerMixin
from kindle_controller.models import (
    BookCandidate,
    BookIdentity,
    ControllerConfig,
    KindleControllerError,
    candidate_matches_identity,
    footer_indicates_start as _footer_indicates_start,
    normalize_identity_text,
    parse_card_name as _parse_card_name,
    select_verified_candidate,
    visual_frames_differ,
)
from kindle_controller.reader import ReaderControllerMixin

_COMPATIBILITY_EXPORTS = (
    time,
    pyautogui,
    auto,
    _footer_indicates_start,
    _parse_card_name,
)


class KindleAppController(LibraryControllerMixin, ReaderControllerMixin):
    """既存の公開APIを保ったKindle操作facade。"""


__all__ = [
    "BookCandidate",
    "BookIdentity",
    "ControllerConfig",
    "KindleAppController",
    "KindleControllerError",
    "candidate_matches_identity",
    "normalize_identity_text",
    "select_verified_candidate",
    "visual_frames_differ",
]
