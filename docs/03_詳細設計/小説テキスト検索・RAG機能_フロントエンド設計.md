# 小説テキスト検索・RAG 機能 フロントエンド設計書

novel タブの「テキスト DB ビューア」を実現するフロントエンド側の詳細設計書。要件は [小説テキスト検索・RAG機能.md](../01_要件定義/小説テキスト検索・RAG機能.md)、API は [小説テキスト検索・RAG機能_バックエンド設計.md](小説テキスト検索・RAG機能_バックエンド設計.md) を参照。

最終更新: 2026-05-09（初版ドラフト）

---

## 1. 概要

### 1.1. 目的

novel タブを **OCR テキスト DB を主軸とした検索・質問応答ビューア** に作り変える。具体的には：

- 1 タブ内で **ライブラリ / 検索 / 質問** の 3 セクションを縦並び配置
- ヘッダーに **スコープドロップダウン**（全件 / シリーズ / 単冊）
- 検索結果はテキスト + サムネイル、クリックでページ画像モーダル
- 質問は 1 問 1 答 + 履歴。LLM（Qwen3.6:35b-a3b）の応答は SSE でストリーミング表示

### 1.2. 設計原則

- **既存規約踏襲**: components/reader (presentation) + components/viewer (state container) 分離 / apiClient 必須 / Dialog 共通シェル / z-index Tailwind 階層 / `any` 禁止（[frontend-conventions skill](../../.claude/skills/frontend-conventions/SKILL.md)）
- **別ルート並行運用**: 新画面は `/novel/db` で稼働（初期設計では `/novel-db`、移行後に `/novel/db` に変更）。既存 `/viewer?source=novel` は撤去済み
- **専用ディレクトリ**: `components/novel_db/` `hooks/novel_db/` `features/novel_db/` のように本機能専用の名前空間を切る（hitomi 機能と同等のスタイル）

### 1.3. 関連ドキュメント

- 要件定義: [docs/01_要件定義/小説テキスト検索・RAG機能.md](../01_要件定義/小説テキスト検索・RAG機能.md)
- バックエンド設計: [小説テキスト検索・RAG機能_バックエンド設計.md](小説テキスト検索・RAG機能_バックエンド設計.md)
- 既存フロント全体: [詳細設計書_フロントエンド編.md](詳細設計書_フロントエンド編.md)
- API 仕様: [API仕様書.md](API仕様書.md) §X（後続追加予定）

---

## 2. アーキテクチャ

### 2.1. 画面遷移

```
[Layout] (グローバルヘッダー: ナビゲーション)
   │
   ├─ /viewer              → ViewerPage（既存、main / kindle / generated / novel）
   │   └─ source=novel     → 旧 PDF ビューア（移行期間中のみ）
   │
   ├─ /novel/db             → NovelDbPage
   │   ├─ ライブラリセクション
   │   └─ 検索セクション（全冊固定スコープ）
   │
   ├─ /novel/detail/:bookName → NovelDetailPage
   │   ├─ 書籍メタ・要約・登場人物・読書会履歴（既存）
   │   ├─ 検索セクション（この本固定スコープ）
   │   ├─ 会話 QA セクション（この本固定スコープ）
   │   └─ 質問セクション + 履歴（この本固定スコープ）
   │
   ├─ /generator           → GeneratorPage（既存）
   ├─ /ocr                 → OCRPage（既存）
   └─ /hitomi              → HitomiPage（既存）
```

移行完了後に `/viewer?source=novel` から `/novel/db` への 301 相当のリダイレクトを実装し、既存 novel タブを撤去。

### 2.2. データフロー

```
[NovelDbPage]（全冊固定スコープ、スコープ選択 UI なし）
   ├─→ [LibrarySection] ── useNovelDbBooks → GET /api/novel_db/books
   │                       useNovelDbRebuildJob → POST /api/novel_db/rebuild + GET /rebuild/status (poll)
   │
   └─→ [SearchSection scope={type:'all'}] ── useNovelDbSearch → POST /api/novel_db/search

[NovelDetailPage]（scope = {type:'book', id:bookName} 固定）
   ├─→ [SearchSection] ── useNovelDbSearch → POST /api/novel_db/search
   │
   ├─→ [ChatSection] ── streamChatSession → POST /api/novel_db/chat/session (SSE)
   │                    useChatSessions → GET /api/novel_db/chat/sessions
   │
   └─→ [QuestionSection] ── useNovelDbQuestion → POST /api/novel_db/qa (SSE)
                            useNovelDbHistory(bookName) → GET /qa/history?book=xxx
                            └→ 引用ページクリック → navigate to reader
```

