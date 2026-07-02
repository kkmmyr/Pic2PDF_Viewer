# Amazon CSV インポート機能 — 要件定義

## 1. 目的 / ユーザー価値

既存の comic / novel ライブラリエントリに対して、Amazon 購入履歴 CSV から著者名・ASIN を一括補完する。毎回手入力していたメタデータを自動化し、ライブラリ整備コストを削減する。

**対象ユーザー**: ライブラリ管理者（自分）

---

## 2. データソース

### CSV ファイル配置先（固定パス）

| 種別 | パス | 形式 | 期間 | 著者情報 |
|------|------|------|------|---------|
| 全期間エクスポート | `C:\Users\amashio\OneDrive\61.tool\amazon_data\amazon-order\Your Amazon Orders\Digital Content Orders.csv` | 英語ヘッダー | 2014年〜 | なし |
| 月別デジタル注文 | `C:\Users\amashio\OneDrive\61.tool\amazon_data\amazon-order_digital\*.csv` | 日本語ヘッダー | 2021年〜 | 「付帯情報」列に含む |

### 統合方針

1. `Digital Content Orders.csv` を読み込み → ASIN + タイトルを取得
   - `(Order ID, ASIN, Digital Order Item ID)` 単位で複数行を集約（Tax / Price Amount 等の重複行対策）
   - `category == "kindle"` のものだけ採用（サブスク・音楽を除外）
2. `amazon-order_digital/*.csv` を全件読み込み → 著者情報を ASIN で追加/補完
3. 最終的な lookup テーブル: `{asin: {title: str, authors: list[str]}}`

### エンコーディング検出

BOM 判定 → `chardet` による検出（confidence < 0.6 は UTF-8 フォールバック）→ SJIS 系は `cp932` に統一。  
参照実装: `D:\61.tool\kindle購入履歴\app\backend\src\kindle_viewer\importer\parser_utils.py` の `detect_encoding()`。

依存ライブラリ: `chardet`（`uv add chardet` で追加する）

### フィールド抽出ルール

| 項目 | ソース列 | 抽出ロジック |
|------|---------|------------|
| ASIN | `ASIN`（英語 CSV）/ `商品URL`（月別 CSV） | 月別 CSV は `re.search(r"/dp/([A-Z0-9]{10})/", url)` で抽出 |
| タイトル | `Product Name`（英語 CSV）/ `商品名`（月別 CSV） | そのまま保持（マッチング時に正規化） |
| 著者 | `付帯情報`（月別 CSV のみ） | `re.sub(r"^\[Kindle 版\]\s*", "", s)` → `re.sub(r"\s+販売:.*$", "", s)` → `,` / `、` で分割 → 役割接尾辞（`（著）` / `/著` 等）を除去 |

### サブスク・音楽除外ルール（`Digital Content Orders.csv`）

以下に該当する行は lookup テーブルに含めない:

- `Subscription Order Type` が `Subscription_Renewal` / `Subscription_Signup`
- ASIN が既知サブスク ASIN（`B0733PCPRF`: Prime、`B075JQ5JR5`: KU、`B00NVK0UZQ`: WashPost）
- `Seller of Record` が Amazon 配信会社（`amazon services international llc` など 16 種）

参照実装: `D:\61.tool\kindle購入履歴\app\backend\src\kindle_viewer\importer\digital_orders_parser.py`

---

## 3. 対象ライブラリ

| source | 対象 | 備考 |
|--------|------|------|
| novel | ✅ | |
| comic | ✅ | |
| doujin | ❌ | スコープ外 |

---

## 4. マッチングロジック

既存エントリとCSVデータを紐付ける手順:

1. エントリにすでに `asin` が設定済み → ASIN で lookup テーブルを直接引く
2. ASIN がない場合 → タイトル正規化+部分一致:
   - CSV タイトルに **タイトル正規化** を適用してマッチ用文字列 `normalized` を生成
   - `normalized` がファイル名（パス末尾）に **包含** されていればマッチ
3. 複数マッチした場合は最初のヒットを採用

### タイトル正規化（正規化後を lookup キーに使用）

参照実装: `D:\61.tool\kindle購入履歴\app\backend\src\kindle_viewer\utils\title.py` の `normalize().base`

以下の順で適用:

1. NFKC 正規化（全角英数を半角に統一）
2. 先頭の `[Kindle 版]` / `【...】` 等のブラケットプレフィクスを除去
3. `【電子限定特典付き】` 等の全角かっこノイズを除去
4. `／電子限定特典付き` 等のスラッシュ区切り装飾を除去
5. 末尾の出版社/レーベル名 `(角川コミックス・エース)` を除去（30文字以内の丸括弧）
6. 末尾の巻番号を反復除去（`（２）`、`第2巻`、`Vol.2`、`: 12`、`2巻` など 7 パターン）
7. 末尾の `：` / `－` 等の区切り文字を除去
8. 連続空白を 1 つに圧縮

