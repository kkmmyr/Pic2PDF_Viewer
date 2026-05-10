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
- **別ルート並行運用**: 新画面は `/novel-db` で稼働、既存 `/viewer?source=novel` は動作確認期間中も残す（[要件定義 §7](../01_要件定義/小説テキスト検索・RAG機能.md)）
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
   ├─ /novel-db (new)      → NovelDbPage
   │   ├─ サブヘッダー (スコープドロップダウン + 設定ボタン)
   │   ├─ ライブラリセクション
   │   ├─ 検索セクション
   │   ├─ 質問セクション
   │   └─ 画像モーダル (オーバーレイ)
   │
   ├─ /generator           → GeneratorPage（既存）
   ├─ /ocr                 → OCRPage（既存）
   └─ /hitomi              → HitomiPage（既存）
```

移行完了後に `/viewer?source=novel` から `/novel-db` への 301 相当のリダイレクトを実装し、既存 novel タブを撤去。

### 2.2. データフロー

```
[NovelDbPage]
   ↓ useNovelDbScope (URL 同期)
   ↓
[ScopeContext.Provider] (scope = all | series | book)
   ↓
   ├─→ [LibrarySection] ── useNovelDbBooks → GET /api/novel_db/books
   │                       useNovelDbRebuildJob → POST /api/novel_db/rebuild + GET /rebuild/status (poll)
   │
   ├─→ [SearchSection] ── useNovelDbSearch → POST /api/novel_db/search (debounce 300ms, 無限スクロール)
   │                       └→ 結果クリック → openImageModal(book, page_no)
   │
   ├─→ [QuestionSection] ── useNovelDbQuestion → POST /api/novel_db/qa (SSE)
   │                        useNovelDbHistory → GET /qa/history + DELETE /qa/history/:id
   │                        ├→ 履歴クリック → 展開
   │                        └→ 引用ページクリック → openImageModal
   │
   └─→ [PageImageModal] ── 単独 state（ZustandStore or useReducer）
                            ├→ ESC / × / 背景クリックで閉じる
                            └→ 左右キー / ボタンで前後ページ
