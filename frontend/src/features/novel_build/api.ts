/**
 * novel_build REST API クライアント（apiClient ラッパー）。
 * SSE のみ別途 `sse.ts` で EventSource ベースに実装する。
 */
import apiClient from '../../config/api_client';

const PREFIX = '/api/novel/build';

export function enqueueBuild(
    bookName: string | null,
    allBooks: boolean,
    mode: 'full_build' | 'generate_contexts' = 'full_build',
): Promise<void> {
    return apiClient.post(`${PREFIX}/enqueue`, { book_name: bookName, all_books: allBooks, mode });
}

export function cancelBuildJob(jobId: number): Promise<void> {
    return apiClient.delete(`${PREFIX}/jobs/${jobId}`);
}
