# B-23 要件: Full Build の Step 3（Contextual Retrieval）を夜間バッチに分離

最終更新: 2026-05-13

## 背景・動機

Step 3（Contextual Retrieval: チャンクごとの文脈付与 + 再 embedding）は 303 チャンク × Qwen 呼び出し + bge-m3 再 embedding のため 10〜20 分かかり、PC 全体が重くなる。

一方、Step 1+2 完了後すぐに検索・QA は動作するため、Step 3 を後回しにしても日常利用への影響は小さい。

## 方針

- **Full Build（Step 1+2 のみ）**: `mode=full_build` は Step 1（チャンク分割 + embedding 構築）と Step 2（サマリ + キャラクター一括生成）だけを実行する。
- **コンテキスト生成（Step 3 のみ）**: `mode=generate_contexts` という新ジョブモードを追加し、Build 管理画面から別ボタンで手動投入する。

## 決定事項一覧

| カテゴリ | 決定 |
|---|---|
| Full Build のデフォルト | Step 1+2 のみ（Step 3 を除去） |
| Step 3 の起動方法 | Build 画面に「コンテキスト生成」ボタンを別途追加 |
| 書籍選択 UI | 既存ドロップダウン（個別指定 / 全冊）をそのまま流用 |
| 部分失敗後の再実行 | `contextual_text IS NULL` のチャンクのみ対象（途中失敗を自動リカバリ） |
| Full Build 再実行後 | Step 1 でチャンクが再生成されるためコンテキスト情報はリセット。Step 3 再投入はユーザー責任 |

## スコープ外

- 自動スケジューリング UI（Windows タスクスケジューラ等による夜間自動実行の UI 化）
- 書籍カードへの Step 3 完了状態の表示
- Step 3 の進捗リアルタイム表示（`current_detail` 連携は B-22 の範囲）

## 影響ファイル

| ファイル | 変更内容 |
|---|---|
| `backend/services/novel_db/full_builder.py` | `build_book_full()` から Step 3 呼び出しを除去 |
| `backend/services/novel_db/job_queue.py` | `mode=generate_contexts` の分岐を追加。`_execute_job` で `_run_generate_contexts` を呼ぶ |
| `backend/routers/novel_build.py` | エンキューエンドポイントに `mode=generate_contexts` を受け付ける |
| `frontend/src/pages/NovelBuildPage.tsx` | 「コンテキスト生成をエンキュー」ボタンを追加 |
| `docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md` | Full Build フロー図を Step 1+2 と Step 3 に分割して更新 |

## 完了条件

1. Full Build（Step 1+2）が旧来より大幅に短時間で完了する
2. 「コンテキスト生成」ジョブがキューで正常実行・完了する
3. 途中失敗後に再投入すると未処理チャンクのみ対象になる
4. バックエンド設計書の Full Build フロー図を更新済み
5. `uv run pytest -q` が全通過する
