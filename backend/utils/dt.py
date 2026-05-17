"""JST (Asia/Tokyo) 日時ユーティリティ。"""
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def jst_now() -> datetime:
    return datetime.now(JST)
