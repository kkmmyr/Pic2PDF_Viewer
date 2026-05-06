"""
routers._deps のユニットテスト。

全ルーターで使われるガード関数とデコレータをカバーする。

実行方法:
    cd backend
    uv run pytest tests/test_router_deps.py -v
"""
import logging
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from routers._deps import (
    assert_valid_source,
    log_and_raise_500,
    validate_request_targets,
    validated_source,
)

# ---------------------------------------------------------------------------
# validated_source (Depends 用)
# ---------------------------------------------------------------------------

class TestValidatedSource:
    def test_generated_passes(self):
        assert validated_source("generated") == "generated"

    def test_kindle_passes(self):
        assert validated_source("kindle") == "kindle"

    def test_novel_passes(self):
        assert validated_source("novel") == "novel"

    def test_default_is_generated(self):
        assert validated_source() == "generated"

    def test_invalid_source_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            validated_source("invalid")
        assert exc.value.status_code == 400
        assert "Invalid source" in exc.value.detail

    def test_uppercase_rejected(self):
        with pytest.raises(HTTPException) as exc:
            validated_source("GENERATED")
        assert exc.value.status_code == 400

    def test_empty_string_rejected(self):
        with pytest.raises(HTTPException) as exc:
            validated_source("")
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# assert_valid_source (リクエストボディ検証用)
# ---------------------------------------------------------------------------

class TestAssertValidSource:
    def test_generated_passes(self):
        assert_valid_source("generated")  # 例外が出ないことを確認

    def test_kindle_passes(self):
        assert_valid_source("kindle")

    def test_novel_passes(self):
        assert_valid_source("novel")

    def test_invalid_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            assert_valid_source("foo")
        assert exc.value.status_code == 400
        assert "Invalid source" in exc.value.detail


# ---------------------------------------------------------------------------
# validate_request_targets (path + names 一括検証)
# ---------------------------------------------------------------------------

class TestValidateRequestTargets:
    def test_valid_path_and_names(self):
        validate_request_targets("sub/dir", ["a.pdf", "b.pdf"])

    def test_empty_path_allowed(self):
        validate_request_targets("", ["a.pdf"])

    def test_empty_names_list_allowed(self):
        # ループが回らないので例外なし
        validate_request_targets("sub", [])

    def test_path_with_dot_dot_rejected(self):
        with pytest.raises(HTTPException) as exc:
            validate_request_targets("../etc", ["a.pdf"])
        assert exc.value.status_code == 400

    def test_absolute_path_rejected(self):
        with pytest.raises(HTTPException) as exc:
            validate_request_targets("/etc", ["a.pdf"])
        assert exc.value.status_code == 400

    def test_name_with_slash_rejected(self):
        with pytest.raises(HTTPException) as exc:
            validate_request_targets("sub", ["foo/bar.pdf"])
        assert exc.value.status_code == 400

    def test_name_with_backslash_rejected(self):
        with pytest.raises(HTTPException) as exc:
            validate_request_targets("sub", ["foo\\bar.pdf"])
        assert exc.value.status_code == 400

    def test_first_invalid_name_short_circuits(self):
        # 最初の不正 name で raise されればよい
        with pytest.raises(HTTPException) as exc:
            validate_request_targets("sub", ["ok.pdf", "../bad.pdf", "ok2.pdf"])
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# log_and_raise_500 デコレータ
# ---------------------------------------------------------------------------

class TestLogAndRaise500:
    def test_normal_return_passes_through(self):
        @log_and_raise_500("test_op")
        def func():
            return {"ok": True}

        assert func() == {"ok": True}

    def test_args_kwargs_forwarded(self):
        @log_and_raise_500("test_op")
        def func(a, b, c=3):
            return a + b + c

        assert func(1, 2, c=10) == 13

    def test_explicit_http_exception_passes_through(self):
        """エンドポイント内で raise した HTTPException は素通し（4xx を残す）。"""
        @log_and_raise_500("test_op")
        def func():
            raise HTTPException(status_code=404, detail="Not found")

        with pytest.raises(HTTPException) as exc:
            func()
        assert exc.value.status_code == 404
        assert exc.value.detail == "Not found"

    def test_400_passes_through(self):
        """400 もそのまま伝わる（再ラップしない）。"""
        @log_and_raise_500("test_op")
        def func():
            raise HTTPException(status_code=400, detail="Bad request")

        with pytest.raises(HTTPException) as exc:
            func()
        assert exc.value.status_code == 400

    def test_unexpected_exception_converted_to_500(self):
        @log_and_raise_500("test_op")
        def func():
            raise RuntimeError("boom")

        with pytest.raises(HTTPException) as exc:
            func()
        assert exc.value.status_code == 500
        assert "boom" in exc.value.detail

    def test_value_error_converted_to_500(self):
        @log_and_raise_500("test_op")
        def func():
            raise ValueError("invalid value")

        with pytest.raises(HTTPException) as exc:
            func()
        assert exc.value.status_code == 500
        assert "invalid value" in exc.value.detail

    def test_logger_records_operation_name(self, caplog):
        """ログメッセージに operation 名が含まれる。"""
        @log_and_raise_500("delete_pages")
        def func():
            raise RuntimeError("boom")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(HTTPException):
                func()

        # logger は decorator 内で func.__module__ から取得される
        # caplog はルートロガー含めて全ロガーを捕捉する
        assert any("delete_pages failed" in r.message for r in caplog.records)

    def test_runtime_error_handled_inline_passes_400(self):
        """エンドポイント関数内で RuntimeError を 400 に変換する典型パターンが正しく伝わる。"""
        @log_and_raise_500("test_op")
        def func():
            try:
                raise RuntimeError("conflict")
            except RuntimeError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e

        with pytest.raises(HTTPException) as exc:
            func()
        assert exc.value.status_code == 400
        assert exc.value.detail == "conflict"

    def test_preserves_function_metadata(self):
        """functools.wraps で __name__ / __doc__ が保たれる。"""
        @log_and_raise_500("test_op")
        def my_func():
            """My docstring."""
            return 1

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "My docstring."