### マッチ例

| CSV 商品名 | 正規化後 | ファイル名 | 結果 |
|-----------|---------|----------|------|
| `針子の乙女　（２） (角川コミックス・エース)` | `針子の乙女` | `針子の乙女 2巻.pdf` | ✅ |
| `ひともんちゃくなら喜んで！（６） (裏サンデー女子部)` | `ひともんちゃくなら喜んで！` | `ひともんちゃくなら喜んで06.pdf` | ✅ (改善) |
| `不徳のギルド 13巻 (デジタル版ガンガンコミックス)` | `不徳のギルド` | `不徳のギルド_013.pdf` | ✅ |

---

## 5. 更新ルール

| フィールド | 条件 |
|-----------|------|
| `authors` | **空欄のときのみ補完**。既存値は上書きしない |
| `asin` | **空欄のときのみ補完**。既存値は上書きしない |

---

## 6. UI

### ボタン配置

| 画面 | 配置場所 |
|------|---------|
| NovelManagePage | 管理画面内のツールバー or ヘッダー |
| comic 管理画面 | ※実装時に確認（専用ページなし、追加場所を要調査） |

### 処理完了後

トースト通知: `「更新: X 件 / スキップ: Y 件 / 未マッチ: Z 件」`

- **更新**: authors または asin を新たに書き込んだエントリ数
- **スキップ**: マッチしたが両フィールドとも既に埋まっていたエントリ数
- **未マッチ**: lookup テーブルに対応データが見つからなかったエントリ数

### エラー時

CSV ファイルが存在しない場合: トーストでエラーメッセージ表示

---

## 7. 変更範囲（影響範囲）

### Backend

| ファイル | 変更内容 |
|---------|---------|
| `backend/services/amazon_csv_importer.py` | 新規: CSV 読み込み・集約・除外・タイトル正規化・lookup テーブル構築 |
| `backend/routers/amazon_import.py` | 新規: `POST /api/amazon/import?source=novel|comic` |
| `backend/services/meta_store.py` | 変更不要（`asin` / `authors` は MetaEntry に定義済み） |
| `backend/main.py` | 新規 router の include |
| `backend/pyproject.toml` | `chardet` を依存に追加（`uv add chardet`） |

### Frontend

| ファイル | 変更内容 |
|---------|---------|
| `frontend/src/pages/NovelManagePage.tsx` | インポートボタン追加 |
| comic 管理 UI (要調査) | インポートボタン追加 |

---

## 8. スコープ外（やらないこと）

- Amazon CSV に存在しない書籍の新規エントリ作成
- `purchase_date` / `amazon_purchase_date` フィールドの保存
- doujin ライブラリへの適用
- CSV パスを UI から変更する設定画面
- マッチング結果のプレビュー / 確認ダイアログ（自動実行）

---

## 9. エッジケース

| ケース | 対応 |
|--------|------|
| CSV ファイルが 0 件 | エラートースト表示 |
| `Digital Content Orders.csv` の重複行 | `(Order ID, ASIN, Digital Order Item ID)` 単位で集約して dedup |
| サブスク・音楽行が CSV に混在 | `_detect_category()` で除外（kindle 以外は lookup に含めない） |
| 2014〜2020 購入分 (月別 CSV なし) | ASIN のみ補完、authors は空のまま |
| 同タイトル別巻が正規化後に同一になる | 部分一致の最初のヒットを採用。マッチ率向上を優先しており誤マッチが生じる可能性はある |
| 著者が複数（`著者A, 著者B`） | `,` / `、` で分割 → 役割接尾辞（`（著）` / `/著` 等）を除去 → `list[str]` に格納 |
| 月別 CSV のエンコーディングが SJIS | `detect_encoding()` で自動判定し `cp932` で読み込む |

---

## 10. 完了条件

- [ ] POST `/api/amazon/import?source=novel` を叩いて novel ライブラリのエントリに著者 / ASIN が補完される
- [ ] POST `/api/amazon/import?source=comic` を叩いて comic ライブラリのエントリに著者 / ASIN が補完される
- [ ] 空欄のみ補完・既存値は上書きしないことを確認
- [ ] トーストに更新 / スキップ / 未マッチ件数が表示される
- [ ] CSV ディレクトリ不在時にエラートーストが出る
- [ ] 設計書 (本ファイル) が `docs/01_要件定義/` に存在する
