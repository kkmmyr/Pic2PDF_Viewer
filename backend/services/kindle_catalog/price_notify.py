"""Kindle 価格監視の Discord 通知。"""

from __future__ import annotations

import sys

import httpx

import config

_TIMEOUT = 10.0


def _yen(value: int | None) -> str:
    return "不明" if value is None else f"￥{value:,}"


def build_message(
    *,
    title: str | None,
    asin: str | None,
    url: str,
    current_price: int | None,
    list_price: int | None,
    ratio_percent: float | None,
    previous_price: int | None,
    kinds: list[str],
) -> str:
    """Discord に送る価格変化メッセージを組み立てる。"""
    subject = title or asin or "Kindle 本"
    reasons: list[str] = []
    if "price_drop" in kinds:
        if previous_price is not None and current_price is not None:
            reasons.append(f"値下がり（{_yen(previous_price)} → {_yen(current_price)}）")
        else:
            reasons.append("値下がり")
    if "below_threshold" in kinds:
        reasons.append("設定した定価比を下回りました")
    ratio = "不明" if ratio_percent is None else f"{ratio_percent:.1f}%"
    return (
        f"📚 Kindle価格監視: {subject}\n"
        f"現在価格: {_yen(current_price)}\n"
        f"定価/参考価格: {_yen(list_price)}\n"
        f"定価比: {ratio}\n"
        f"理由: {' / '.join(reasons)}\n"
        f"{url}"
    )


def notify_price_event(
    *,
    title: str | None,
    asin: str | None,
    url: str,
    current_price: int | None,
    list_price: int | None,
    ratio_percent: float | None,
    previous_price: int | None,
    kinds: list[str],
) -> bool:
    """価格イベントを Discord Webhook に送る。未設定・失敗時は False。"""
    webhook_url = config.KINDLE_PRICE_DISCORD_WEBHOOK_URL
    if not webhook_url:
        return False

    try:
        response = httpx.post(
            webhook_url,
            json={
                "content": build_message(
                    title=title,
                    asin=asin,
                    url=url,
                    current_price=current_price,
                    list_price=list_price,
                    ratio_percent=ratio_percent,
                    previous_price=previous_price,
                    kinds=kinds,
                )
            },
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        print(f"[kindle_price_monitor] WARN: Discord 通知失敗: {exc}", file=sys.stderr)
        return False
