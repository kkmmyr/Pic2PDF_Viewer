"""`docs/**/*.md` の整合性を検査する（pre-commit フックからコミットをブロックする）。

check_claude_drift.py（`.claude/` 向け・常に exit 0 の人間判断ツール）とは異なり、
本スクリプトは違反があれば **exit 1** する。以下 3 ルールを検査する。

  Rule 1: docs 間の相対 Markdown リンク切れ
  Rule 2: メインの変更履歴.md の行数肥大化（週次ローテーション漏れ）
  Rule 3: mkdocs.yml の nav ツリーとの同期（dead entry / orphan ファイル）

usage:
    uv run python scripts/maintenance/check_docs.py

リポジトリルートから実行する想定（pre-commit hook から `uv run python
scripts/maintenance/check_docs.py` として呼ばれる）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

# Windows 環境で日本語ファイルパスが文字化けしないよう UTF-8 出力を強制
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"
MKDOCS_YML = PROJECT_ROOT / "mkdocs.yml"

# Rule 2: メインの変更履歴.md がこの行数を超えたら、古い週を
# 変更履歴/YYYY-Www.md にローテーションするよう促す
CHANGELOG_LINE_LIMIT = 800

MD_LINK_RE = re.compile(r"\[(?:[^\]]*)\]\(([^)#\s][^)]*)\)")
WEEKLY_CHANGELOG_RE = re.compile(r"^\d{4}-W\d{2}\.md$")


# ---------------------------------------------------------------------------
# Rule 1: docs 間の相対リンク切れ
# ---------------------------------------------------------------------------


def _iter_non_fenced_lines(md_file: Path):
    """フェンス付きコードブロック外の (行番号, 行) を yield する。"""
    lines = md_file.read_text(encoding="utf-8", errors="replace").splitlines()
    in_fence = False
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield lineno, line


def check_broken_links() -> list[str]:
    """docs/**/*.md 内の相対 Markdown リンク（*.md 宛て）の切れを検出する。

    リンクはリンク元ファイル自身のディレクトリ基準で解決する（このリポジトリの
    docs 内リンクは実際にそう書かれているため。例: `../05_記録/変更履歴.md`）。
    """
    violations: list[str] = []
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        rel_file = md_file.relative_to(PROJECT_ROOT)
        for lineno, line in _iter_non_fenced_lines(md_file):
            for m in MD_LINK_RE.finditer(line):
                raw = m.group(1).strip()
                if not raw or raw.startswith("#"):
                    continue
                if raw.lower().startswith(("http://", "https://")):
                    continue
                # アンカーとタイトル ( `path.md "title"` ) を除去
                target = raw.split("#")[0].strip()
                target = re.split(r'\s+["\']', target, maxsplit=1)[0].strip()
                if not target.lower().endswith(".md"):
                    continue
                resolved = (md_file.parent / target).resolve()
                if not resolved.exists():
                    violations.append(f"{rel_file}:{lineno} -> {raw}")
    return violations


# ---------------------------------------------------------------------------
# Rule 2: 変更履歴.md の行数肥大化
# ---------------------------------------------------------------------------


def check_changelog_size() -> list[str]:
    """メインの変更履歴.md（`変更履歴/` サブフォルダ配下の週次アーカイブを除く）
    が CHANGELOG_LINE_LIMIT 行を超えていないか検査する。

    バケットフォルダ名（`05_記録/` 等）はハードコードしない。ファイル名パターン
    のみで探すため、移行フェーズでバケットが変わっても動作し続ける。
    """
    violations: list[str] = []
    candidates = [p for p in DOCS_DIR.rglob("変更履歴.md") if p.parent.name != "変更履歴"]
    for p in sorted(candidates):
        rel = p.relative_to(PROJECT_ROOT)
        line_count = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
        if line_count > CHANGELOG_LINE_LIMIT:
            violations.append(
                f"{rel}: {line_count} 行（上限 {CHANGELOG_LINE_LIMIT} 行を超過）"
                f" -> 古い週を 変更履歴/YYYY-Www.md にローテーションしてください"
            )
    return violations


# ---------------------------------------------------------------------------
# Rule 3: mkdocs.yml nav 同期（dead entry / orphan）
# ---------------------------------------------------------------------------


class _LenientYamlLoader(yaml.SafeLoader):
    """mkdocs.yml の markdown_extensions 内で使われる
    `!!python/name:...` タグを無視して読み飛ばすための Loader。
    nav: セクションの解析にしか興味がないため、未知タグはエラーにせず None を返す。
    """


def _ignore_python_tag(loader: yaml.Loader, suffix: str, node: yaml.Node) -> None:
    return None


_LenientYamlLoader.add_multi_constructor("tag:yaml.org,2002:python/name:", _ignore_python_tag)


def _load_mkdocs_nav() -> list:
    text = MKDOCS_YML.read_text(encoding="utf-8")
    data = yaml.load(text, Loader=_LenientYamlLoader)
    if not isinstance(data, dict):
        return []
    nav = data.get("nav", [])
    return nav if isinstance(nav, list) else []


def _collect_nav_paths(node) -> list[str]:
    """nav ツリー（入れ子の list / dict）から、docs_dir 相対のファイルパス文字列を
    すべて収集する。"""
    paths: list[str] = []
    if isinstance(node, str):
        paths.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            paths.extend(_collect_nav_paths(v))
    elif isinstance(node, list):
        for item in node:
            paths.extend(_collect_nav_paths(item))
    return paths


def _is_exempt_orphan(rel: Path) -> bool:
    """nav 未掲載でも許容される（本文リンク・索引経由でのみ到達する）ファイルか判定する。
    フォルダ名の「部分一致」ではなく「セグメント完全一致」で判定する
    （例: `要件` フォルダに `要件定義` フォルダが誤って一致しないように）。
    """
    if rel.as_posix() == "index.md":
        return True

    parts = rel.parts

    # ADR 配下は README.md 以外すべて免除
    if "ADR" in parts:
        if rel.name == "README.md" and len(parts) >= 2 and parts[-2] == "ADR":
            return False
        return True

    # 変更履歴/ 配下の週次アーカイブ（YYYY-Www.md）は索引経由のため免除
    if "変更履歴" in parts and WEEKLY_CHANGELOG_RE.match(rel.name):
        return True

    # アーカイブ配下の 要件/ フォルダ（撤去済み機能の個別要件定義）は免除
    if "要件" in parts and ("archive" in parts or "99_アーカイブ" in parts):
        return True

    return False


def check_nav_sync() -> list[str]:
    """mkdocs.yml の nav ツリーと docs/**/*.md の実ファイルを突き合わせ、
    (a) 実在しないファイルを指す dead nav entry と
    (b) nav にもエグゼンプションにも該当しない orphan ファイル
    を検出する。
    """
    violations: list[str] = []
    nav_paths = _collect_nav_paths(_load_mkdocs_nav())

    # (a) dead nav entries
    for p in nav_paths:
        resolved = DOCS_DIR / p
        if not resolved.exists():
            violations.append(f"[dead nav entry] mkdocs.yml nav -> {p} (ファイルが存在しません)")

    # (b) orphans
    nav_path_set = {Path(p).as_posix() for p in nav_paths}
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        rel = md_file.relative_to(DOCS_DIR)
        rel_posix = rel.as_posix()
        if rel_posix in nav_path_set:
            continue
        if _is_exempt_orphan(rel):
            continue
        violations.append(
            f"[orphan] docs/{rel_posix} は mkdocs.yml の nav に存在しません（かつ免除対象でもありません）"
        )

    return violations


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    broken_links = check_broken_links()
    changelog_over = check_changelog_size()
    nav_violations = check_nav_sync()

    print("=== check_docs: docs/ 整合性チェック ===\n")

    print(f"[Rule 1] docs 間リンク切れ: {len(broken_links)} 件")
    for line in broken_links:
        print(f"  {line}")
    print()

    print(f"[Rule 2] 変更履歴.md 行数超過 (> {CHANGELOG_LINE_LIMIT} 行): {len(changelog_over)} 件")
    for line in changelog_over:
        print(f"  {line}")
    print()

    print(f"[Rule 3] mkdocs.yml nav 同期 (dead entry / orphan): {len(nav_violations)} 件")
    for line in nav_violations:
        print(f"  {line}")
    print()

    total = len(broken_links) + len(changelog_over) + len(nav_violations)
    if total == 0:
        print("違反なし。")
        sys.exit(0)
    print(f"合計 {total} 件の違反を検出しました。")
    sys.exit(1)


if __name__ == "__main__":
    main()
