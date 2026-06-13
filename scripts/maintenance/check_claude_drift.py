"""`.claude/**/*.md` 内のローカルパス参照が実在するか検査する。

markdown リンク `[..](target)` のローカルターゲットと、バックティック内の
パス様トークン（`/` を含み既知ルート配下または拡張子付き）を抽出し、
リポジトリルート基準（リンクは記載ファイル相対も試す）で実在検証する。

usage:
    cd backend && uv run python ../scripts/maintenance/check_claude_drift.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Windows 環境で日本語ファイルパスが文字化けしないよう UTF-8 出力を強制
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = PROJECT_ROOT / ".claude"

KNOWN_ROOTS = (
    "backend/",
    "frontend/",
    "docs/",
    "scripts/",
    ".claude/",
    "common/",
    "kindle-pdf/",
    "data/",
    # memory/ はプロジェクトルートに存在しない（グローバルメモリは C:\Users\... 配下）
    # KNOWN_ROOTS に含めると memory/ を prefix 検出対象にしてしまい偽陽性になるため除外
)

# .claude/ 内での省略記法（`commands/x` → `.claude/commands/x` 等）
CLAUDE_SHORTCUTS = (
    "commands/",
    "skills/",
    "agents/",
    "hooks/",
)

# backend/ 内パスの省略記法（`services/x.py` → `backend/services/x.py` 等）
# SKILL.md ではバックエンドのファイルを backend/ プレフィックスなしで書くことがある
BACKEND_SHORTCUTS = (
    "services/",
    "routers/",
    "utils/",
    "config/",
    "tests/",
)

# frontend/src/ 内での省略記法
FRONTEND_SRC_SHORTCUTS = (
    "components/",
    "hooks/",
    "lib/",
    "api/",
    "src/",
    "test/",  # frontend/src/test/ 配下のテストファイル
)

EXTERNAL_PREFIXES = (
    "http://",
    "https://",
    "~/",
    "~\\",
    "@/",       # TypeScript パスエイリアス（実ファイルパスではない）
    "memory/",  # グローバルメモリはプロジェクト外（C:\Users\...\memory\）
    "Z:",
    "C:",
    "D:",
    "\\\\",
)

ATTR_REF_RE = re.compile(r"::")
GLOB_CHARS_RE = re.compile(r"[*?{}]")
PLACEHOLDER_RE = re.compile(r"<[^>]+>")
MD_LINK_RE = re.compile(r"\[(?:[^\]]*)\]\(([^)#\s][^)]*)\)")
BACKTICK_TOKEN_RE = re.compile(r"`([^`\n]+)`")


def _is_path_like(token: str) -> bool:
    t = token.strip()
    if not t or "/" not in t:
        return False
    if GLOB_CHARS_RE.search(t):
        return False
    if PLACEHOLDER_RE.search(t):
        return False
    if ATTR_REF_RE.search(t):
        return False
    if any(t.startswith(ext) or t.lower().startswith(ext.lower()) for ext in EXTERNAL_PREFIXES):
        return False
    has_known_root = any(
        t.startswith(root) or f"/{root}" in t or t.lstrip("./").startswith(root)
        for root in KNOWN_ROOTS
    )
    has_extension = bool(re.search(r"\.[a-zA-Z]{2,6}$", t.split("/")[-1]))
    return has_known_root or has_extension


def _normalize_link_target(target: str) -> str:
    return target.split("#")[0].strip()


def _should_skip_target(raw: str) -> bool:
    t = raw.strip()
    if not t:
        return True
    if PLACEHOLDER_RE.search(t):
        return True
    if GLOB_CHARS_RE.search(t):
        return True
    if ATTR_REF_RE.search(t):
        return True
    return any(t.startswith(ext) or t.lower().startswith(ext.lower()) for ext in EXTERNAL_PREFIXES)


def _resolve(target: str, source_file: Path) -> Path | None:
    t = target.strip().lstrip("/")
    # 試行1: リポジトリルート基準
    candidate_root = PROJECT_ROOT / t
    if candidate_root.exists():
        return candidate_root
    # 試行2: ソースファイルからの相対パス
    candidate_rel = (source_file.parent / target).resolve()
    if candidate_rel.exists():
        return candidate_rel
    # 試行3: .claude/ 省略記法
    for shortcut in CLAUDE_SHORTCUTS:
        if t.startswith(shortcut):
            candidate = PROJECT_ROOT / ".claude" / t
            if candidate.exists():
                return candidate
    # 試行4: frontend/src/ 省略記法
    for shortcut in FRONTEND_SRC_SHORTCUTS:
        if t.startswith(shortcut):
            candidate = PROJECT_ROOT / "frontend" / "src" / t
            if candidate.exists():
                return candidate
            candidate2 = PROJECT_ROOT / "frontend" / t
            if candidate2.exists():
                return candidate2
    # 試行5: backend/ 省略記法（SKILL.md でよく使われる backend/ プレフィックスなし参照）
    for shortcut in BACKEND_SHORTCUTS:
        if t.startswith(shortcut):
            candidate = PROJECT_ROOT / "backend" / t
            if candidate.exists():
                return candidate
    return None


def check_drift() -> list[tuple[str, int, str]]:
    broken: list[tuple[str, int, str]] = []
    for md_file in sorted(CLAUDE_DIR.rglob("*.md")):
        rel_file = md_file.relative_to(PROJECT_ROOT)
        lines = md_file.read_text(encoding="utf-8", errors="replace").splitlines()
        in_code_fence = False
        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_code_fence = not in_code_fence
            if in_code_fence and not (stripped.startswith("```") or stripped.startswith("~~~")):
                continue
            for m in MD_LINK_RE.finditer(line):
                raw = m.group(1)
                if _should_skip_target(raw):
                    continue
                target = _normalize_link_target(raw)
                if not target:
                    continue
                if _resolve(target, md_file) is None:
                    broken.append((str(rel_file), lineno, target))
            for m in BACKTICK_TOKEN_RE.finditer(line):
                token = m.group(1)
                if not _is_path_like(token):
                    continue
                if _should_skip_target(token):
                    continue
                candidates = token.split() if " " in token else [token]
                for cand in candidates:
                    cand = cand.strip().strip("'\"(),;")
                    if not _is_path_like(cand):
                        continue
                    if _should_skip_target(cand):
                        continue
                    if _resolve(cand, md_file) is None:
                        broken.append((str(rel_file), lineno, cand))
    return broken


def main() -> None:
    broken = check_drift()
    if not broken:
        print("ドリフトなし（存在しないローカルパス参照: 0件）")
        sys.exit(0)
    print(f"存在しないローカルパス参照: {len(broken)} 件\n")
    for file_path, lineno, ref in broken:
        print(f"  {file_path}:{lineno} -> {ref}")
    sys.exit(0)  # 列挙のみ、判断は人間に委ねる


if __name__ == "__main__":
    main()