```

### 2.3. 設計判断（Why）

- **専用ディレクトリで隔離する理由**: `components/reader` 系は既存 PDF ビューア向けで肥大化中。新機能を混ぜると既存テストや refactor 計画に影響を出すため、`components/novel_db/` で独立させる
- **別ルート (/novel-db) にする理由**: 動作確認中は既存 novel タブと並行運用したい（[要件定義 §7 Phase 1](../01_要件定義/小説テキスト検索・RAG機能.md)）。同一ルートで分岐するとロールバック不可
- **SSE を fetch + ReadableStream で実装する理由**: 標準 EventSource は `POST` リクエスト不可、リクエストボディに質問文を渡したいので fetch streaming を採用

---

## 3. ディレクトリ構成

```
frontend/src/
├── pages/
│   └── NovelDbPage.tsx                  # 新規（ルート: /novel-db）
├── components/
│   └── novel_db/                        # 新規（本機能専用、presentation 中心）
│       ├── index.ts
│       ├── NovelDbHeader.tsx            # スコープドロップダウン + 設定ボタン
│       ├── ScopeSelector.tsx            # 全件 / シリーズ / 単冊 切替
│       ├── LibrarySection.tsx           # 書籍一覧 + 再構築ボタン
│       ├── BookCard.tsx                 # 1 冊分カード（サムネイル + メタ + DB 状態 + 再構築ボタン）
│       ├── RebuildJobBanner.tsx         # 上部に出る「再構築中」表示
│       ├── SearchSection.tsx            # 検索ボックス + 結果リスト + 無限スクロール
│       ├── SearchHitItem.tsx            # 1 件分検索結果（snippet + サムネイル + ページ番号）
│       ├── QuestionSection.tsx          # 質問入力 + 履歴
│       ├── QuestionInput.tsx            # textarea + 送信ボタン + 文字数カウンタ + 連投警告
│       ├── QuestionStreaming.tsx        # 送信中のストリーミング表示（停止ボタン含む）
│       ├── QuestionHistoryList.tsx      # 履歴リスト（時系列降順）
│       ├── QuestionHistoryItem.tsx      # 1 履歴行（折りたたみ展開、引用ページリンク）
│       └── PageImageModal.tsx           # ヒットページ画像モーダル（前後送り対応）
├── features/
│   └── novel_db/                        # 新規（API / 型）
│       ├── api.ts                       # apiClient ラッパ（GET books / POST search / POST qa SSE / etc）
│       ├── types.ts                     # 共通型（BookSummary, SearchHit, QaHistoryEntry, RebuildJob 等）
│       └── sse.ts                       # SSE クライアント（fetch + ReadableStream）
├── hooks/
│   └── novel_db/                        # 新規
│       ├── index.ts
│       ├── useNovelDbScope.ts           # URL 同期スコープ (?scope=all|series&id=... | book&id=...)
│       ├── useNovelDbBooks.ts           # 書籍一覧取得 + ポーリング更新
│       ├── useNovelDbSearch.ts          # 検索（debounce 300ms + 無限スクロール）
│       ├── useNovelDbQuestion.ts        # 質問送信 + SSE 受信 + 停止
│       ├── useNovelDbHistory.ts         # 履歴一覧 + 削除
│       ├── useNovelDbRebuildJob.ts      # ジョブ起動 + ステータスポーリング (5s)
│       └── useNovelDbPageImageModal.ts  # 画像モーダルの開閉 + 前後送り
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
<Route path="/novel-db" element={<NovelDbPage />} />
```

### 4.2. URL パラメータ

| パラメータ | 用途 | 例 |
|---|---|---|
| `scope` | スコープタイプ | `all` / `series` / `book` |
| `series_id` | scope=series の対象 | `oko-kishi-1` 等の文字列 |
| `book` | scope=book の対象 | `おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)` |
| `q` | 検索クエリ（オプション、検索したまま再訪用） | `デューク` |

URL 例:
- `/novel-db?scope=all` (デフォルト)
- `/novel-db?scope=series&series_id=oko-kishi`
- `/novel-db?scope=book&book=...&q=アストリッド`

`useNovelDbScope` で URL とローカル state の双方向同期。`history.replaceState` で履歴汚染を抑える（既存 `useUrlState` 流用パターン）。

---

## 5. コンポーネント設計

### 5.1. `NovelDbPage`（ルート画面）

```tsx
function NovelDbPage() {
    const scope = useNovelDbScope();  // URL 同期
    return (
        <div className="flex flex-col gap-6 p-4">
            <NovelDbHeader scope={scope} />
            <RebuildJobBanner />
            <LibrarySection scope={scope} />
            <SearchSection scope={scope} />
            <QuestionSection scope={scope} />
            <PageImageModal />  // 内部で useNovelDbPageImageModal を読む
        </div>
    );
}
```

- 各セクションは props で `scope` を受け取り、自身で API 呼び出し
- `PageImageModal` は portal でなく単純な fixed overlay（既存 Dialog 系の z-dialog クラスを使う）

### 5.2. `NovelDbHeader` + `ScopeSelector`

- 上段: 戻るボタン（任意） / タイトル「小説テキスト検索」 / 設定アイコン
- 下段: `ScopeSelector` ドロップダウン（全件 / シリーズ / 単冊 を切替）

```tsx
<select value={scope.type} onChange={...}>
    <option value="all">全件</option>
    <optgroup label="シリーズ">
        {seriesList.map(s => <option value={`series:${s.id}`}>{s.name}</option>)}
    </optgroup>
    <optgroup label="単冊">
        {books.map(b => <option value={`book:${b.name}`}>{b.name}</option>)}
    </optgroup>
</select>
```

シリーズ未所属の書籍は `<optgroup label="シリーズ">` には出さず、`<optgroup label="単冊">` のみに表示（[要件定義 TBD-7](../01_要件定義/小説テキスト検索・RAG機能.md)）。

### 5.3. `LibrarySection` + `BookCard`

- BookCard グリッド（既存 PdfCard を流用せず、シンプル化した独自カード）
    - サムネイル（`/kindle_novel/images/{書籍名}/001.png` を縮小）
    - 書籍名 / 作者 / ページ数 / DB 状態バッジ
    - 「再構築」ボタン → `useNovelDbRebuildJob.enqueueBook(name)` 呼び出し
- シリーズグループ表示: scope=all のとき、シリーズ単位でグルーピング（既存 `LibraryPanel` のシリーズ表示パターンを参考）
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

### 5.6. `QuestionSection` の構成

```tsx
<section>
    <QuestionInput
        scope={scope}
        onSubmit={...}
        disabled={isStreaming || isRebuildRunning}
        maxLength={500}
    />
    {isStreaming && <QuestionStreaming text={streamingText} onStop={...} />}
    <QuestionHistoryList items={history} onDelete={...} onClickPage={openImageModal} />
