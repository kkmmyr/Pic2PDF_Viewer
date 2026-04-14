"""
パス操作のユーティリティモジュール。

ディレクトリトラバーサル攻撃を防ぐバリデーション関数と、
クロスプラットフォームのパス結合ヘルパーを提供する。
"""
import os
from fastapi import HTTPException


def validate_safe_path(path: str, param_name: str = "path") -> str:
    """
    ユーザー入力のパスを検証し、ディレクトリトラバーサル攻撃を防ぐ。

    以下の条件に該当する場合は HTTPException(400) を発生させる:
    - ".." が含まれる (上位ディレクトリへの移動)
    - "/" で始まる (Unix 系の絶対パス)
    - "\\" で始まる (Windows UNCパス / 絶対パス)

    Args:
        path: 検証するパス文字列
        param_name: エラーメッセージに使用するパラメータ名

    Returns:
        バックスラッシュをスラッシュに統一した正規化パス
    """
    if ".." in path or path.startswith("/") or path.startswith("\\"):
        raise HTTPException(status_code=400, detail=f"Invalid {param_name}")
    return path.replace("\\", "/")


def validate_safe_name(name: str, param_name: str = "name") -> str:
    """
    ファイル名・フォルダ名を検証する。パスセパレータを含む名前を拒否する。

    Args:
        name: 検証する名前文字列
        param_name: エラーメッセージに使用するパラメータ名

    Returns:
        検証済みの名前文字列
    """
    if ".." in name or "/" in name or "\\" in name:
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
