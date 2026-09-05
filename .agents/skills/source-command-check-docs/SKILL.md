---
name: "source-command-check-docs"
description: "設計書（要件定義/基本設計/詳細設計書[バックエンド編・フロントエンド編・フロントエンド_ファイルマップ・共通]/API.md（一覧は /openapi.json））と実装の整合性をクロスチェックする"
---

# source-command-check-docs

Use this skill when the user asks to run the migrated source command `check-docs`.

## Command Template

設計書と実装の整合性チェックを実行してください。Phase 完了直後・大きな機能追加後・リファクタリング後の検証用。

## チェック対象（`docs-cross-checker` agent への範囲指定に使う）

| 設計書 | 実装との対応 |
|---|---|
| `docs/design/要件定義/要件定義書.md` | 機能の存在 |
| `docs/design/基本設計/基本設計書.md` | アーキテクチャ・技術スタック |
| `docs/design/詳細設計/詳細設計書_バックエンド編.md` | バックエンドのHTTP・共通サービス・保存責務 |
| `docs/design/詳細設計/詳細設計書_バックエンド_ファイルマップ.md` | backend／Kindleの自動生成ファイルマップ |
| `docs/design/詳細設計/詳細設計書_フロントエンド_ファイルマップ.md` | フロントエンドのファイルマップ（最重要）|
| `docs/design/詳細設計/詳細設計書_フロントエンド編.md` | Context／フック／UI／コンポーネント設計 |
| `docs/design/詳細設計/詳細設計書_共通.md` | 全体配置・source・静的配信・リリース構成 |
| `docs/design/詳細設計/API.md` | OpenAPIで表せない境界・失敗時挙動（一覧と型は`/openapi.json`） |
| `docs/design/詳細設計/機能別/OCR設計書.md` | OCR候補・QA・公開 |
| `docs/design/詳細設計/機能別/Kindle自動撮影ジョブ契約.md` | job・manifest・登録補償・シリーズ実行 |
| `kindle-pdf/docs/detailed_design.md` | WindowsのUI操作・撮影内部 |

## 進め方

1. **`docs-cross-checker` サブエージェントを呼ぶ**（長文の設計書をメイン context に乗せないため、自分で Read して回らない）。
   - ユーザーから対象領域の指定があればその領域だけを、なければ上表の全領域を対象として渡す
   - 実装側の新規/削除ファイルの手がかりとして `git log --stat` や `git diff --stat HEAD~10` の参照も併せて依頼してよい
2. agent が返す差分（`[仕様未実装]` / `[実装が設計外]` / `[仕様乖離]`）を受け取る。差分が大量なら agent 側が Top 10 を返すので、続きが必要かここで判断する。
3. 差分がなければ「整合性 OK」とそのまま報告して終了。差分があれば下記フォーマットに整形して提示する。

## 報告フォーマット

```markdown
## 整合性チェック結果

### ✅ 整合済み
- 〇〇〇

### ⚠️ 不整合（要修正）

#### 詳細設計書（バックエンド編／フロントエンド編）
- [ ] AAA — 実装にあるが設計書に未記載: ファイルパス
- [ ] BBB — 設計書にあるが実装にない: ファイルパス

#### API.md（一覧は /openapi.json）
- [ ] CCC — OpenAPIと実装の契約不一致: `POST /api/xxx`
- [ ] DDD — レスポンス例の不一致

### 📝 参考指摘（リファクタリング範囲外）
- 要件定義書に未反映の機能: ...
```

## 修正方針

不整合が見つかった場合：
- **修正してもよいか確認**してから着手する（勝手に大規模 docs 編集をしない）
- 1 設計書 = 1 コミット で分割するか、まとめて 1 コミットにするかをユーザーに聞く
- 修正後は `docs/log/変更履歴.md` にも記録する