### 2.3. 設計判断（Why）

- **専用ディレクトリで隔離する理由**: `components/reader` 系は既存 PDF ビューア向けで肥大化中。新機能を混ぜると既存テストや refactor 計画に影響を出すため、`components/novel_db/` で独立させる
- **別ルート (/novel/db) にする理由**: 動作確認中は既存 novel タブと並行運用したい（[要件定義 §7 Phase 1](../01_要件定義/小説テキスト検索・RAG機能.md)）。同一ルートで分岐するとロールバック不可（初期設計では `/novel-db`、移行後に `/novel/db` に統一）
- **SSE を fetch + ReadableStream で実装する理由**: 標準 EventSource は `POST` リクエスト不可、リクエストボディに質問文を渡したいので fetch streaming を採用

---

## 3. ディレクトリ構成

```
frontend/src/
├── pages/
│   └── NovelDbPage.tsx                  # ルート: /novel/db
├── components/
│   └── novel_db/                        # 新規（本機能専用、presentation 中心）
│       ├── index.ts
│       ├── NovelDbHeader.tsx            # スコープドロップダウン + 設定ボタン
│       ├── ScopeSelector.tsx            # 全件 / シリーズ / 単冊 切替
│       ├── LibrarySection.tsx           # 書籍一覧（グループカードグリッド + ドリルダウン）
│       ├── BookCard.tsx                 # 1 冊分カード（サムネイル + メタ + DB 状態 + 再構築ボタン）
│       ├── BookMetaEditModal.tsx        # novel 書籍メタ手動編集モーダル（4.3 /「編集」ボタンから開く）
│       ├── BookMetaList.tsx             # メタ情報表示（card: コンパクト / detail: dl 形式）
│       ├── CharactersPanel.tsx          # BookCard 内折りたたみ登場人物一覧（B-15、expanded 時のみ API 呼び出し）
│       ├── CharacterDetailDialog.tsx    # キャラクター詳細ダイアログ（B-15 / サマリ + 主要シーン top5）
│       ├── ChatSection.tsx              # マルチターン会話 QA セクション（B-16 / ChatGPT 風左右 2 ペイン）
│       ├── DiscussionHistoryItem.tsx    # 読書会ディスカッション履歴アイテム（折りたたみカード / NovelDiscussionPage / NovelDetailPage 共用）
│       ├── NovelBulkAuthorDialog.tsx    # 複数書籍への作者名一括設定ダイアログ（`<Dialog>` ベース）
│       ├── NovelBulkSeriesAssignDialog.tsx # 複数書籍を一度にシリーズへ登録するダイアログ
│       ├── SeriesGroupCard.tsx          # シリーズ/作者グループカード（代表表紙 + 名前 + 冊数バッジ）。選択モード時グループ全選択対応
│       ├── SeriesDrilldownView.tsx      # シリーズ内書籍一覧（@dnd-kit/sortable で並び替え可、パンくず付き）
│       ├── RebuildJobBanner.tsx         # 上部に出る「再構築中」表示
│       ├── SearchSection.tsx            # 検索ボックス + 結果リスト + 無限スクロール
│       ├── SearchHitItem.tsx            # 1 件分検索結果（snippet + サムネイル + ページ番号）
│       ├── QuestionSection.tsx          # 質問入力 + 履歴（上部入力帯 + 下部左右 2 ペイン）
│       ├── QuestionInput.tsx            # textarea + 送信ボタン + 文字数カウンタ + 連投警告
│       ├── QuestionStreaming.tsx        # 送信中のストリーミング表示（停止ボタン含む）
│       ├── QuestionHistoryList.tsx      # 履歴リスト（左パネル、時系列降順）
│       ├── QuestionHistoryItem.tsx      # 1 履歴行（左パネル行、ホバー削除）
│       ├── QuestionHistoryDetail.tsx    # 選択履歴の詳細（右パネル、オンデマンド fetch）
│       └── PageImageModal.tsx           # ヒットページ画像モーダル（前後送り対応）
├── features/
│   └── novel_db/                        # 新規（API / 型）
│       ├── api.ts                       # apiClient ラッパ（GET books / POST search / POST qa SSE / etc）
│       ├── types.ts                     # 共通型（BookSummary, SearchHit, QaHistoryEntry, RebuildJob 等）
│       └── sse.ts                       # SSE クライアント（fetch + ReadableStream）
├── hooks/
│   └── novel_db/                        # novel_db 専用フック
│       ├── index.ts
│       ├── useNovelDbScope.ts           # URL 同期スコープ (?scope=all|series&id=... | book&id=...)
│       ├── useNovelDbBooks.ts           # 書籍一覧取得 + ポーリング更新
│       ├── useNovelDbSearch.ts          # 検索（debounce 300ms + 無限スクロール）
│       ├── useNovelDbQuestion.ts        # 質問送信 + SSE 受信 + 停止
│       ├── useNovelDbHistory.ts         # 履歴一覧 + 削除（book フィルタ対応）
│       ├── useNovelDbRebuildJob.ts      # ジョブ起動 + ステータスポーリング (5s)
│       ├── useNovelDbPageImageModal.ts  # 画像モーダルの開閉 + 前後送り
│       ├── useBookDetail.ts             # 書籍詳細取得（`GET /api/novel_db/books/{book_name}/detail`）。NovelDetailPage で使用
│       ├── useBookCharacters.ts         # 書籍のキャラクター一覧 on-demand 取得（B-15 / enabled=false 中は未取得）
│       ├── useCharacterDetail.ts        # キャラクター詳細（サマリ + 主要シーン top 5）取得（B-15）
│       └── useChatSessions.ts           # 会話セッション一覧・詳細・SSE ストリーム管理（B-16）
└── constants.ts                         # NOVEL_DB_CONFIG セクション追加
                                          # - SEARCH_DEBOUNCE_MS = 300
                                          # - SEARCH_PAGE_SIZE = 20
                                          # - REBUILD_POLL_INTERVAL_MS = 5000
                                          # - QUESTION_MAX_LENGTH = 500
```

