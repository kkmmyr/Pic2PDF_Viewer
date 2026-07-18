"""`docs/design/詳細設計/` のファイルマップ（ディレクトリ構成 ASCII ツリー）を
実際のディレクトリ構成から自動生成し、対象 Markdown 内のマーカーブロックへ書き戻す。

背景: `詳細設計書_フロントエンド_ファイルマップ.md` の
`## 1. ディレクトリ構成（フロントエンド側）` と、
`詳細設計書_バックエンド編.md` の `## 1. ディレクトリ構成（バックエンド側）` は
これまで手書きの box-drawing ツリー（`├──` / `│` / `└──`）だったため実体との
ドリフトが発生していた。本スクリプトはそのツリーを `backend/` /
`kindle-pdf/` / `frontend/src/` の実ファイルシステムから機械的に再生成する。

対象 Markdown 内の以下マーカー行の間（exclusive）を、生成したツリーを含む
fenced ```text コードブロックで置換する。

    <!-- GENERATED:FILE_MAP:START -->
    ...
    <!-- GENERATED:FILE_MAP:END -->

マーカーが見つからない場合は対象ファイルごとにハードエラーとする（無言スキップ
しない）。マーカーの挿入自体は別ステップの仕事であり、本スクリプトはマーカーが
挿入済みであることを前提とする。存在しない対象ファイル（例:
`詳細設計書_バックエンド_ファイルマップ.md` はまだ作成されていない）は warning
を出してスキップする（エラーにしない）。

usage:
    uv run python scripts/maintenance/generate_file_map.py            # 差分があれば書き込み、変更ファイルを報告
    uv run python scripts/maintenance/generate_file_map.py --check     # 書き込みなしで差分検査のみ（CI 用）

exit code:
    0: 変更なし（--check: 差分なし）
    1: 変更した / 差分がある（--check: 差分あり）、またはマーカー欠落等のエラー
"""

from __future__ import annotations

import fnmatch
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Windows 環境で日本語ファイルパスが文字化けしないよう UTF-8 出力を強制
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# 除外ルール
# ---------------------------------------------------------------------------

# ディレクトリ名の完全一致で除外（配下には一切降りない）。
# tests/test/__tests__ は「ソース構成マップ」の対象外という方針
# （.claude/commands/big-files.md が肥大化探索で test ディレクトリを除外する
# 慣習と揃える）。
EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",  # kindle-pdf/.gitignore は無点の venv/ を使う
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        ".git",
        "dist",
        "output",  # kindle-pdf/.gitignore の output/（キャプチャ出力）
        "coverage",
        "htmlcov",
        "tests",
        "test",
        "__tests__",
    }
)

# ディレクトリ名の glob パターンで除外
EXCLUDED_DIR_GLOBS = ("playwright-*", "*.egg-info")

# プロジェクトルート相対パスの完全一致で除外するディレクトリ
# （名前だけでは判別できない特定パスの除外）
EXCLUDED_RELATIVE_DIRS = frozenset(
    {
        "backend/complete",
        "backend/data",
        "backend/input",
        "backend/scripts/results",
    }
)

# ファイル名の完全一致で除外するもの。方針: ディレクトリレベルのノイズのみを
# 除外し、拡張子ベースのフィルタは行わない（.tsbuildinfo / .pyc 等は
# 実ファイルとして存在すれば表示される）。例外はここに完全一致で個別列挙する:
# - .DS_Store: macOS のノイズ
# - .coverage: gitignore 対象の実行時生成物。ローカルの汚れた状態で生成した
#   ツリーが CI のクリーンチェックアウトと恒常的にドリフトした実績があるため
#   （2026-07 CI修理計画書 DOCS-1）
EXCLUDED_FILE_NAMES = frozenset({".DS_Store", ".coverage"})

def _is_excluded_dir(path: Path) -> bool:
    name = path.name
    if name in EXCLUDED_DIR_NAMES:
        return True
    if any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDED_DIR_GLOBS):
        return True
    rel_posix = path.relative_to(PROJECT_ROOT).as_posix()
    return rel_posix in EXCLUDED_RELATIVE_DIRS

