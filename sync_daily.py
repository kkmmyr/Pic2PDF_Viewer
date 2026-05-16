#!/usr/bin/env python3
"""Pic2PDF_Viewer 日次同期チェック

実装・設計書・メモリのズレを毎日1回検出し、レポートを生成する。
run_sync_daily.bat から呼び出す想定（起動時 or タスクスケジューラ経由）。

実行条件:
- 当日フラグ (.claude/daily-flags/.synced_YYYY-MM-DD) がなければ実行
- 実行済みの場合はスキップ（同日内に何度起動しても1回のみ）
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
JST = timezone(timedelta(hours=9))
FLAGS_DIR = SCRIPT_DIR / ".claude" / "daily-flags"
REPORTS_DIR = SCRIPT_DIR / ".claude" / "daily-reports"
LOG_FILE = SCRIPT_DIR / "sync_daily.log"
CLAUDE_CMD = os.environ.get("CLAUDE_CMD", "claude")

FLAGS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ts = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def cleanup_old_flags(keep_days: int = 30) -> None:
    cutoff = datetime.now(JST) - timedelta(days=keep_days)
    for f in FLAGS_DIR.glob(".synced_*"):
        try:
            date_str = f.name.replace(".synced_", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=JST)
            if file_date < cutoff:
                f.unlink()
        except ValueError:
            pass


def run_claude(prompt: str, allowed_tools: str, timeout: int = 240) -> str:
    """Claude CLI を非インタラクティブ実行してテキスト出力を返す。"""
    try:
        result = subprocess.run(
            [
                CLAUDE_CMD, "-p", prompt,
                "--allowedTools", allowed_tools,
                "--output-format", "text",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=str(SCRIPT_DIR),
        )
    except subprocess.TimeoutExpired:
        return f"⚠️ タイムアウト（{timeout}秒）で完了しませんでした。"
    except FileNotFoundError:
        log(f"ERROR: claude コマンドが見つかりません: {CLAUDE_CMD}")
        sys.exit(1)

    if result.returncode != 0:
        return (
            f"⚠️ claude CLI エラー (exit {result.returncode})\n"
            f"```\n{result.stderr[:600]}\n```"
        )

    return result.stdout.strip()


def check_memory(project_dir: str) -> str:
    prompt = (
        f"プロジェクト {project_dir} のメモリと実装の同期状態をチェックし、"
        "Markdownレポートを出力してください。変更は一切行わないでください。\n\n"
        "## チェック手順\n"
        "1. C:\\Users\\amashio\\.claude\\projects\\d--61-tool-Pic2PDF-Viewer\\memory\\MEMORY.md を Read で読む\n"
        "2. MEMORY.md に記載された各メモリファイル (pending_tasks.md / project_refactoring.md など) を Read\n"
        "3. git log --oneline -20 を実行して直近コミットを確認\n"
        "4. pending_tasks.md に残っているタスクがすでにコミット済みか確認\n"
        "5. project_refactoring.md などのフェーズ番号がコミット内容と一致するか確認\n\n"
        "## 出力形式（このフォーマットで出力してください）\n"
        "## メモリ同期チェック結果\n"
        "### ✅ 一致\n"
        "- (一致している項目)\n"
        "### ⚠️ ズレ（要更新）\n"
        "- (ズレがある項目・なければ「なし」)\n"
        "### 📝 備考\n"
        "- (その他気づき・なければ省略)\n\n"
        "ユーザーへの質問・確認は不要です。チェック結果のみ出力してください。"
    )
    return run_claude(
        prompt,
        "Read,Glob,Grep,Bash(git log),Bash(git log *)",
        timeout=240,
    )


def check_docs(project_dir: str) -> str:
    prompt = (
        f"プロジェクト {project_dir} の設計書と実装の整合性をチェックし、"
        "Markdownレポートを出力してください。変更は一切行わないでください。\n\n"
        "## チェック手順\n"
        "1. git diff --stat HEAD~5 で直近5コミットの変更ファイルを確認\n"
        "2. docs/02_基本設計/アーキテクチャ詳細_バックエンド編.md を Read\n"
        "3. docs/02_基本設計/アーキテクチャ詳細_フロントエンド編.md を Read\n"
        "4. 変更されたバックエンド・フロントエンドのファイルが設計書のファイルマップに反映されているか確認\n"
        "5. backend/routers/ 配下の主要エンドポイントが docs/03_詳細設計/API仕様書.md に記載されているか確認\n\n"
        "## 出力形式（このフォーマットで出力してください）\n"
        "## 設計書整合性チェック結果\n"
        "### ✅ 整合済み\n"
        "- (整合している項目)\n"
        "### ⚠️ 不整合（要修正）\n"
        "- (不整合がある項目・なければ「なし」)\n"
        "### 📝 参考指摘\n"
        "- (軽微な指摘・なければ省略)\n\n"
        "ユーザーへの質問・確認は不要です。チェック結果のみ出力してください。"
    )
    return run_claude(
        prompt,
        "Read,Glob,Grep,Bash(git diff),Bash(git diff *),Bash(git log),Bash(git log *)",
        timeout=300,
    )


def main() -> None:
    cleanup_old_flags()

    now_jst = datetime.now(JST)
    today_str = now_jst.strftime("%Y-%m-%d")

    flag_file = FLAGS_DIR / f".synced_{today_str}"
    if flag_file.exists():
        print(f"Already synced for {today_str}, skipping.")
        sys.exit(0)

    project_dir = str(SCRIPT_DIR)
    log(f"=== 日次同期チェック開始: {today_str} ===")

    log("(1/2) メモリ同期チェック実行中 ...")
    memory_report = check_memory(project_dir)

    log("(2/2) 設計書整合性チェック実行中 ...")
    docs_report = check_docs(project_dir)

    report_file = REPORTS_DIR / f"{today_str}.md"
    report_content = (
        f"# 日次同期チェックレポート — {today_str}\n\n"
        f"実行日時: {now_jst.strftime('%Y-%m-%d %H:%M:%S')} JST\n\n"
        f"---\n\n"
        f"## 1. メモリ同期チェック\n\n"
        f"{memory_report}\n\n"
        f"---\n\n"
        f"## 2. 設計書整合性チェック\n\n"
        f"{docs_report}\n\n"
        f"---\n\n"
        f"> このレポートは自動生成されました。\n"
        f"> 修正が必要な場合は `/sync-memory` または `/check-docs` コマンドを実行してください。\n"
    )
    report_file.write_text(report_content, encoding="utf-8")

    flag_file.touch()
    log(f"=== 完了: {report_file} ===")
    print(f"\nレポートを保存しました: {report_file}")


if __name__ == "__main__":
    main()
