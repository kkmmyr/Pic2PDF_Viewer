# ADR-0008: 設計ドキュメントを Markdown 編集 + mkdocs-material で HTML 配信

- **Status**: Accepted
- **Date**: 2026-05-11
- **決定者**: プロジェクトオーナー
- **関連**: [docs/index.md](../../index.md) / `mkdocs.yml`（プロジェクトルート） / `backend/main.py`（`/docs-html` マウント） / `.claude/CLAUDE.md`「設計ドキュメントの HTML 配信」セクション

## コンテキスト

`docs/` 配下の設計ドキュメントは累計で 20+ 本、長いもので 1,000 行超に達してきた。以下の課題が顕在化:

- **可読性**: 長い Markdown はテキストエディタや GitHub プレビューでは構造が掴みにくい。VSCode の MD プレビューは便利だが、TOC・サイドバー・検索が弱い
- **共有/レビュー**: 100 行を超える MD を腰を据えて読んでもらうのは現実的に難しい
- **視覚要素の不足**: ASCII アート図に頼っており、フロー / シーケンス / 関係図が表現しづらい
- **将来の読者**: 数ヶ月後の自分や別の Claude セッションが横断的に参照するときの導線が弱い

一方で:
- **Claude Code が読み書きする** ドキュメントが多い（人より Claude のほうが頻繁にアクセス）
- HTML 直書きにすると **Claude の read/edit/grep の効率が落ちる**（タグによる token 膨張、編集失敗率増、cross-doc 整合チェックの精度低下）
- 既存 MD 資産（ADR 7 件、設計書 10+ 件、運用知見、変更履歴）の継続利用が前提

「Claude にやさしい MD を保ちつつ、人間の閲覧性を上げる」両立策が必要。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. 全面 HTML 化（thariqs の記事方針）| 設計書すべてを HTML で記述・編集 | Claude の token 効率低下・edit 失敗率増加。grep / cross-doc 整合チェックの精度劣化。既存 MD 資産を全変換するコストも大 |
| B. Markdown のまま + Mermaid / SVG で視覚要素を強化 | 既存運用維持 + 図を Mermaid に置換 | 視覚的改善はできるが、TOC / サイドバー / 全文検索 / レスポンシブ表示は得られない |
| **C. MD ソース + mkdocs-material で HTML ビルド（採用）** | ソースは MD、ビルド時に site/ へ HTML 生成 | （採用） |
| D. mkdocs ではなく Pandoc 等の単発変換 | MD → 単一 HTML | サイドバーナビゲーションや横断検索を独自実装するコストが高い |
| E. mdBook / VitePress / Sphinx 等 | 他の doc 生成ツール | mkdocs-material は Python ネイティブで uv との親和性が高い。Sphinx は reStructuredText 寄り。mdBook は Rust 環境が要る |

## 決定

1. **ソース・オブ・トゥルース** は `docs/*.md`（Markdown）。Claude Code は今までどおり MD を読み書きする
2. **HTML 配信** は `mkdocs-material` で `site/` ディレクトリにビルドし、FastAPI が `/docs-html` で配信する
3. `site/` は `.gitignore`。`mkdocs build` で都度生成
4. 開発時プレビューは `mkdocs serve`（`http://localhost:8000`、ファイル変更で自動リロード）
5. 統合モード（FastAPI `:8090`）では `http://localhost:8090/docs-html/` から閲覧
6. **Mermaid 図** を ` ```mermaid` フェンスで MD 内に記述可能（mkdocs-material が描画）

## 根拠

### 「ソースは MD」維持の理由

- Claude Code が **最も頻繁にアクセスする読者** であり、Read / Edit / Grep の効率が高い形式を保つ必要がある
- HTML 直書きすると:
    - Read 時の token 消費が 1.5〜2 倍に膨張 → 長文ドキュメントで context が圧迫
    - Edit の `old_string` マッチが不安定化（改行・属性順・空白の差で「not found」連発）
    - Grep がタグまみれになりノイズ増加
    - 複数ファイル整合チェック（例: 「§5.7 の言及を全設計書から検出」）の精度低下
- 既存 MD 資産（ADR 7 件、設計書 10+ 件、運用知見、変更履歴）が継続利用できる

### mkdocs-material 採用の理由

- **Python ネイティブ**: uv tool でインストール可能、別言語ランタイム不要
- **多階層ナビ + 全文検索**: 設計書ツリーがそのまま左サイドバーに展開、日本語含む検索が動く
- **Mermaid 内蔵**: `pymdownx.superfences` + `mermaid2` プラグインで ` ```mermaid` がそのまま描画
- **ダークモード / モバイル対応**: テーマ機能で標準対応
- **ライセンス**: BSD（無償利用可）