---

## 4. ルーティング・URL 同期

### 4.1. ルート

`App.tsx` または `Layout.tsx` のルート定義に追加（既存実装が React Router 等を使っているか要確認 → 詳細は実装時）。

```tsx
<Route path="/novel/db" element={<NovelDbPage />} />
```

### 4.2. URL パラメータ

| パラメータ | 用途 | 例 |
|---|---|---|
| `scope` | スコープタイプ | `all` / `series` / `book` |
| `series_id` | scope=series の対象 | `oko-kishi-1` 等の文字列 |
| `book` | scope=book の対象 | `おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)` |
| `q` | 検索クエリ（オプション、検索したまま再訪用） | `デューク` |

URL 例:
- `/novel/db?scope=all` (デフォルト)
- `/novel/db?scope=series&series_id=oko-kishi`
- `/novel/db?scope=book&book=...&q=アストリッド`

`useNovelDbScope` で URL とローカル state の双方向同期。`history.replaceState` で履歴汚染を抑える（既存 `useUrlState` 流用パターン）。

---

## 5. コンポーネント設計

### 5.1. `NovelDbPage`（ルート画面）— 2026-05-14 改修

ライブラリ一覧と全冊検索に専念するシンプルな構成。QuestionSection / ChatSection / ScopeSelector は **NovelDetailPage に移動**して削除済み。

```tsx
function NovelDbPage() {
    return (
        <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
            <LibrarySection ... />
            <BookMetaEditModal ... />
            <SearchSection scope={{ type: 'all' }} ... />
        </div>
    );
}
```

- `scope` は `{type:'all'}` 固定で `SearchSection` に直接渡す（`useNovelDbScope` / `NovelDbHeader` は不使用）
- `useNovelDbRebuildJob` / `RebuildJobBanner` も削除（再構築は各 NovelDetailPage から操作）

### 5.2. `NovelDbHeader` + `ScopeSelector`（削除済み）

NovelDbPage から削除。`NovelDbHeader.tsx` / `ScopeSelector.tsx` ファイルは components/novel_db/ に残るが NovelDbPage では使用しない。

### 5.3. `LibrarySection` + `BookCard`

- **トップ階層（シリーズ/作者グループカードグリッド）**
    - グループモード切替トグル: `flat` / `series` / `author`
    - `SeriesGroupCard`: 代表カード（series の場合は volume 最小 or series_index 最小の表紙）+ シリーズ名 + 冊数バッジ
    - 未グループ書籍（シリーズ/作者未設定）はグリッド下部にフラット表示
    - 選択モード（一括シリーズ登録 / 作者設定）はフラット・グループ・ドリルダウン全モードで使用可

