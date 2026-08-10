from __future__ import annotations

from dataclasses import dataclass

from .models import novel_footer_indicates_first_page


@dataclass(frozen=True)
class PageLayoutPolicy:
    """source ごとの Kindle ページレイアウト選択方針。"""

    option_id: str
    compatible_without_option_id: str | None = None


_PAGE_LAYOUT_POLICIES = {
    "comic": PageLayoutPolicy(option_id="aaOption-Split"),
    "novel": PageLayoutPolicy(
        option_id="aaOption-Single",
        compatible_without_option_id="フォント-item",
    ),
}


def page_layout_policy(source: str) -> PageLayoutPolicy | None:
    """source に対応するレイアウト方針を返す。"""
    return _PAGE_LAYOUT_POLICIES.get(source)


def needs_cover_step(source: str, footer_name: str) -> bool:
    """直接遷移後に表紙へ1ページだけ戻す必要があるか判定する。"""
    return source == "novel" and novel_footer_indicates_first_page(footer_name)


def previous_page_key(direction: str) -> str:
    """選択中のページ送り方向に対する逆向きキーを返す。"""
    return "right" if direction == "left" else "left"