# ---------------------------------------------------------------------------
# ツリー描画
# ---------------------------------------------------------------------------
#
# ソート順: 各階層でディレクトリを先に、ファイルを後に列挙する。
# 各グループ内はファイル名の大小文字を無視したアルファベット順
# （手書き時代の並びを厳密に再現することは狙わない。決定論的で読みやすい
# 順序であることを優先する — 本スクリプトが手動管理を置き換えるため）。


def _list_children(dir_path: Path) -> list[Path]:
    dirs: list[Path] = []
    files: list[Path] = []
    for child in dir_path.iterdir():
        if child.is_dir():
            if _is_excluded_dir(child):
                continue
            dirs.append(child)
        else:
            if child.name in EXCLUDED_FILE_NAMES:
                continue
            files.append(child)
    dirs.sort(key=lambda p: p.name.lower())
    files.sort(key=lambda p: p.name.lower())
    return [*dirs, *files]


def _render_children(dir_path: Path, prefix: str, lines: list[str]) -> None:
    children = _list_children(dir_path)
    last_index = len(children) - 1
    for i, child in enumerate(children):
        is_last = i == last_index
        connector = "└── " if is_last else "├── "
        if child.is_dir():
            lines.append(f"{prefix}{connector}{child.name}/")
            extension = "    " if is_last else "│   "
            _render_children(child, prefix + extension, lines)
        else:
            lines.append(f"{prefix}{connector}{child.name}")


def render_tree(root: Path, root_label: str) -> str:
    """root 配下を box-drawing ASCII ツリーとして描画する。

    root_label はツリー1行目に使うラベル（例: "backend/" / "frontend/src/"）。
    既存の手書きドキュメントに合わせ、プロジェクトルート相対パスをそのまま
    ラベルにする（frontend 側は "frontend/" を省略せず "frontend/src/" とする
    ことで、backend/ 側の "backend/" "kindle-pdf/" と表記の一貫性を保つ）。
    """
    lines = [root_label]
    _render_children(root, "", lines)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# マーカーブロック置換
# ---------------------------------------------------------------------------

MARKER_START = "<!-- GENERATED:FILE_MAP:START -->"
MARKER_END = "<!-- GENERATED:FILE_MAP:END -->"

_MARKER_BLOCK_RE = re.compile(re.escape(MARKER_START) + r"\n(.*?)\n" + re.escape(MARKER_END), re.DOTALL)


class MarkerNotFoundError(RuntimeError):
    """対象 Markdown にマーカー行の組が見つからない場合に送出する。"""


def build_marker_block(trees: list[str]) -> str:
    """複数ツリーを 1 つの ```text フェンスコードブロックにまとめる。

    設計判断: バックエンド側は backend/ と kindle-pdf/ の 2 ツリーを持つが、
    別々のフェンスに分けず 1 つのフェンス内で空行区切りにする（各ツリーの
    1 行目がそのまま "backend/" / "kindle-pdf/" というルートラベルになる
    ため、フェンスを分けなくても視認性は落ちない。マーカー置換ロジックも
    単純に保てる）。
    """
    body = "\n\n".join(trees)
    return f"```text\n{body}\n```"


def replace_marker_block(text: str, new_block: str, *, source_label: str) -> str:
    """text 内の MARKER_START/END の間（exclusive）を new_block で置換する。

    マーカーが見つからない場合は MarkerNotFoundError を送出する
    （無言スキップしない・呼び出し元でハードエラーとして扱わせるため）。
    """
    if MARKER_START not in text or MARKER_END not in text:
        raise MarkerNotFoundError(
            f"{source_label}: マーカー {MARKER_START} / {MARKER_END} が見つかりません。"
            "マーカー挿入ステップを先に実施してください。"
        )
    new_text, count = _MARKER_BLOCK_RE.subn(lambda _m: f"{MARKER_START}\n{new_block}\n{MARKER_END}", text, count=1)
    if count == 0:
        raise MarkerNotFoundError(f"{source_label}: マーカーの並び（START → END の順）が不正、または壊れています。")
    return new_text


# ---------------------------------------------------------------------------
# 対象ファイル定義
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderRoot:
    label: str
    path: Path