- **選択モードの挙動**
    - 「選択」ボタンは全モードで常時表示
    - フラットモード: 各書籍カードにチェックボックスオーバーレイ
    - グループモード（series/author）: `SeriesGroupCard` はそのまま表示し、クリックでグループ内全書籍を一括選択/解除。カード左上に選択状態チェックボックスを表示（全選択=✓ 青、部分選択=−、未選択=空）。グループカードの展開は行わない
    - ドリルダウンモード: `SeriesDrilldownView`（DnD）の代わりに個別書籍カードグリッドを表示し、1 冊ずつ選択可。戻るボタンで選択状態をリセット

- **ドリルダウン（シリーズ内ビュー）**
    - シリーズカードクリック → `SeriesDrilldownView` を表示
    - パンくず: `ライブラリ > {series_title}`（ライブラリ部分クリックでトップへ戻る）
    - 書籍カードは `@dnd-kit/sortable` によりドラッグ可能（選択モードでない場合）
    - DnD ドロップ時に即座に `POST /api/series/reorder { source: "novel", series_id, names: ["{book_name}.pdf", ...] }` を呼び出し、`series_index` を `1.0, 2.0, ...` に更新
    - ドロップ後はローカル state の順序を保ったまま表示（次回読み込み時は series_index 順）

- **`useNovelLibraryGroup` フック**
    - `series_id` / `representative`（代表 BookSummary）/ `books`（series_index 昇順ソート済み、null は末尾）を各グループに付与
    - `volume` は表示用整数、並び替え後の順序は `series_index`（float）を使用

- BookCard グリッド（既存 PdfCard を流用せず、シンプル化した独自カード）
    - サムネイル（`/kindle_novel/images/{書籍名}/001.png` を縮小）
    - 書籍名 / 作者 / ページ数 / DB 状態バッジ
- 「全件再構築」「このシリーズ再構築」ボタンはセクションヘッダーに配置

### 5.4. `RebuildJobBanner`

- 画面上部の固定バナー。`useNovelDbRebuildJob` の `is_running` が true のとき表示
- 内容: 「再構築中: {target_name} ({progress_done}/{progress_total} 冊)」
- 検索 / 質問 API は 503 を返すので、フロント側で送信ボタンを disable + ツールチップで案内

### 5.5. `SearchSection` + `SearchHitItem`

- 検索ボックス（debounce 300ms、Enter で即時実行）
- 結果リストは `IntersectionObserver` で末端を監視し、20 件ごとに追加読み込み
- `SearchHitItem`:
    - 左: サムネイル（クリックで PageImageModal 起動）
    - 右: 書名 / page 番号 / `<mark>` ハイライト付きスニペット（`dangerouslySetInnerHTML` で FTS5 の snippet を反映、サニタイズは backend 側で `<mark>` 以外をエスケープ済み）
- 「該当なし」時は単にメッセージ表示（[要件定義 TBD-10](../01_要件定義/小説テキスト検索・RAG機能.md)）

### 5.6. `QuestionSection` の構成（2026-05-14 改修）

入力帯を上部に固定し、その下を ChatSection と同様の左右 2 ペインに変更。履歴が縦長になる問題を解消する。

```
[QuestionInput]                      ← 上部帯（現状維持）
[QuestionStreaming]                   ← 入力帯直下（現状維持）
┌────────────────┬──────────────────────────────────┐
│ 左パネル(260px)│ 右パネル(flex-1)                  │
│ QuestionHistory│ QuestionHistoryDetail             │
│ List           │  - 質問全文                        │
│ - 質問行1      │  - 日時・応答時間                  │
│ - 質問行2      │  - 回答テキスト                    │
│ ...            │  - 参照ページボタン群              │
└────────────────┴──────────────────────────────────┘
```

- 送信完了後は `pendingAutoSelect` フラグ経由で最新エントリを自動選択して右パネルに表示
- `selectedId: number | null` を `QuestionSection` 内で管理（`QuestionHistoryDetail` へ prop で渡す）

#### 5.6.1. `QuestionInput`

- textarea（4 行）
- 文字数カウンタ表示。500 文字超で disabled
- 送信ボタン
- **連投警告**: 直前の質問テキストと完全一致した場合、`<ConfirmDialog>` で「同じ質問を再送しますか?」と確認
    - 「直前」の判定は **セッション内（メモリ上）のみ**。`useNovelDbQuestion` の `lastQuestion` で保持し、ページリロードで自動リセット

#### 5.6.2. `QuestionStreaming`

送信中の表示。応答が逐次描画される。停止ボタンあり。

停止: `useNovelDbQuestion.stop()` を呼び、`AbortController.abort()` で fetch を中断 → バックエンドが `done_reason='canceled'` で履歴保存 → `useNovelDbHistory` が再フェッチ。

