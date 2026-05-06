"""
utils.logger のユニットテスト。

`get_logger` のスモークテスト。

実行方法:
    cd backend
    uv run pytest tests/test_logger.py -v
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.logger import get_logger


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
