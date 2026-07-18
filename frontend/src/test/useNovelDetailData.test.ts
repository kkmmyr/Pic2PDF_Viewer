import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../features/novel_db/api', () => ({
    fetchDiscussionHistory: vi.fn(),
    fetchSimilarBooks: vi.fn(),
}));

import { fetchDiscussionHistory, fetchSimilarBooks } from '@/features/novel_db/api';
import { useNovelDetailData } from '@/hooks/novel_db/useNovelDetailData';
import { createQueryWrapper } from '@/test/queryTestUtils';

describe('useNovelDetailData', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(fetchDiscussionHistory).mockResolvedValue([]);
        vi.mocked(fetchSimilarBooks).mockResolvedValue([{ name: 'similar', score: 0.9 }]);
    });

    it('履歴を取得し、未索引なら類似書籍は取得しない', async () => {
        const { result } = renderHook(() => useNovelDetailData('book-a', false), {
            wrapper: createQueryWrapper(),
        });

        await waitFor(() => expect(result.current.discussionsLoading).toBe(false));
        expect(fetchDiscussionHistory).toHaveBeenCalledWith('book-a');
        expect(fetchSimilarBooks).not.toHaveBeenCalled();
    });

    it('索引済みなら類似書籍を取得する', async () => {
        const { result } = renderHook(() => useNovelDetailData('book-a', true), {
            wrapper: createQueryWrapper(),
        });

        await waitFor(() => expect(result.current.similarBooks).toHaveLength(1));
        expect(fetchSimilarBooks).toHaveBeenCalledWith('book-a');
    });
});
