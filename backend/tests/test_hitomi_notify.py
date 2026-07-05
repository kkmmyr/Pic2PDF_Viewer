"""services.hitomi.notify のユニットテスト。

Webhook 未設定時の no-op、送信本文の組み立て、HTTP 失敗時の握りつぶしを検証する。
"""

import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.hitomi import notify


class TestBuildMessage:
    def test_includes_all_counts(self):
        msg = notify.build_message(added=3, skipped=2, errors=1)
        assert "3" in msg and "2" in msg and "1" in msg

    def test_zero_counts(self):
        # 0 件でも本文を組み立てられる（0 件通知の要件）
        msg = notify.build_message(added=0, skipped=0, errors=0)
        assert "0 件" in msg


class TestNotifyRunResult:
    def test_no_webhook_is_noop(self, monkeypatch):
        monkeypatch.setattr(notify, "HITOMI_DISCORD_WEBHOOK_URL", None)
        assert notify.notify_run_result(added=1, skipped=0, errors=0) is False

    def test_posts_when_webhook_set(self, monkeypatch):
        sent = {}

        def fake_post(url, json, timeout):
            sent["url"] = url
            sent["json"] = json
            return httpx.Response(204, request=httpx.Request("POST", url))

        monkeypatch.setattr(notify, "HITOMI_DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
        monkeypatch.setattr(notify.httpx, "post", fake_post)

        assert notify.notify_run_result(added=0, skipped=0, errors=0) is True
        assert sent["url"] == "https://discord.test/webhook"
        assert "content" in sent["json"]

    def test_http_error_is_swallowed(self, monkeypatch):
        def fake_post(url, json, timeout):
            raise httpx.ConnectError("boom")

        monkeypatch.setattr(notify, "HITOMI_DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
        monkeypatch.setattr(notify.httpx, "post", fake_post)

        # 例外を投げず False を返す（監視処理を止めない）
        assert notify.notify_run_result(added=1, skipped=0, errors=0) is False
