# 小説 DB 作者・シリーズ UI 管理 — 要件定義

> 2026-05-13 /grill-me セッションで確定。4.3 で定義したデータモデルを前提とした UI 管理フェーズ。

---

## 1. 概要と目的

小説ライブラリに **作者・シリーズ単位のグループ表示** と **複数冊への一括設定操作** を追加し、同人誌と同等の操作体験を実現する。

**解決したい問題**:
- 4.3 でデータフィールド（`authors / series_id / volume`）は付与できるようになったが、一覧はフラットなままでグループ化されない。
- 複数冊に同じ作者・シリーズを設定するには 1 冊ずつ `BookMetaEditModal` を開く必要があり手間。

---

## 2. 前提

- `4.3_作者シリーズ整理_要件.md` が実装済みであること（MetaEntry の `authors / series_id / volume` フィールド、`BookMetaEditModal`、Amazon CSV インポート）。
- `volume` は整数のみ（小数不要）。上下巻などは別巻番号として扱う。

---

## 3. 機能詳細

### 3.1 グループ表示（LibrarySection 拡張）

**表示モード切替トグル**（`NovelDbPage` ヘッダーに追加）:

| モード | 表示 |
|---|---|
| フラット（現状） | 書籍をフラット一覧 |
| 作者別グループ | 作者名でグループ折りたたみ |
| シリーズ別グループ | シリーズ名でグループ折りたたみ + volume 昇順ソート |

**未設定書籍の扱い**:
- 作者未設定 / シリーズ未設定の書籍はグループ外にフラット列挙（「未設定」グループには入れない）。

**シリーズ内ソート**:
- `volume` 昇順。`volume` が `null` の書籍はシリーズ末尾。

### 3.2 一括作者設定ダイアログ（小説専用）

- `LibrarySection` で複数冊を選択 → 「作者を設定」ボタン → ダイアログ表示。
- 機能:
  - 既存の作者一覧から検索・選択（`SearchableSelect`）。
  - または自由入力（複数作者はカンマ区切り or タグ入力）。
  - 「選択した N 冊に適用」で `PATCH /api/meta/novel/{book_key}` を順次呼び出し。
- doujin 用 `BulkAuthorDialog` は流用しない（小説専用コンポーネントを新規作成）。

### 3.3 一括シリーズ登録ダイアログ（小説専用）

- 複数冊選択 → 「シリーズに登録」ボタン → ダイアログ表示。
- 機能:
  - モード選択: 既存シリーズに追加 / 新規シリーズ作成 / シリーズから外す。
  - 既存シリーズ一覧から検索・選択（`GET /api/novel/series` 経由）。
  - 巻番号: 選択順に自動採番（1, 2, 3, …）。登録後に手動修正可。
  - 「AI 提案」ボタン: 選択冊の書名から Qwen にシリーズ名を提案させる（後述 §3.4）。
- doujin 用 `BulkSeriesAssignDialog` は流用しない（小説専用コンポーネントを新規作成）。

### 3.4 AI シリーズ提案（任意オプション、低優先）

- 選択した書籍の書名を LLM に渡し、シリーズ名・巻番号を推定して返す。
- 実装方法: 既存 `POST /api/novel/ask`（Qwen QA 経路）を流用 or 専用エンドポイント追加。
- 提案結果はあくまで候補。ユーザーが確認・修正してから保存。

---

## 4. バックエンド API

| エンドポイント | メソッド | 説明 |
|---|---|---|
| `/api/novel/series` | `GET` | 全シリーズ一覧（`SeriesSummary` リスト）を返す |
| `/api/novel/authors` | `GET` | 全作者一覧（`string[]` または `AuthorSummary[]`）を返す |
| `/api/meta/novel/{book_key}` | `PATCH` | 既存エンドポイント流用（4.3 実装済み） |

`GET /api/novel/series` は `SeriesSummary { id, name, book_count }` を返す（型は既に存在するため追加のみ）。

---

## 5. データモデル影響

- `MetaEntry` は変更なし（4.3 で拡張済み）。
- フロントエンド側で `BookSummary` を作者 / シリーズ でグループ集計するロジックをフック化する。

---

## 6. スコープ外

- doujin / comic への適用。
- doujin 用ダイアログの小説版共通化（`BulkAuthorDialog` / `BulkSeriesAssignDialog` のリファクタ）。
- `BookMetaEditModal` のさらなる改良（4.3 で完了）。
- 作者・シリーズのリネーム / マージ機能。
- 複数作者間の名寄せ・表記ゆれ統合。

---

## 7. 完了条件

- [ ] グループ表示トグルが動作し、作者別・シリーズ別グループ折りたたみが表示される。
- [ ] 未設定書籍がグループ外にフラット列挙される。
- [ ] 一括作者設定ダイアログで複数冊に作者を適用できる。
- [ ] 一括シリーズ登録ダイアログで選択順自動採番のうえシリーズ登録できる。
- [ ] `uv run pytest -q` が全通過。
- [ ] `npm run test` が全通過（フィルタ / グループロジックの vitest テスト追加）。
- [ ] `npx tsc --noEmit` がエラーなし。

---

## 8. 影響ファイル（想定）

**フロントエンド**:
- `frontend/src/pages/NovelDbPage.tsx` — グループ表示モード切替トグル追加
- `frontend/src/components/novel_db/LibrarySection.tsx` — 作者/シリーズグループ折りたたみ表示
- `frontend/src/components/novel_db/NovelBulkAuthorDialog.tsx`（新規）
- `frontend/src/components/novel_db/NovelBulkSeriesAssignDialog.tsx`（新規）
- `frontend/src/hooks/useNovelLibraryGroup.ts`（新規）— グループ集計ロジック
- `frontend/src/features/novel_db/api.ts` — `/api/novel/series` / `/api/novel/authors` 追加

**バックエンド**:
- `backend/routers/novel_db.py`（または `backend/routers/novel_meta.py`）— 作者・シリーズ一覧 GET 追加

**設計書**:
- `docs/03_詳細設計/詳細設計書_フロントエンド編.md` — LibrarySection グループ表示設計
- `docs/03_詳細設計/API仕様書.md` — 作者・シリーズ一覧エンドポイント追記
- `docs/05_記録/変更履歴.md` — 実装完了時に追記
