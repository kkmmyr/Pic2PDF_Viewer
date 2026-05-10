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
    BookSummary,
    QaHistoryDetail,
    QaHistoryListResponse,
    RebuildEnqueueResponse,
    RebuildJobMode,
    RebuildJobType,
    RebuildStatus,
    Scope,
    SearchResponse,
    SeriesSummary,
} from './types';

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

export function fetchQaHistory(offset = 0, limit = 20): Promise<QaHistoryListResponse> {
    return apiClient.get<unknown, QaHistoryListResponse>(`${PREFIX}/qa/history`, {
        params: { offset, limit },
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
