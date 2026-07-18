"""
パス操作のユーティリティモジュール。

ディレクトリトラバーサル攻撃を防ぐバリデーション関数と、
クロスプラットフォームのパス結合ヘルパーを提供する。
"""

import ntpath
import os
from pathlib import Path

from fastapi import HTTPException


def validate_safe_path(path: str, param_name: str = "path") -> str:
    """
    ユーザー入力のパスを検証し、ディレクトリトラバーサル攻撃を防ぐ。

    以下の条件に該当する場合は HTTPException(400) を発生させる:
    - パス成分として ".." を含む（`/` `\\` で分割した成分のいずれかが ".." と一致）
    - "/" で始まる (Unix 系の絶対パス)
    - "\\" で始まる (Windows UNCパス / 絶対パス)

    `".."` の検出はパス成分単位で行う。OS が ".." を親ディレクトリ参照として
    特別扱いするのは成分として単独で出現したときのみで、`foo..bar` や
    `わたし...変えられちゃいました.pdf` のような名前は安全に扱えるため許可する。

    Args:
        path: 検証するパス文字列
        param_name: エラーメッセージに使用するパラメータ名

    Returns:
        バックスラッシュをスラッシュに統一した正規化パス
    """
    drive, _ = ntpath.splitdrive(path)
    if path.startswith("/") or path.startswith("\\") or drive or "\x00" in path:
        raise HTTPException(status_code=400, detail=f"Invalid {param_name}")
    parts = path.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        raise HTTPException(status_code=400, detail=f"Invalid {param_name}")
    return path.replace("\\", "/")


def resolve_under_base(base_dir: str | os.PathLike[str], path: str, param_name: str = "path") -> str:
    """ユーザー入力パスを ``base_dir`` 配下の絶対パスへ安全に解決する。

    drive 絶対パスや ``..`` を文字列段階で拒否したうえで ``Path.resolve`` し、
    symlink を経由した場合も最終的な解決先が基準ディレクトリ配下か確認する。
    """
    normalized = validate_safe_path(path, param_name=param_name)
    base = Path(base_dir).resolve()
    target = (base / normalized).resolve()
    if not target.is_relative_to(base):
        raise HTTPException(status_code=400, detail=f"Invalid {param_name}")
    return str(target)


def validate_safe_name(name: str, param_name: str = "name") -> str:
    """
    ファイル名・フォルダ名を検証する。パスセパレータを含む名前と、
    `.` / `..` のように OS から特別扱いされる名前を拒否する。

    `..secret` のように `..` を含むだけの名前は OS から見れば通常のファイル名
    （`os.path.join("/data", "..secret")` は `/data/..secret` であり親階層に
    出ない）ため許可する。

    Args:
        name: 検証する名前文字列
        param_name: エラーメッセージに使用するパラメータ名

    Returns:
        検証済みの名前文字列
    """
    drive, _ = ntpath.splitdrive(name)
    if not name or name in (".", "..") or "/" in name or "\\" in name or ":" in name or drive or "\x00" in name:
        raise HTTPException(status_code=400, detail=f"Invalid {param_name}")
    return name


def join_path(*parts: str) -> str:
    """
    パスを結合し、スラッシュに統一して返す。
    os.path.join + .replace("\\\\", "/") の代替。

    Args:
        *parts: 結合するパス要素

    Returns:
        スラッシュ統一済みのパス文字列
    """
    return os.path.join(*parts).replace("\\", "/")
