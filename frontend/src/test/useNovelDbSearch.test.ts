/**
 * useNovelDbSearch: debounce + 無限スクロール。
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { useNovelDbSearch } from '@/hooks/novel_db/useNovelDbSearch';
import type { Scope, SearchResponse } from '@/features/novel_db/types';
import { createQueryWrapper } from '@/test/queryTestUtils';

vi.mock('../features/novel_db/api', () => ({
    searchHits: vi.fn(),
}));

import { searchHits } from '@/features/novel_db/api';

const SCOPE: Scope = { type: 'all' };

function makeResponse(offset: number, count: number, total: number): SearchResponse {
    return {
        hits: Array.from({ length: count }, (_, i) => ({
            book_name: 'b',
            page_no: offset + i + 1,
            snippet: 's',
            has_highlight: false,
            image_url: null,
            rrf_score: 0.1,
        })),
        total,
        offset,
        limit: count,
    };
}

describe('useNovelDbSearch', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(searchHits).mockReset();
    });

    it('クエリが空なら検索しない', async () => {
        renderHook(() => useNovelDbSearch(SCOPE), { wrapper: createQueryWrapper() });
        await new Promise((r) => setTimeout(r, 50));
        expect(searchHits).not.toHaveBeenCalled();
    });

    it('クエリ入力 → debounce 後に検索', async () => {
        vi.mocked(searchHits).mockResolvedValue(makeResponse(0, 5, 5));
        const { result } = renderHook(() => useNovelDbSearch(SCOPE), {
            wrapper: createQueryWrapper(),
        });

        act(() => {
            result.current.setQuery('デューク');
        });

        await waitFor(
            () => {
                expect(searchHits).toHaveBeenCalled();
            },
            { timeout: 1000 },
        );

        await waitFor(() => {
            expect(result.current.hits.length).toBe(5);
            expect(result.current.total).toBe(5);
        });
    });

    it('loadMore で次ページを追加読み込み', async () => {
        vi.mocked(searchHits)
            .mockResolvedValueOnce(makeResponse(0, 20, 40)) // 初回
            .mockResolvedValueOnce(makeResponse(20, 20, 40)); // 追加

        const { result } = renderHook(() => useNovelDbSearch(SCOPE), {
            wrapper: createQueryWrapper(),
        });
        act(() => result.current.setQuery('q'));

        await waitFor(() => {
            expect(result.current.hits.length).toBe(20);
        });

        expect(result.current.hasMore).toBe(true);

        await act(async () => {
            await result.current.loadMore();
        });

        await waitFor(() => {
            expect(result.current.hits.length).toBe(40);
            expect(result.current.hasMore).toBe(false);
        });
    });

    it('検索エラーは error に格納される', async () => {
        vi.mocked(searchHits).mockRejectedValue(new Error('boom'));

        const { result } = renderHook(() => useNovelDbSearch(SCOPE), {
            wrapper: createQueryWrapper(),
        });
        act(() => result.current.setQuery('q'));

        await waitFor(() => {
            expect(result.current.error).toBe('boom');
        });
    });
});