### FastAPI 統合の理由

- 既存の StaticFiles マウントパターン（`/kindle_novel/images` 等）の延長で `/docs-html` を 1 行追加
- 統合モード（`:8090`）でアプリと同居しているため、ブックマーク 1 つで全機能にアクセスできる
- ローカル LAN ツールという性質上、外部公開（S3 等）は不要

## 結果（Consequences）

### ポジティブ

- 設計書の閲覧体験が大幅改善（サイドバー / 検索 / ダークモード / レスポンシブ）
- Claude の読み書き効率は維持（MD のまま）
- Mermaid で図を書けるようになり、ASCII 図から脱却可能
- 視覚要素を増やしながらも git diff が読める（MD ベースなので）

### ネガティブ・受容したコスト

- **ビルドステップが増える**: 設計書を編集した後 `mkdocs build` が必要。CI 等で自動化していないので忘れる可能性あり。`mkdocs serve` で開発中は自動リロードされるため、忘れ問題は実機運用時のみ
- **2 ファイル状態の混在**: MD（ソース） + HTML（成果物）。`site/` は .gitignore なので git で混乱しないが、デプロイ手順は意識が必要
- **依存ツール増**: `mkdocs` / `mkdocs-material` / `mkdocs-mermaid2-plugin` を開発者がインストールする必要がある（`uv tool install` で 1 コマンド）
- **PATH 設定**: `uv tool install` 後、`~/.local/bin` が PATH にないと `mkdocs` コマンドが見つからない（`uv tool update-shell` または手動 PATH 設定が必要）

### 既存リンクのアンカー警告（受容）

`mkdocs build` 実行時に 200+ 件の INFO 警告（古いリンクアンカー、見出しリネーム由来）が出る。サイト動作には影響しないが、徐々に解消したい。`/check-docs` スラッシュコマンドで網羅検出可能。

### 影響範囲

- 変更が及ぶファイル:
    - 新規: `mkdocs.yml`（プロジェクトルート）
    - 新規: `docs/index.md`（ランディングページ）
    - 修正: `.gitignore`（`site/` 追加）
    - 修正: `backend/main.py`（`/docs-html` マウント追加、`PROJECT_ROOT` import）
    - 修正: `.claude/CLAUDE.md`（「設計ドキュメントの HTML 配信」セクション追加）

- 後続作業:
    - 設計書中の ASCII 図を順次 Mermaid に置換（任意）
    - アンカー警告のクリーンアップ（`/check-docs` 経由、低優先）

## 将来の再評価条件

- **MkDocs 2.0 リリース時**: 現行 Material は MkDocs 2.0 で動作しなくなる予定（ビルド警告で告知済み）。リリースされたら Material の対応バージョンに pin するか別ツールに移行する判断が必要
- **設計書が極度に大規模化**（例: 100 ファイル超）した場合: より重量級の Sphinx / Docusaurus 等への移行を再検討
- **複数人開発体制**になった場合: HTML を git に commit してデプロイ前提でも良いかもしれない（CI ビルドが面倒な場合）
- **mkdocs-material のライセンス変更時**: 現在 BSD だが、Material 2.0 で変わる可能性あり。商用利用への切替時は再確認