#### 5.6.3. `QuestionHistoryList`（左パネル）

- 時系列降順の質問一覧
- 各行: 質問テキスト（1 行 truncate）+ スコープ（2 行目、小さく）
- 選択行をハイライト（`bg-primary-50`）
- ホバー時に右端へ Trash アイコン表示 → `<ConfirmDialog>` → DELETE API → 再フェッチ
- `max-h-[600px]` スクロール可（ChatSection と統一）

#### 5.6.4. `QuestionHistoryDetail`（右パネル）

- `selectedId` が `null` の場合はプレースホルダー表示
- 選択時: `fetchQaHistoryDetail(selectedId)` をオンデマンドで呼び出し
- 表示内容: 質問全文 / 日時（JST）/ 応答時間 / 回答テキスト（whitespace-pre-wrap）/ 参照ページボタン群
- `max-h-[600px]` スクロール可

**タイムスタンプの取り扱い** (2026-05-11 追記):
- バックエンドは SQLite `datetime('now')` で保存しており、出力形式は `"2026-05-11 13:30:45"`（タイムゾーン情報なし、実体は **UTC**）
- JS の `new Date(s)` がこの形式をローカル時刻として誤解釈する事故を防ぐため、frontend では [`utils/date.ts`](../../frontend/src/utils/date.ts) に `parseSqliteUtc` / `formatSqliteUtcAsJst` / `formatElapsedSeconds` を集約
- `QuestionHistoryItem` は `formatSqliteUtcAsJst(asked_at)` で JST 表示し、`formatElapsedSeconds(asked_at, finished_at)` で応答時間（例: 「2 分 50 秒」「1 時間 1 分」）を併記

### 5.7. `PageImageModal`

```tsx
<Dialog open={isOpen} onClose={close} variant="image">
    <div className="flex items-center justify-between p-2">
        <div>{book} - page {pageNo}</div>
        <button onClick={close} aria-label="閉じる">×</button>
    </div>
    <div className="flex items-center justify-center">
        <button onClick={prevPage} disabled={pageNo <= 1}>‹</button>
        <img src={`/kindle_novel/images/${encodeURIComponent(book)}/${String(pageNo).padStart(3, '0')}.png`} />
        <button onClick={nextPage} disabled={pageNo >= maxPage}>›</button>
    </div>
</Dialog>
```

操作:
- 左右キー: 前後ページ送り
- ESC キー / × ボタン / 背景クリック: 閉じる

`Dialog` 共通シェルを利用するが、画像表示用に `variant="image"` モードを追加（中央配置 + max-w-screen-lg + transparent backdrop）。`Dialog.tsx` 自体に微改修が必要なら別タスクで切り出す。

### 5.8. `NovelDetailPage` — RAG 機能セクション（2026-05-14 追加）

書籍詳細画面（`/novel/detail/:bookName`）の既存セクション（要約 / 登場人物 / 読書会履歴）の下に、この本固定スコープの RAG 機能セクションを追加する。

**配置順（下から）:**

```
既存: 要約セクション
既存: 登場人物セクション
既存: 読書会履歴セクション
--- 追加 ---
<SearchSection scope={bookScope} onOpenImage={handleOpenScene} />
<ChatSection scope={bookScope} disabled={isLocked} />
<QuestionSection scope={bookScope} history={bookHistory} ... disabled={isLocked} />
```

**スコープ:**

```tsx
const bookScope: Scope = { type: 'book', id: decodedName };
```

UI には ScopeSelector を表示しない。書籍名は URL パラメータ（`useParams`）から取得。

**履歴フィルタ:**

```tsx
const { items: history, ... } = useNovelDbHistory(decodedName);
```

`useNovelDbHistory(decodedName)` は `GET /api/novel_db/qa/history?book={decodedName}` を呼び出し、この書籍への質問のみ返す。

**disabled 制御:**

既存の `useNovelDbRebuildJob` の `isLocked`（`rebuildStatus?.is_running ?? false`）を SearchSection / ChatSection / QuestionSection に流す。

**セクション間の順序の意図:**

「会話 QA（ChatSection）が先、質問＋履歴（QuestionSection）が後」は、一問一答の記録よりマルチターン対話を優先する UX 上の判断（[要件定義](../01_要件定義/NovelPage_QA_UI_リデザイン_要件.md)）。

---

## 6. hooks 設計

### 6.1. `useNovelDbScope`

URL クエリパラメータ ↔ React state の双方向同期。

