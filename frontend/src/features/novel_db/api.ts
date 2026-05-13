/**
 * novel_db API クライアント（apiClient ラッパ）。
 * SSE のみ別途 `sse.ts` で fetch ベースに実装する（apiClient は SSE 非対応）。
 *
 * apiClient (axios) の interceptor が `response.data` を返すため、
 * `apiClient.get<unknown, T>(...)` の第 2 ジェネリクスが解決値の型になる
 * （既存パターン: hooks/useGenres.ts 等を参照）。
 */
import apiClient from '../../config/api_client';

import type {
    BookDetail,
    BookSummary,
    CharacterDetail,
    CharacterSummary,
    ChatSessionDetail,
    ChatSessionSummary,
    NovelMetaPatch,
    QaHistoryDetail,
    QaHistoryListResponse,
    DiscussionHistoryItem,
    RebuildEnqueueResponse,
    RebuildJobMode,
    RebuildJobType,
    RebuildStatus,
    Scope,
    SearchResponse,
    SeriesSummary,
} from './types';

export type { DiscussionHistoryItem };

const PREFIX = '/api/novel_db';

// ---------------------------------------------------------------------------
// ライブラリ
// ---------------------------------------------------------------------------

export function fetchBooks(): Promise<BookSummary[]> {
    return apiClient.get<unknown, BookSummary[]>(`${PREFIX}/books`);
}

export function fetchSeries(): Promise<SeriesSummary[]> {
    return apiClient.get<unknown, SeriesSummary[]>(`${PREFIX}/series`);
}

export function fetchNovelAuthors(): Promise<string[]> {
    return apiClient.get<unknown, string[]>(`${PREFIX}/authors`);
}

// ---------------------------------------------------------------------------
// 検索
// ---------------------------------------------------------------------------

export interface SearchRequest {
    query: string;
    scope: Scope;
    offset?: number;
    limit?: number;
}

export function searchHits(req: SearchRequest): Promise<SearchResponse> {
    return apiClient.post<unknown, SearchResponse>(`${PREFIX}/search`, req);
}

// ---------------------------------------------------------------------------
// 質問履歴
// ---------------------------------------------------------------------------

export function fetchQaHistory(
    offset = 0,
    limit = 20,
    book?: string,
): Promise<QaHistoryListResponse> {
    return apiClient.get<unknown, QaHistoryListResponse>(`${PREFIX}/qa/history`, {
        params: { offset, limit, ...(book !== undefined && { book }) },
    });
}

export function fetchQaHistoryDetail(id: number): Promise<QaHistoryDetail> {
    return apiClient.get<unknown, QaHistoryDetail>(`${PREFIX}/qa/history/${id}`);
}

export function deleteQaHistory(id: number): Promise<void> {
    return apiClient.delete<unknown, void>(`${PREFIX}/qa/history/${id}`);
}

// ---------------------------------------------------------------------------
// 再構築ジョブ
// ---------------------------------------------------------------------------

export interface RebuildEnqueueRequest {
    type: RebuildJobType;
    target_id?: string | null;
    mode?: RebuildJobMode;
}

export function postRebuild(req: RebuildEnqueueRequest): Promise<RebuildEnqueueResponse> {
    return apiClient.post<unknown, RebuildEnqueueResponse>(`${PREFIX}/rebuild`, req);
}

export function fetchRebuildStatus(): Promise<RebuildStatus> {
    return apiClient.get<unknown, RebuildStatus>(`${PREFIX}/rebuild/status`);
}

export function cancelRebuild(jobId: number): Promise<void> {
    return apiClient.delete<unknown, void>(`${PREFIX}/rebuild/${jobId}`);
}

// ---------------------------------------------------------------------------
// キャラクター辞典（B-15）
// ---------------------------------------------------------------------------

export function fetchBookCharacters(bookName: string): Promise<CharacterSummary[]> {
    return apiClient.get<unknown, CharacterSummary[]>(
        `${PREFIX}/books/${encodeURIComponent(bookName)}/characters`,
    );
}

export function fetchCharacterDetail(bookName: string, charName: string): Promise<CharacterDetail> {
    return apiClient.get<unknown, CharacterDetail>(
        `${PREFIX}/books/${encodeURIComponent(bookName)}/characters/${encodeURIComponent(charName)}`,
    );
}

// ---------------------------------------------------------------------------
// マルチターン会話 QA（B-16）
// ---------------------------------------------------------------------------

export function fetchChatSessions(offset = 0, limit = 20): Promise<ChatSessionSummary[]> {
    return apiClient.get<unknown, ChatSessionSummary[]>(`${PREFIX}/qa/sessions`, {
        params: { offset, limit },
    });
}

export function fetchChatSessionDetail(sessionId: number): Promise<ChatSessionDetail> {
    return apiClient.get<unknown, ChatSessionDetail>(`${PREFIX}/qa/sessions/${sessionId}`);
}

export function deleteChatSession(sessionId: number): Promise<void> {
    return apiClient.delete<unknown, void>(`${PREFIX}/qa/sessions/${sessionId}`);
}

export function patchChatSessionTitle(sessionId: number, title: string): Promise<void> {
    return apiClient.patch<unknown, void>(`${PREFIX}/qa/sessions/${sessionId}/title`, { title });
}

// ---------------------------------------------------------------------------
// 書籍メタ編集（4.3）
// ---------------------------------------------------------------------------

export function patchNovelBookMeta(bookKey: string, patch: NovelMetaPatch): Promise<void> {
    return apiClient.patch<unknown, void>(`/api/meta/novel/${encodeURIComponent(bookKey)}`, patch);
}

export function reorderNovelSeries(seriesId: string, names: string[]): Promise<void> {
    return apiClient.post<unknown, void>('/api/series/reorder', {
        series_id: seriesId,
        names,
        source: 'novel',
    });
}

// ---------------------------------------------------------------------------
// 読書会ディスカッション（B-20）
// ---------------------------------------------------------------------------

export function fetchBookDetail(bookName: string): Promise<BookDetail> {
    return apiClient.get<unknown, BookDetail>(
        `${PREFIX}/books/${encodeURIComponent(bookName)}/detail`,
    );
}

export function fetchDiscussionHistory(bookName: string): Promise<DiscussionHistoryItem[]> {
    return apiClient.get<unknown, DiscussionHistoryItem[]>(
        `/api/novel/discussion/history?book_name=${encodeURIComponent(bookName)}`,
    );
}
