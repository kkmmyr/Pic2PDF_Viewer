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

from utils.path_utils import join_path, resolve_under_base, validate_safe_name, validate_safe_path

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

    @pytest.mark.parametrize("path", ["C:/Windows", "C:\\Windows", "C:relative"])
    def test_invalid_windows_drive_path(self, path):
        with pytest.raises(HTTPException) as exc:
            validate_safe_path(path)
        assert exc.value.status_code == 400

    def test_custom_param_name_in_detail(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_path("../bad", param_name="source_path")
        assert "source_path" in exc.value.detail

    def test_invalid_dot_dot_alone(self):
        # `..` 単独成分も拒否する
        with pytest.raises(HTTPException) as exc:
            validate_safe_path("..")
        assert exc.value.status_code == 400

    def test_invalid_dot_dot_at_end(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_path("foo/..")
        assert exc.value.status_code == 400

    def test_invalid_dot_dot_with_backslash(self):
        # 正規化前に `\\` で分割しても `..` 成分を検出できる
        with pytest.raises(HTTPException) as exc:
            validate_safe_path("foo\\..\\bar")
        assert exc.value.status_code == 400

    def test_valid_filename_with_triple_dots(self):
        # 連続 3 ドット（三点リーダ的用法）は OS から見れば普通のファイル名で許可する
        # 旧実装は `..` 部分一致で誤検出していたが、成分ベース判定では許可される
        assert validate_safe_path("わたし...変えられちゃいました.pdf") == "わたし...変えられちゃいました.pdf"

    def test_valid_filename_with_dot_dot_substring(self):
        # `foo..bar` のように成分内に `..` を含むだけの名前は許可
        assert validate_safe_path("foo..bar") == "foo..bar"

    def test_valid_path_with_dot_dot_in_segment(self):
        # サブフォルダ内のファイル名にも `..` を含めて良い
        assert validate_safe_path("sub/My...file.pdf") == "sub/My...file.pdf"


class TestResolveUnderBase:
    def test_resolves_child_under_base(self, tmp_path):
        resolved = resolve_under_base(tmp_path, "nested/book.pdf")
        assert resolved == str(tmp_path / "nested" / "book.pdf")

    def test_rejects_symlink_escape(self, tmp_path):
        outside = tmp_path.parent / f"{tmp_path.name}-outside"
        outside.mkdir()
        link = tmp_path / "escape"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation is unavailable on this Windows environment")

        with pytest.raises(HTTPException) as exc:
            resolve_under_base(tmp_path, "escape/secret.txt")
        assert exc.value.status_code == 400


# =============================================================================
# validate_safe_name
# =============================================================================


class TestValidateSafeName:
    def test_valid_name(self):
        assert validate_safe_name("MyFolder") == "MyFolder"

    def test_invalid_empty_name(self):
        with pytest.raises(HTTPException):
            validate_safe_name("")

    def test_valid_name_with_spaces(self):
        assert validate_safe_name("My Folder") == "My Folder"

    def test_invalid_windows_drive_or_ads_name(self):
        with pytest.raises(HTTPException):
            validate_safe_name("C:secret")

    def test_invalid_dot_dot_exact(self):
        # 名前自体が `..` のときだけ拒否
        with pytest.raises(HTTPException) as exc:
            validate_safe_name("..")
        assert exc.value.status_code == 400

    def test_invalid_single_dot_exact(self):
        with pytest.raises(HTTPException) as exc:
            validate_safe_name(".")
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

    def test_valid_name_with_dot_dot_substring(self):
        # 旧実装は `..secret` を拒否していたが、これは隠しファイルとして安全な名前
        assert validate_safe_name("..secret") == "..secret"

    def test_valid_filename_with_triple_dots(self):
        # 連続 3 ドットを含む書籍タイトルが正規ファイル名として許可される
        title = "わたし...変えられちゃいました。 ―アラサーOLがヤリチン大学生達のチ○ポにドハマリするまで― 総集編.pdf"
        assert validate_safe_name(title) == title

    def test_valid_filename_with_dot_dot_substring(self):
        assert validate_safe_name("My..file.pdf") == "My..file.pdf"


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
