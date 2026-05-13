# NovelPage QA UI リデザイン 要件

## 背景・目的

全体ライブラリ画面（NovelDbPage）に質問・会話 QA が混在しており煩雑。
個別本画面（NovelDetailPage）でのみ本固定スコープで RAG 検索・質問できるよう再配置し、
全体画面はライブラリ閲覧 + 全文検索に専念させる。

あわせて「会話 QA → 質問＋履歴」の順序（ChatSection が先）を新配置で実現する。

## 変更一覧

### 1. NovelDbPage（全体画面）のスリム化

| 対象 | 変更 |
|------|------|
| `NovelDbHeader` | 丸ごと削除（ScopeSelector・全件再構築ボタン含む） |
| `QuestionSection` | 削除 |
| `ChatSection` | 削除 |
| `RebuildJobBanner` + `useNovelDbRebuildJob` | 削除（再構築トリガーがなくなるため不要） |
| `SearchSection` | **残す**。`scope={{ type: 'all' }}` 固定渡し。UI 変更なし |
| `LibrarySection` + `BookMetaEditModal` | **残す** |
| `useNovelDbScope`, `useNovelDbHistory` の import | 削除 |

最終的な NovelDbPage の構成:

```
<LibrarySection />
<BookMetaEditModal />
<SearchSection scope={{ type: 'all' }} />
```

### 2. NovelDetailPage（個別本）への RAG 機能追加

既存セクション（要約 / 登場人物 / 読書会履歴）の**下**に追加。

追加順:
```
<SearchSection scope={bookScope} />
<ChatSection scope={bookScope} />
<QuestionSection scope={bookScope} history={bookHistory} ... />
```

- `bookScope = { type: 'book', id: decodedName }` — 固定スコープ（ScopeSelector なし）
- `QuestionSection` の履歴はこの本への質問のみ（`useNovelDbHistory(decodedName)` で取得）
- `disabled` は既存の `useNovelDbRebuildJob` の `isLocked` を流用

### 3. バックエンド API 拡張

#### `GET /api/novel_db/qa/history`

クエリパラメータ `book: str | None` を追加。

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `offset` | int | 0 | 既存 |
| `limit` | int | 20 | 既存 |
| `book` | str \| None | None | 指定時: `scope_type='book' AND scope_id=?` でフィルタ |

`book` が None（未指定）の場合は従来通り全件返却（既存の呼び出し元に影響なし）。

#### `list_history()` の変更

```python
def list_history(conn, offset=0, limit=20, book: str | None = None) -> dict:
    where = "WHERE scope_type='book' AND scope_id=?" if book else ""
    params = [book, limit, offset] if book else [limit, offset]
    rows = conn.execute(
        f"SELECT ... FROM qa_history {where} "
        "ORDER BY asked_at DESC, id DESC LIMIT ? OFFSET ?",
        params,
    ).fetchall()
    ...
```

### 4. フロントエンド変更

| ファイル | 変更内容 |
|---------|---------|
| `features/novel_db/api.ts` | `fetchQaHistory(offset, limit, book?)` に `book` 追加 |
| `hooks/novel_db/useNovelDbHistory.ts` | `useNovelDbHistory(book?: string)` に引数追加 |
| `hooks/novel_db/index.ts` | export 維持（シグネチャ変更のみ） |
| `pages/NovelDbPage.tsx` | NovelDbHeader / QuestionSection / ChatSection / RebuildJobBanner 削除 |
| `pages/NovelDetailPage.tsx` | SearchSection / ChatSection / QuestionSection 追加 |

## スコープ外

- ChatSection のセッション一覧フィルタ（全書籍共通のまま。scope ラベルで判別）
- NovelDbPage での再構築トリガー（個別本 Detail ページから操作）
- SearchSection に「全件」ラベル表示追加（要望なし）
- ページネーション実装

## 完了条件

- [ ] NovelDbPage: LibrarySection + SearchSection のみ（ヘッダーなし）
- [ ] NovelDetailPage: 既存セクション下に SearchSection → ChatSection → QuestionSection（scope 固定）
- [ ] 個別本の QuestionSection 履歴はその本のみ表示
- [ ] バックエンドテスト: `GET /qa/history?book=xxx` フィルタのテスト追加
- [ ] フロントエンドテスト: 既存テスト更新
- [ ] API 仕様書 §7.5 に `book` パラメータ追記
- [ ] フロントエンド詳細設計の NovelDetailPage セクション更新
