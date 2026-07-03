"""`.claude/**/*.md` と グローバル `memory/**/*.md` 内のローカルパス参照が
実在するか検査する。あわせて `mkdocs.yml` の nav ツリーの dead entry と、
`.claude/README.md` のスキル/コマンド一覧表と実体（`.claude/skills/` /
`.claude/commands/`）とのドリフトも検査する。

markdown リンク `[..](target)` のローカルターゲットと、バックティック内の
パス様トークン（`/` を含み既知ルート配下または拡張子付き）を抽出し、
リポジトリルート基準（リンクは記載ファイル相対も試す）で実在検証する。

`memory/` はプロジェクトルート外（`C:\\Users\\...\\memory\\`）にあるため、
`.claude/` とは別ディレクトリとして走査する。解決ロジック自体
（`_resolve()`）は共通で、リポジトリルート基準の解決と記載ファイル相対の
解決の両方を試すため、memory ファイル内の `docs/...` バックティック参照
（リポジトリルート基準）と memory ファイル同士の相対リンク（記載ファイル
基準）の両方をそのまま拾える。

`.claude/README.md` のスキル一覧・コマンド一覧は手動転記のテーブルのため、
`.claude/skills/*/SKILL.md` / `.claude/commands/*.md` の実体が増減しても
追随されず古くなりがち。`check_readme_registry_drift()` は実体（ディレクトリ /
ファイル）と README のテーブル記載を突き合わせ、両方向の差分（未掲載 / 実体なし）
を報告する。あわせて `.claude/hooks/README.md`（一覧表）と実体（`.claude/hooks/*.sh`、
`hooks/tests/` は除く）、および `.claude/README.md` のエージェント一覧表と実体
（`.claude/agents/*.md`）とのドリフトも同じ関数内で検査する。

report-only（人間の判断に委ねるツール）のため、常に exit 0。

usage:
    cd backend && uv run python ../scripts/maintenance/check_claude_drift.py
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
CLAUDE_DIR = PROJECT_ROOT / ".claude"
# グローバルメモリはプロジェクト外に存在する（リポジトリには含まれない）
MEMORY_DIR = Path(r"C:\Users\amashio\.claude\projects\d--61-tool-Pic2PDF-Viewer\memory")
MKDOCS_YML = PROJECT_ROOT / "mkdocs.yml"
CLAUDE_README = CLAUDE_DIR / "README.md"
SKILLS_DIR = CLAUDE_DIR / "skills"
COMMANDS_DIR = CLAUDE_DIR / "commands"
AGENTS_DIR = CLAUDE_DIR / "agents"
HOOKS_DIR = CLAUDE_DIR / "hooks"
HOOKS_README = HOOKS_DIR / "README.md"

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
    "@/",  # TypeScript パスエイリアス（実ファイルパスではない）
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
        t.startswith(root) or f"/{root}" in t or t.lstrip("./").startswith(root) for root in KNOWN_ROOTS
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


def check_drift(scan_dir: Path, display_root: Path, display_prefix: str = "") -> list[tuple[str, int, str]]:
    """scan_dir 配下の `*.md` を走査し、存在しないローカルパス参照を集める。

    表示用の相対パスは display_root 基準（+ display_prefix）で組み立てる。
    `.claude/` 呼び出しでは display_root=PROJECT_ROOT, display_prefix="" とし、
    従来と完全に同じ表示（`.claude/xxx.md:N -> ...`）になる。
    解決ロジック（_resolve）自体は scan_dir に関わらず PROJECT_ROOT 基準 /
    記載ファイル相対の両方を試すため、memory/ 配下のファイルでも
    「docs/ 始まりのバックティック参照（リポジトリルート基準）」と
    「memory ファイル同士の相対リンク（記載ファイル基準）」の両方を正しく拾う。
    """
    broken: list[tuple[str, int, str]] = []
    for md_file in sorted(scan_dir.rglob("*.md")):
        try:
            rel_file = md_file.relative_to(display_root)
        except ValueError:
            rel_file = md_file
        rel_label = f"{display_prefix}{rel_file}"
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
                    broken.append((rel_label, lineno, target))
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
                        broken.append((rel_label, lineno, cand))
    return broken


# ---------------------------------------------------------------------------
# mkdocs.yml nav の dead entry 検査（check_docs.py Rule 3 の簡易版・重複実装）
# ---------------------------------------------------------------------------


class _LenientYamlLoader(yaml.SafeLoader):
    """mkdocs.yml の markdown_extensions 内で使われる `!!python/name:...`
    タグを無視して読み飛ばすための Loader（nav: の解析にしか興味がないため）。"""


def _ignore_python_tag(loader: yaml.Loader, suffix: str, node: yaml.Node) -> None:
    return None


_LenientYamlLoader.add_multi_constructor("tag:yaml.org,2002:python/name:", _ignore_python_tag)


def _collect_nav_paths(node) -> list[str]:
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


def check_nav_dead_entries() -> list[str]:
    """mkdocs.yml の nav ツリーが存在しないファイルを指していないか検査する。"""
    if not MKDOCS_YML.exists():
        return []
    data = yaml.load(MKDOCS_YML.read_text(encoding="utf-8"), Loader=_LenientYamlLoader)
    nav = data.get("nav", []) if isinstance(data, dict) else []
    docs_dir = PROJECT_ROOT / "docs"
    violations: list[str] = []
    for p in _collect_nav_paths(nav):
        if not (docs_dir / p).exists():
            violations.append(f"mkdocs.yml nav -> {p} (ファイルが存在しません)")
    return violations


# ---------------------------------------------------------------------------
# .claude/README.md のスキル/コマンド一覧表と実体とのドリフト検査
# ---------------------------------------------------------------------------

TABLE_ROW_RE = re.compile(r"^\|\s*`([/A-Za-z0-9_.-]+)`")


def _discover_skills() -> set[str]:
    if not SKILLS_DIR.is_dir():
        return set()
    return {p.name for p in SKILLS_DIR.iterdir() if p.is_dir() and (p / "SKILL.md").exists()}


def _discover_commands() -> set[str]:
    if not COMMANDS_DIR.is_dir():
        return set()
    return {p.stem for p in COMMANDS_DIR.glob("*.md")}


def _discover_agents() -> set[str]:
    if not AGENTS_DIR.is_dir():
        return set()
    return {p.stem for p in AGENTS_DIR.glob("*.md")}


def _discover_hooks() -> set[str]:
    """`.claude/hooks/` 直下（`hooks/tests/` は含まない）の `*.sh` を列挙する。

    hook 名はテーブル側が拡張子込み（例: `remind_docs_update.sh`）で記載されるため、
    skills/commands と異なり拡張子を残したファイル名で返す。
    """
    if not HOOKS_DIR.is_dir():
        return set()
    return {p.name for p in HOOKS_DIR.glob("*.sh")}


def _extract_table_names_under_heading(lines: list[str], heading: str) -> set[str]:
    """README.md の指定見出しセクション内のテーブルから `name` トークンを抽出する。

    行頭が `` |`name` `` 形式（バックティック直後の英数字/ハイフン/アンダースコア/
    スラッシュ）のもののみをデータ行とみなし、ヘッダ行・区切り行（`|---|---|` 等）は
    自然に除外される。次の `## ` 見出しに到達したら走査を止める。
    """
    names: set[str] = set()
    in_section = False
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if line.strip() == heading:
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            m = TABLE_ROW_RE.match(line.strip())
            if m:
                names.add(m.group(1).lstrip("/"))
    return names


def check_readme_registry_drift() -> list[str]:
    """`.claude/README.md` のスキル/コマンド/エージェント一覧表と実体（skills/ commands/ agents/）を突き合わせる。"""
    if not CLAUDE_README.exists():
        return []
    lines = CLAUDE_README.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

    readme_skills = _extract_table_names_under_heading(lines, "## スキル一覧（現状）")
    readme_commands = _extract_table_names_under_heading(lines, "## スラッシュコマンド一覧（現状）")
    readme_agents = _extract_table_names_under_heading(lines, "## エージェント一覧（現状）")

    actual_skills = _discover_skills()
    actual_commands = _discover_commands()
    actual_agents = _discover_agents()

    issues: list[str] = []

    for name in sorted(actual_skills - readme_skills):
        issues.append(f"skill '{name}' が実体にあるが .claude/README.md のスキル一覧表に未掲載")
    for name in sorted(readme_skills - actual_skills):
        issues.append(
            f"skill '{name}' が .claude/README.md のスキル一覧表に記載されているが "
            f".claude/skills/{name}/SKILL.md が存在しない"
        )

    for name in sorted(actual_commands - readme_commands):
        issues.append(f"command '{name}' が実体にあるが .claude/README.md のコマンド一覧表に未掲載")
    for name in sorted(readme_commands - actual_commands):
        issues.append(
            f"command '{name}' が .claude/README.md のコマンド一覧表に記載されているが "
            f".claude/commands/{name}.md が存在しない"
        )

    for name in sorted(actual_agents - readme_agents):
        issues.append(f"agent '{name}' が実体にあるが .claude/README.md のエージェント一覧表に未掲載")
    for name in sorted(readme_agents - actual_agents):
        issues.append(
            f"agent '{name}' が .claude/README.md のエージェント一覧表に記載されているが "
            f".claude/agents/{name}.md が存在しない"
        )

    if HOOKS_README.exists():
        hooks_lines = HOOKS_README.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        readme_hooks = _extract_table_names_under_heading(hooks_lines, "## 一覧")
        actual_hooks = _discover_hooks()

        for name in sorted(actual_hooks - readme_hooks):
            issues.append(f"hook '{name}' が実体にあるが .claude/hooks/README.md の一覧表に未掲載")
        for name in sorted(readme_hooks - actual_hooks):
            issues.append(
                f"hook '{name}' が .claude/hooks/README.md の一覧表に記載されているが "
                f".claude/hooks/{name} が存在しない"
            )

    return issues


def main() -> None:
    claude_broken = check_drift(CLAUDE_DIR, PROJECT_ROOT)
    memory_broken = check_drift(MEMORY_DIR, MEMORY_DIR, display_prefix="memory/")
    nav_broken = check_nav_dead_entries()
    registry_broken = check_readme_registry_drift()

    print(f"[.claude/] 存在しないローカルパス参照: {len(claude_broken)} 件")
    for file_path, lineno, ref in claude_broken:
        print(f"  {file_path}:{lineno} -> {ref}")
    print()

    print(f"[memory/] 存在しないローカルパス参照: {len(memory_broken)} 件")
    for file_path, lineno, ref in memory_broken:
        print(f"  {file_path}:{lineno} -> {ref}")
    print()

    print(f"[mkdocs.yml nav] 存在しない参照先: {len(nav_broken)} 件")
    for line in nav_broken:
        print(f"  {line}")
    print()

    print(f"[.claude/README.md registry] スキル/コマンド/エージェント/hooks 一覧との差分: {len(registry_broken)} 件")
    for line in registry_broken:
        print(f"  {line}")
    print()

    total = len(claude_broken) + len(memory_broken) + len(nav_broken) + len(registry_broken)
    if total == 0:
        print("ドリフトなし（存在しないローカルパス参照: 0件）")
    else:
        print(f"合計 {total} 件（列挙のみ、判断は人間に委ねる）")
    sys.exit(0)  # 列挙のみ、判断は人間に委ねる


if __name__ == "__main__":
    main()
