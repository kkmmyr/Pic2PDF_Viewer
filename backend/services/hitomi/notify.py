"""hitomi 新着監視の実行結果を Discord に通知する。

Webhook URL（config.HITOMI_DISCORD_WEBHOOK_URL）が未設定なら何もしない。
通知の失敗は監視処理を止めてはならないため、例外は握りつぶして warning ログのみ出す。
"""

from __future__ import annotations

import sys
from typing import Final

import httpx

from config import HITOMI_DISCORD_WEBHOOK_URL

_TIMEOUT: Final[float] = 10.0


def build_message(added: int, skipped: int, errors: int) -> str:
    """Discord に送る本文を組み立てる（件数のみ）。"""
    return f"📥 hitomi 新着監視: 新着 {added} 件（skip {skipped} / エラー {errors}）"


def notify_run_result(added: int, skipped: int, errors: int) -> bool:
    """実行結果を Discord Webhook に送信する。

    Args:
        added: 今回追加した新着件数（0 でも送信する）
        skipped: スキップした作者数
        errors: エラー件数

    Returns:
        送信した場合 True、Webhook 未設定またはエラーで送らなかった場合 False。
    """
    if not HITOMI_DISCORD_WEBHOOK_URL:
        return False

    content = build_message(added, skipped, errors)
    try:
        resp = httpx.post(
            HITOMI_DISCORD_WEBHOOK_URL,
            json={"content": content},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError as e:
        print(f"[hitomi_monitor] WARN: Discord 通知失敗: {e}", file=sys.stderr)
        return False