```tsx
type Scope =
    | { type: "all" }
    | { type: "series"; id: string }
    | { type: "book"; name: string };

function useNovelDbScope(): { scope: Scope; setScope: (s: Scope) => void };
```

実装は既存の `useUrlState` を参考に。

### 6.2. `useNovelDbBooks`

```tsx
function useNovelDbBooks(): {
    books: BookSummary[];
    seriesList: SeriesSummary[];
    isLoading: boolean;
    refetch: () => Promise<void>;
};
```

- 初回マウント時に `GET /api/novel_db/books` + `GET /api/novel_db/series`
- `useNovelDbRebuildJob` のジョブ完了通知を受けて自動 refetch（共通の event emitter or React Query 採用検討）

### 6.3. `useNovelDbSearch`

```tsx
function useNovelDbSearch(scope: Scope): {
    query: string;
    setQuery: (q: string) => void;
    hits: SearchHit[];
    hasMore: boolean;
    loadMore: () => Promise<void>;
    isSearching: boolean;
};
```

- `query` 変更を 300ms debounce → POST /api/novel_db/search
- `hasMore` は API レスポンスの `total > hits.length`
- `IntersectionObserver` 用の sentinel ref を返すと使いやすい（`loadMoreRef`）

### 6.4. `useNovelDbQuestion`

```tsx
function useNovelDbQuestion(scope: Scope): {
    submit: (question: string) => Promise<void>;
    stop: () => void;
    streamingText: string;
    isStreaming: boolean;
    error: string | null;
    isReplay: (q: string) => boolean;  // セッション内の直前質問と一致なら true
};
```

- `submit` 内で `fetch('/api/novel_db/qa', { signal: abortController.signal })` を呼び、`response.body.getReader()` で SSE をパース
- 各 token を受信するたびに `setStreamingText(prev => prev + token)`
- `done` イベント受信時に履歴 refetch
- `stop` で `abortController.abort()` → サーバ側が中断検知して履歴に保存
- **直前質問の記憶**: フックの内部 state（useState）に最後に送信した質問テキストを保持。**セッション内（タブを開いている間）のみ有効**で、ページリロードや別タブで開くとリセット。永続化（localStorage / DB 履歴照合）はしない

### 6.5. `useNovelDbHistory`

```tsx
function useNovelDbHistory(book?: string): {
    items: QaHistoryEntry[];
    total: number;
    isLoading: boolean;
    error: string | null;
    deleteItem: (id: number) => Promise<void>;
    refetch: () => Promise<void>;
};
```

- `book` が指定された場合: `GET /api/novel_db/qa/history?book=xxx` でその書籍の質問のみ取得
- `book` が未指定の場合: 全件取得（NovelDbPage では現在 QuestionSection ごと削除されたため使用なし）
- 質問送信完了時 / 削除時に refetch

### 6.6. `useNovelDbRebuildJob`

```tsx
function useNovelDbRebuildJob(): {
    enqueue: (job: RebuildRequest) => Promise<{ job_id: number; queued_position: number }>;
    cancel: (jobId: number) => Promise<void>;
    status: RebuildStatus;  // { is_running, current_job, queued_jobs }
};
```

- `status` は 5 秒間隔でポーリング（既存 `usePolling` フック流用）
- `enqueue` 後にステータス即時 refetch
- ジョブ完了を検知したら `useNovelDbBooks.refetch` をトリガ（イベントバスや context で連携）

### 6.7. `useNovelDbPageImageModal`

画像モーダルの開閉と前後送りを集約。

```tsx
function useNovelDbPageImageModal(): {
    isOpen: boolean;
    book: string | null;
    pageNo: number | null;
    open: (book: string, pageNo: number) => void;
    close: () => void;
    prevPage: () => void;
    nextPage: () => void;
};
```

書籍ごとの最大ページ数は `useNovelDbBooks.books` から参照。

---

## 7. API 連携（`features/novel_db/api.ts`）

### 7.1. apiClient ラッパ

```ts
import { apiClient } from "@/config/api_client";
import type { BookSummary, SearchHit, ... } from "./types";

export async function fetchBooks(): Promise<BookSummary[]> {
    const { data } = await apiClient.get<BookSummary[]>("/novel_db/books");
    return data;
}

export async function postSearch(req: SearchRequest): Promise<SearchResponse> {
    const { data } = await apiClient.post<SearchResponse>("/novel_db/search", req);
    return data;
}

export async function postRebuild(req: RebuildRequest): Promise<RebuildJobResponse> {
    const { data } = await apiClient.post<RebuildJobResponse>("/novel_db/rebuild", req);
    return data;
}

// ... etc
```

