"""
utils.path_utils のユニットテスト。

実行方法:
    cd backend
    pytest tests/test_path_utils.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi import HTTPException

from utils.path_utils import join_path, validate_safe_name, validate_safe_path

# =============================================================================
# validate_safe_path
# =============================================================================

class TestValidateSafePath:
    def test_valid_simple_path(self):
        assert validate_safe_path("main/subdir") == "main/subdir"

    def test_valid_empty_string(self):
        assert validate_safe_path("") == ""

    def test_valid_single_segment(self):
        assert validate_safe_path("folder") == "folder"

    def test_backslash_normalized_to_slash(self):
        result = validate_safe_path("path\\to\\file")
        assert result == "path/to/file"

    def test_invalid_dot_dot(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_path("../etc/passwd")
        assert exc.value.status_code == 400

    def test_invalid_dot_dot_middle(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_path("foo/../bar")
        assert exc.value.status_code == 400

    def test_invalid_starts_with_slash(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_path("/etc/passwd")
        assert exc.value.status_code == 400

    def test_invalid_starts_with_backslash(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_path("\\windows\\system32")
        assert exc.value.status_code == 400

    def test_custom_param_name_in_detail(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_path("../bad", param_name="source_path")
        assert "source_path" in exc.value.detail


# =============================================================================
# validate_safe_name
# =============================================================================

class TestValidateSafeName:
    def test_valid_name(self):
        assert validate_safe_name("MyFolder") == "MyFolder"

    def test_valid_name_with_spaces(self):
        assert validate_safe_name("My Folder") == "My Folder"

    def test_invalid_dot_dot(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_name("..secret")
        assert exc.value.status_code == 400

    def test_invalid_forward_slash(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_name("folder/name")
        assert exc.value.status_code == 400

    def test_invalid_backslash(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_name("folder\\name")
        assert exc.value.status_code == 400

    def test_custom_param_name_in_detail(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_name("bad/name", param_name="folder_name")
        assert "folder_name" in exc.value.detail


# =============================================================================
# join_path
# =============================================================================

class TestJoinPath:
    def test_join_two_parts(self):
        result = join_path("base", "sub")
        assert "/" in result
        assert "\\" not in result

    def test_join_multiple_parts(self):
        result = join_path("a", "b", "c")
        assert result.endswith("a/b/c") or result.replace("\\", "/").endswith("a/b/c")
