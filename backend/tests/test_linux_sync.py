"""services.linux_sync のユニットテスト。

SSH 接続はモック化して、パス解決ロジック・有効/無効フラグを検証する。
"""
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import services.linux_sync as ls

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_file(path: Path, content: bytes = b"\x00") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# sync_after_generate — LINUX_SYNC_ENABLED=false の場合はスキップ
# ---------------------------------------------------------------------------

class TestSyncDisabled:
    def test_no_ssh_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ls, "_SYNC_ENABLED", False)

        with patch("subprocess.run") as mock_run:
            ls.sync_after_generate(["book.pdf"], str(tmp_path), str(tmp_path))

        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# sync_after_generate — パス解決が正しいか
# ---------------------------------------------------------------------------

class TestSyncPathResolution:
    def test_images_dir_uses_stem_not_pdf_name(self, tmp_path, monkeypatch):
        """book_names の ".pdf" を除いた stem でディレクトリを探す。"""
        monkeypatch.setattr(ls, "_SYNC_ENABLED", True)

        images_dir = tmp_path / "images"
        thumbs_dir = tmp_path / "thumbnails"

        # 正しいパス: images/stem (拡張子なし)
        _make_dir(images_dir / "mybook")
        _make_file(images_dir / "mybook" / "01.webp")
        _make_file(thumbs_dir / "mybook.jpg")

        captured = []

        def _fake_run(cmd, **kw):
            captured.append(cmd)
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", _fake_run)

        ls.sync_after_generate(["mybook.pdf"], str(images_dir), str(thumbs_dir))

        # SSH が 3 回呼ばれる: images tar / thumbnail send / meta init
        assert len(captured) == 3
        # images: tar が images/mybook を対象にする（.pdf 付きではない）
        ssh_images_cmd = captured[0]
        assert "tar" in ssh_images_cmd[-1] or "images" in str(captured[0])

    def test_thumbnail_sent_as_file_not_tar(self, tmp_path, monkeypatch):
        """サムネイルは _send_file (cat >) で送信、_tar_and_send ではない。"""
        monkeypatch.setattr(ls, "_SYNC_ENABLED", True)

        images_dir = tmp_path / "images"
        thumbs_dir = tmp_path / "thumbnails"

        _make_dir(images_dir / "book1")
        _make_file(thumbs_dir / "book1.jpg")

        ssh_cmds = []

        def _fake_run(cmd, **kw):
            ssh_cmds.append(cmd[-1])  # SSH コマンド文字列
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", _fake_run)

        ls.sync_after_generate(["book1.pdf"], str(images_dir), str(thumbs_dir))

        # サムネイル転送コマンドに "cat >" が含まれる（_send_file 経由）
        assert any("cat >" in c for c in ssh_cmds), f"Expected 'cat >' in one of: {ssh_cmds}"

    def test_missing_images_dir_logs_warning_not_error(self, tmp_path, monkeypatch, caplog):
        """images ディレクトリが存在しない場合は warning のみで例外を投げない。"""
        monkeypatch.setattr(ls, "_SYNC_ENABLED", True)

        images_dir = tmp_path / "images"   # 作らない
        thumbs_dir = tmp_path / "thumbnails"

        _make_file(thumbs_dir / "book.jpg")

        def _fake_run(cmd, **kw):
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", _fake_run)

        with caplog.at_level(logging.WARNING, logger="services.linux_sync"):
            ls.sync_after_generate(["book.pdf"], str(images_dir), str(thumbs_dir))

        assert any("source not found" in r.message for r in caplog.records)

    def test_multiple_books_each_synced(self, tmp_path, monkeypatch):
        """複数書籍ぶん全てが同期される。"""
        monkeypatch.setattr(ls, "_SYNC_ENABLED", True)

        images_dir = tmp_path / "images"
        thumbs_dir = tmp_path / "thumbnails"

        for name in ["alpha", "beta"]:
            _make_dir(images_dir / name)
            _make_file(thumbs_dir / f"{name}.jpg")

        call_count = {"n": 0}

        def _fake_run(cmd, **kw):
            call_count["n"] += 1
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", _fake_run)

        ls.sync_after_generate(
            ["alpha.pdf", "beta.pdf"],
            str(images_dir), str(thumbs_dir),
        )

        # 各書籍 2 回 (images tar + thumbnail) × 2 冊 + meta init 1 回 = 5 回
        assert call_count["n"] == 5


# ---------------------------------------------------------------------------
# _init_meta_on_linux — meta.db 初期化スクリプトの検証
# ---------------------------------------------------------------------------

class TestInitMetaOnLinux:
    def test_sends_python_script_via_stdin(self, monkeypatch):
        """SSH 経由で python3 に書籍名リストを含むスクリプトを送信する。"""
        monkeypatch.setattr(ls, "_SYNC_ENABLED", True)

        captured = {}

        def _fake_run(cmd, input=None, **kw):
            captured["cmd"] = cmd
            captured["input"] = input
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", _fake_run)

        ls._init_meta_on_linux(["book1.pdf", "book2.pdf"])

        # python3 へ stdin でスクリプトを渡す
        assert captured["cmd"][-1] == "python3"
        script = captured["input"].decode("utf-8")
        # 書籍名・INSERT 文・オリジナルが含まれる
        assert "book1.pdf" in script
        assert "book2.pdf" in script
        assert "INSERT OR IGNORE" in script
        assert "オリジナル" in script or "\\u30aa\\u30ea\\u30b8\\u30ca\\u30eb" in script

    def test_ssh_error_raises(self, monkeypatch):
        """SSH が失敗した場合は RuntimeError を投げる。"""
        monkeypatch.setattr(ls, "_SYNC_ENABLED", True)

        def _fake_run(cmd, **kw):
            return MagicMock(returncode=1, stderr=b"connection refused")

        monkeypatch.setattr("subprocess.run", _fake_run)

        import pytest
        with pytest.raises(RuntimeError):
            ls._init_meta_on_linux(["book.pdf"])

    def test_meta_init_error_does_not_abort_sync(self, tmp_path, monkeypatch):
        """meta init が失敗しても sync_after_generate 全体は成功扱いになる。"""
        monkeypatch.setattr(ls, "_SYNC_ENABLED", True)

        images_dir = tmp_path / "images"
        thumbs_dir = tmp_path / "thumbnails"
        _make_dir(images_dir / "book")
        _make_file(thumbs_dir / "book.jpg")

        call_count = {"n": 0}

        def _fake_run(cmd, **kw):
            call_count["n"] += 1
            # 3 回目（meta init）は失敗させる
            if call_count["n"] == 3:
                return MagicMock(returncode=1, stderr=b"error")
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", _fake_run)

        # 例外なく完了する
        ls.sync_after_generate(["book.pdf"], str(images_dir), str(thumbs_dir))
