## 概要

<!-- 何を・なぜ。1〜3 行で。 -->

## 種別

<!-- 該当するものに x を入れる -->

- [ ] feat / fix / refactor（コード変更）
- [ ] docs（設計書のみ）
- [ ] chore / test

## 設計書 DoD（設計の意図・API・データ構造に影響する変更のみ）

- [ ] 関連する `docs/design/` 設計書を **現在形で** 更新した（`> status:` の `last-verified` 日付も更新）
- [ ] 機能単位の設計文書をクローズする場合: 現在形を `docs/design/` の **component 軸文書へ吸収** し、設計過程の原本を `docs/archive/` へ **📦 バナー付きで凍結** した
- [ ] 横断的な事実（ポート・環境変数・スキーマ・ディレクトリレイアウト等）は **正本マップ（[`docs/index.md`](../docs/index.md)）が定める所有文書のみ** に記載し、他所はそこへのリンクにした（二重記載しない）
- [ ] `docs/log/変更履歴.md` に `## YYYY-MM-DD: type — タイトル` 形式で追記した

## 検証

- [ ] `uv run python scripts/maintenance/check_docs.py` が green（Rule 1/2/3/5 のブロッキング違反ゼロ）
- [ ] backend 変更あり: `cd backend && uv run pytest -q`
- [ ] frontend 変更あり: `cd frontend && npm run test` / 型変更あり: `npx tsc --noEmit`

<!--
設計書ガバナンスの詳細は docs/index.md の「正本マップ」「整合性の自動チェック（ガバナンス）」節を参照。
軽微な変更（typo・コメント整理・フォーマットのみ）では設計書 DoD はスキップしてよい。
-->
