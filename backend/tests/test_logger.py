"""
utils.logger のユニットテスト。

`get_logger` のスモークテスト + RotatingFileHandler の登録確認。

実行方法:
    cd backend
    uv run pytest tests/test_logger.py -v
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.logger import _FILE_HANDLER_MARKER, _LOG_DIR, _LOG_FILE, get_logger


class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_same_name_returns_same_logger(self):
        """logging.getLogger と同様、同名なら同一インスタンスが返る。"""
        a = get_logger("dup.test")
        b = get_logger("dup.test")
        assert a is b

    def test_no_duplicate_handlers(self):
        """同じ名前で複数回呼んでも handler が増えない。"""
        name = "no_dup_handler_test"
        logger1 = get_logger(name)
        initial = len(logger1.handlers)

        logger2 = get_logger(name)
        assert len(logger2.handlers) == initial
        # 念のためもう一度
        get_logger(name)
        assert len(logger1.handlers) == initial

    def test_default_level_is_info(self):
        logger = get_logger("level.test")
        assert logger.level == logging.INFO

    def test_handler_has_formatter(self):
        logger = get_logger("formatter.test")
        # 少なくとも 1 つの handler に formatter が付く
        assert any(h.formatter is not None for h in logger.handlers)


class TestRootFileHandler:
    """RotatingFileHandler が root logger に 1 度だけ付与されるか確認。"""

    def test_log_directory_is_created(self):
        get_logger("rootfile.dir.test")
        assert os.path.isdir(_LOG_DIR)

    def test_root_has_rotating_file_handler(self):
        get_logger("rootfile.exists.test")
        root = logging.getLogger()
        marked = [h for h in root.handlers if getattr(h, _FILE_HANDLER_MARKER, False)]
        assert len(marked) == 1
        assert isinstance(marked[0], RotatingFileHandler)

    def test_rotating_file_handler_config(self):
        """maxBytes / backupCount / encoding が ADR-0006 の決定値と一致。"""
        get_logger("rootfile.config.test")
        root = logging.getLogger()
        handler = next(h for h in root.handlers if getattr(h, _FILE_HANDLER_MARKER, False))
        assert isinstance(handler, RotatingFileHandler)
        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 5
        assert handler.encoding == "utf-8"
        assert os.path.normpath(handler.baseFilename) == os.path.normpath(_LOG_FILE)

    def test_root_file_handler_not_duplicated(self):
        """get_logger を多数回呼んでも RotatingFileHandler は 1 個のまま。"""
        for i in range(5):
            get_logger(f"rootfile.no_dup.test.{i}")
        root = logging.getLogger()
        marked = [h for h in root.handlers if getattr(h, _FILE_HANDLER_MARKER, False)]
        assert len(marked) == 1

    def test_log_message_is_written_to_file(self, tmp_path):
        """propagate 経由でログがファイルへ書き込まれるかをエンドツーエンドで確認。

        既存の RotatingFileHandler は backend/data/logs/app.log を見るので、
        そのファイルに書き込まれた末尾を読み出して確認する。
        """
        logger = get_logger("rootfile.e2e.test")
        marker = "ROTATE_E2E_PROBE_4f2a91c0"
        logger.warning("%s payload", marker)

        # FileHandler を flush
        for h in logging.getLogger().handlers:
            h.flush()

        assert os.path.isfile(_LOG_FILE)
        with open(_LOG_FILE, encoding="utf-8") as f:
            content = f.read()
        assert marker in content