### 7.2. SSE クライアント (`features/novel_db/sse.ts`)

`apiClient` (axios) は SSE 対応していないため、SSE は `fetch` を直接使う唯一の例外。`features/novel_db/sse.ts` に隔離して、他から fetch 直叩きが広がらないようにする。

```ts
export interface SseHandlers {
    onToken: (text: string) => void;
    onDone: (final: { eval_count: number; done_reason: string }) => void;
    onError: (err: Error) => void;
}

export async function streamQa(
    body: QaRequest,
    handlers: SseHandlers,
    signal: AbortSignal,
): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/novel_db/qa`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(body),
        signal,
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const json = JSON.parse(line.slice(6));
            if (json.token) handlers.onToken(json.token);
            if (json.done) handlers.onDone(json);
        }
    }
}
```

abort はキャッチして `done_reason='aborted'` として `onDone` を呼ぶか、上位で扱う。

---

## 8. 状態管理パターン

- **ローカル状態**: 各セクションは自前のフック（`useNovelDbBooks` 等）で fetch + 状態管理
- **画面間で共有が必要な状態**:
    - `scope`: URL パラメータ駆動 → `useNovelDbScope` で同期
    - `画像モーダル`: シングルトン的に開きたいので `useNovelDbPageImageModal` を Context で提供（単純な useState で十分なら Context 不要）
    - `再構築ジョブの完了通知`: 書籍一覧を refetch する必要があるため、Context + useEffect で監視 or React Query の invalidateQueries 相当の仕組み
- **既存のグローバル Context は使わない**（Toast Context のみ流用）
- **React Query 等は導入しない**（既存プロジェクトに無いため。手書きフックで十分な規模）

---

## 9. UI スタイル方針

- 既存のダークモード対応（`useDarkMode`）に追従
- `<Dialog>` `<Button>` `<ConfirmDialog>` `<Alert>` `<TagsInput>` 等の共通プリミティブを優先利用
- z-index は `z-overlay-bar`（再構築バナー）/ `z-dialog`（PageImageModal） / `z-toast`（既存）を使用
- グリッド・パディングは Tailwind 標準クラス。新規 CSS 変数は必要最小限
- 検索ハイライト用の `<mark>` のスタイルは Tailwind プリセット or `tailwind.config.js` に追加

---

## 10. テスト方針

`frontend/src/test/` に追加（既存 vitest パターン踏襲）。

| ファイル | 対象 |
|---|---|
| `NovelDbScope.test.tsx` | URL ↔ state 同期、scope 変更で URL が書き換わるか |
| `useNovelDbSearch.test.ts` | debounce 300ms、無限スクロール、scope フィルタ |
| `useNovelDbQuestion.test.ts` | SSE モック、stop 時の AbortController 動作、エラーハンドリング |
| `useNovelDbRebuildJob.test.ts` | enqueue → polling → 完了検知、cancel の 409 ハンドリング |
| `useNovelDbHistory.test.ts` | refetch、削除確認、エラー時のロールバック |
| `QuestionInput.test.tsx` | 文字数制限、連投警告、disabled 条件 |
| `PageImageModal.test.tsx` | キーボード操作、前後送り境界（page=1 / page=max）、aria-label |
| `BookCard.test.tsx` | DB 状態バッジ、再構築ボタン disable 条件 |
| `SearchHitItem.test.tsx` | snippet の HTML サニタイゼーション、画像クリックでモーダル起動 |

SSE は `setupServer` (msw) でモック。fetch + ReadableStream のテスト用に `Response` をスタブ。

---

## 11. 移行・撤去計画

### Phase 1: 並行運用

- `/novel-db` ルートを追加 + 新画面を実装・公開
- 既存 `/viewer?source=novel` はそのまま動作
- Layout のグローバルナビに「小説検索 (novel)」リンクを追加（既存 SourceSelector からも `?source=novel` で旧画面に行ける）
- 11 冊で UC-1〜UC-5 の動作確認

### Phase 2: 旧資産の削除

- [frontend/src/config/api.ts:110](../../frontend/src/config/api.ts#L110) の `source === 'novel'` 分岐を削除
- 既存 SourceSelector の `novel` タブ表示を「小説検索 (新)」へのリンクに置換 or タブ自体を撤去
- ViewerPage で `source=novel` のリクエストが来たら `/novel/db` にリダイレクト
- バックエンド側の `/kindle_novel/pdfs` マウント削除（バックエンド設計 §13 と連動）

### 残す資産

- `/kindle_novel/images/{書籍名}/*.png` の StaticFiles マウント（PageImageModal が利用）
- 既存 Dialog / Button / Toast 等の共通プリミティブ

---

## 11. 読書会ディスカッション画面（B-20 / `/novel/discussion`）実装済み（2026-05-13）

### 11.1 画面構成

書籍選択 → ペルソナ A/B 設定 → 往復数スライダー → 生成 → SSE リアルタイム表示 → 履歴閲覧 のワンページ構成。

```
NovelDiscussionPage (/novel/discussion)
  ├─ 書籍選択ドロップダウン（useNovelDbBooks の books から）
  ├─ PersonaPanel × 2（A/B）
  │    ├─ 名前テキスト入力
  │    ├─ プリセット 3 軸チップ（読書スタイル / 口調 / 視点）
  │    └─ カスタム切替（自由テキストに切り替え可）
  ├─ 往復数スライダー（2〜20、デフォルト 6）
  ├─ 生成ボタン / 中止ボタン
  ├─ エラーバナー
  ├─ 生成結果エリア（TurnCard の積み上げ、新ターン追加時に自動スクロール）
  └─ 履歴セクション（書籍変更時に自動ロード、HistoryItemCard で折りたたみ表示）
```

### 11.2 ファイル構成（実装済み）

```
frontend/src/
  pages/
    NovelDiscussionPage.tsx   — ページ + ローカルサブコンポーネント（一体型）
  features/novel_db/
    sse.ts                    — streamDiscussion() 追加（B-20 SSE クライアント）
    api.ts                    — fetchDiscussionHistory() / DiscussionHistoryItem 型追加
```

サブコンポーネント（`PersonaPanel`, `PresetRow`, `TurnCard`, `HistoryItemCard`）は
`NovelDiscussionPage.tsx` 内にローカル定義（別ファイル分割なし）。

### 11.3 プリセット定義（実装済み）

```ts
const READING_STYLES = ['批評家', 'ファン', '懐疑派'] as const;
const TONES         = ['敬語丁寧', 'フランク', '関西弁風'] as const;
const PERSPECTIVES  = ['文学評論', '感情重視', 'ロジック重視'] as const;
```

各軸から 1 つ選ぶと `style_description`（例: `批評家・敬語丁寧・文学評論`）を自動生成。カスタムモード切替で自由記述に上書き可。

### 11.4 SSE 接続パターン

`features/novel_db/sse.ts` の `streamDiscussion()` を直接呼び出す（hook 化なし）。

```ts
// POST /api/novel/discussion/generate → SSE
streamDiscussion(body, {
  onTurn: (ev) => setTurns(prev => [...prev, ev]),   // turn ごとに追記
  onDone: () => { setIsGenerating(false); void loadHistory(book); },
  onError: (e) => { setError(e.message); setIsGenerating(false); },
}, abortController.signal);
```

受信イベント: `{"type": "turn", "speaker": "A"|"B", "text": "..."}` が 1 ターンごとに到着。

### 11.5 ルーティング

`App.tsx` の `/novel/discussion` ルート追加済み。`Layout.tsx` の小説カテゴリに「読書会」（`MessageSquare` アイコン）リンク追加済み。

---

## 12. 既知の制限・将来検討

- **画像プリロード**: PageImageModal で前後ページを開いたときの読み込み待ち時間は許容。気になれば将来 `useImagePreloader` 流用
- **オフライン対応**: 想定しない（LAN 内利用前提）
- **モバイル対応**: PC 利用前提。スマホで開けはするが、モーダル UI 等の最適化は別途
- **キーボードショートカット**: 検索 (`/`)、質問 (`?`) などのトップレベルショートカットは [バックログ.md](../01_要件定義/バックログ.md) と相談しつつ後付け

---

## 13. 関連ドキュメント

- 要件: [docs/01_要件定義/小説テキスト検索・RAG機能.md](../01_要件定義/小説テキスト検索・RAG機能.md)
- バックエンド設計: [小説テキスト検索・RAG機能_バックエンド設計.md](小説テキスト検索・RAG機能_バックエンド設計.md)
- 既存フロント全体: [詳細設計書_フロントエンド編.md](詳細設計書_フロントエンド編.md)
- フロント規約: [.claude/skills/frontend-conventions/SKILL.md](../../.claude/skills/frontend-conventions/SKILL.md)
- API 仕様: [API仕様書.md](API仕様書.md)（後続で novel_db セクション追加）
- PoC 実装の参考: 旧 `tmp_poc/`（実装完了後に削除済み）