</section>
```

#### 5.6.1. `QuestionInput`

- textarea（5 行ぐらい高さ）
- 文字数カウンタ表示。500 文字超で disabled
- 送信ボタン
- **連投警告**: 直前の質問テキストと完全一致した場合、`<ConfirmDialog>` で「同じ質問を再送しますか?」と確認
    - 「直前」の判定は **セッション内（メモリ上）のみ**。`QuestionSection` の `useState` で保持し、ページリロードで自動リセット
    - 履歴 API（`qa_history` テーブル）とは独立。永続的な「過去すべての質問との重複」までは見ない

#### 5.6.2. `QuestionStreaming`

送信中の表示。応答が逐次描画される。停止ボタンあり：

```tsx
<div className="border rounded p-3 bg-card">
    <div className="text-sm text-muted">回答生成中...</div>
    <div className="whitespace-pre-wrap">{streamingText}</div>
    <div className="flex justify-end mt-2">
        <Button variant="ghost" onClick={onStop}>停止</Button>
    </div>
</div>
```

停止: `useNovelDbQuestion.stop()` を呼び、`AbortController.abort()` で fetch を中断 → バックエンドが `done_reason='canceled'` で履歴保存 → `useNovelDbHistory` が再フェッチ。

#### 5.6.3. `QuestionHistoryList` + `QuestionHistoryItem`

- 時系列降順
- `QuestionHistoryItem` は折りたたみ展開（`<details>` + `<summary>` ベース）
    - 折りたたみ時: 質問テキスト先頭 60 字 + タイムスタンプ + スコープ
    - 展開時: 回答全文 + 引用ページ番号（クリックで PageImageModal 起動）+ 削除ボタン
- 削除ボタン → `<ConfirmDialog>` で確認 → DELETE API → 一覧再フェッチ

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
function useNovelDbHistory(): {
    items: QaHistoryEntry[];
    isLoading: boolean;
    deleteItem: (id: number) => Promise<void>;
    refetch: () => Promise<void>;
};
```

質問送信完了時 / 削除時に refetch。

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
- ViewerPage で `source=novel` のリクエストが来たら `/novel-db` にリダイレクト
- バックエンド側の `/kindle_novel/pdfs` マウント削除（バックエンド設計 §13 と連動）

### 残す資産

- `/kindle_novel/images/{書籍名}/*.png` の StaticFiles マウント（PageImageModal が利用）
- 既存 Dialog / Button / Toast 等の共通プリミティブ

---

## 12. 既知の制限・将来検討

- **画像プリロード**: PageImageModal で前後ページを開いたときの読み込み待ち時間は許容。気になれば将来 `useImagePreloader` 流用
- **オフライン対応**: 想定しない（LAN 内利用前提）
- **モバイル対応**: PC 利用前提。スマホで開けはするが、モーダル UI 等の最適化は別途
- **キーボードショートカット**: 検索 (`/`)、質問 (`?`) などのトップレベルショートカットは [機能追加候補.md](../01_要件定義/機能追加候補.md) と相談しつつ後付け

---

## 13. 関連ドキュメント

- 要件: [docs/01_要件定義/小説テキスト検索・RAG機能.md](../01_要件定義/小説テキスト検索・RAG機能.md)
- バックエンド設計: [小説テキスト検索・RAG機能_バックエンド設計.md](小説テキスト検索・RAG機能_バックエンド設計.md)
- 既存フロント全体: [詳細設計書_フロントエンド編.md](詳細設計書_フロントエンド編.md)
- フロント規約: [.claude/skills/frontend-conventions/SKILL.md](../../.claude/skills/frontend-conventions/SKILL.md)
- API 仕様: [API仕様書.md](API仕様書.md)（後続で novel_db セクション追加）
- PoC 実装の参考: 旧 `tmp_poc/`（実装完了後に削除済み）
