# ADR-0011: GitHub Actions CI 導入（PR 品質ゲートの自動化）

- **Status**: Accepted
- **Date**: 2026-06-11
- **決定者**: 開発者
- **関連**: ADR-0010（uv workspace）/ Phase 0-2 / commit `4949e41`

## コンテキスト

`.github/` ディレクトリが存在せず、**CI/CD が完全に不在**だった。バックエンド 67 本・フロントエンド 101 本のテスト、ruff lint、tsc 型チェック、Playwright E2E がすべて手動実行の状態で、ライブラリ更新やリファクタリングが安全にできないリスクがあった。

ライブラリは既に最先端（React 19 / Vite 8 / TS 6 / Python 3.12 / FastAPI / Pydantic v2）で、「テストが手動でも回る」ことは確認済みだが、継続的に回す仕組みがなかった。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. CI なし継続 | 変更なし | 手動テストの抜け漏れが増える一方 |
| B. pre-commit のみ | ローカルフック（Phase 0-4）で担保 | push 前の保証のみ。PR マージ時の自動チェックがない |
| **C. GitHub Actions PR ゲート** | push / PR トリガーで backend + frontend を自動テスト | （採用） |

## 決定

`.github/workflows/ci.yml` を新規作成する。`ubuntu-latest` ランナーで backend ジョブ（ruff + basedpyright + pytest --cov-fail-under=65）と frontend ジョブ（eslint + tsc --noEmit + vitest）を並列実行する。

## 根拠

- Linux ランナーを使うことで Windows 特有のパス問題（日本語ファイル名など）を回避できる
- `--cov-fail-under=65` でカバレッジ下限を固定し、テスト削除による意図しないデグレを検知できる
- ADR-0010 の uv workspace 化によりクローン単体ビルドが可能になったため、CI での `uv sync` が実現できた

## 結果（Consequences）

### ポジティブ
- PR ごとに lint / 型チェック / テストが自動で回る
- リファクタリング（Phase 1〜3）でのデグレ検知が機械的に担保された
- basedpyright（ADR-0003 相当）を CI ゲートに組み込み、型ヒントの健全性を継続検証できる

### ネガティブ・受容したコスト
- GitHub Actions の無料枠消費（個人用途なので実質無限）
- CI 設定ファイルのメンテが必要（依存バージョン変更時など）

### 影響範囲
- `.github/workflows/ci.yml`（新規）
- `backend/pyproject.toml`（pytest.ini_options asyncio_mode=auto 追加）

## 将来の再評価条件

- E2E テスト（Playwright）が安定したら CI に組み込む
- デプロイ自動化（CD）が必要になった場合は本ワークフローを拡張する

## 2026-07-18 追補: サプライチェーン検査

CIの復旧後、品質ゲートを次の3系統へ拡張した。

- gitleaks による秘密情報検査（pre-commit + GitHub Actions）
- `npm audit` によるフロントエンド依存監査
- 期限・理由付きallowlistを検証するラッパー経由の `uv audit --locked`

GPU依存の既知脆弱性は無期限に黙殺せず、期限切れをCI失敗にする。即時更新可能な通常依存はallowlistへ入れず更新で解消する。