@dataclass(frozen=True)
class Target:
    path: Path
    roots: list[RenderRoot]


# ハードコード対象リスト（config ファイルなし。check_docs.py の DOCS_DIR /
# MKDOCS_YML 同様、このリポジトリではパスを直接書く慣習に合わせる）。
TARGETS: list[Target] = [
    Target(
        path=PROJECT_ROOT / "docs" / "design" / "詳細設計" / "詳細設計書_フロントエンド_ファイルマップ.md",
        roots=[RenderRoot("frontend/src/", PROJECT_ROOT / "frontend" / "src")],
    ),
    Target(
        # このファイルはまだ存在しない（マーカー挿入と合わせて後続ステップで新設）。
        # 存在しない間は「警告してスキップ」扱いになる（エラーにしない）。
        path=PROJECT_ROOT / "docs" / "design" / "詳細設計" / "詳細設計書_バックエンド_ファイルマップ.md",
        roots=[
            RenderRoot("backend/", PROJECT_ROOT / "backend"),
            RenderRoot("kindle-pdf/", PROJECT_ROOT / "kindle-pdf"),
        ],
    ),
]


def build_block_for_target(target: Target) -> str:
    trees = [render_tree(root.path, root.label) for root in target.roots]
    return build_marker_block(trees)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _display_path(path: Path) -> str:
    """表示・エラーメッセージ用のパス文字列。

    PROJECT_ROOT 配下なら相対パス（POSIX 区切り）、配下でなければ絶対パスの
    ままにする（テストで scratch フィクスチャ等 PROJECT_ROOT 外のファイルを
    Target に指定するケースに対応するための保険）。
    """
    if path.is_relative_to(PROJECT_ROOT):
        return path.relative_to(PROJECT_ROOT).as_posix()
    return str(path)


def process_target(target: Target, *, check: bool) -> str:
    """対象ファイル 1 件を処理し、状態を返す。

    戻り値: "missing" | "unchanged" | "would-change" | "changed"
    マーカーが見つからない場合は MarkerNotFoundError を送出する（呼び出し元で処理）。
    """
    if not target.path.exists():
        return "missing"
    original = target.path.read_text(encoding="utf-8")
    block = build_block_for_target(target)
    updated = replace_marker_block(original, block, source_label=_display_path(target.path))
    if updated == original:
        return "unchanged"
    if check:
        return "would-change"
    target.path.write_text(updated, encoding="utf-8")
    return "changed"


def run(targets: list[Target], *, check: bool) -> int:
    """targets を処理し、exit code を返す（main() から呼ばれる。
    テストからも直接カスタム targets を渡して呼べるようにするための分離）。
    """
    changed: list[str] = []
    would_change: list[str] = []
    missing: list[str] = []
    marker_errors: list[str] = []

    for target in targets:
        rel = _display_path(target.path)
        try:
            status = process_target(target, check=check)
        except MarkerNotFoundError as e:
            print(f"[ERROR] {e}")
            marker_errors.append(rel)
            continue

        if status == "missing":
            print(f"[SKIP] {rel} はまだ存在しません。作成後に再実行してください。")
            missing.append(rel)
        elif status == "unchanged":
            print(f"[OK] {rel}: 変更なし")
        elif status == "would-change":
            print(f"[DIFF] {rel}: 差分あり（--check のため書き込みません）")
            would_change.append(rel)
        elif status == "changed":
            print(f"[UPDATED] {rel}: マーカーブロックを更新しました")
            changed.append(rel)

    print()
    if marker_errors:
        print(f"{len(marker_errors)} 件のファイルでマーカーエラーが発生しました: {', '.join(marker_errors)}")
        return 1

    if check:
        if would_change:
            print(f"差分あり: {', '.join(would_change)}")
            return 1
        print("変更なし")
        return 0

    if changed:
        print(f"更新したファイル: {', '.join(changed)}")
        return 1
    print("変更なし")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check = "--check" in args
    print("=== generate_file_map: ファイルマップ生成 ===\n")
    return run(TARGETS, check=check)


if __name__ == "__main__":
    sys.exit(main())
