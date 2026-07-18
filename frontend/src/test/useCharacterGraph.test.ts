import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../features/novel_graph/api', () => ({
    fetchSeriesList: vi.fn(),
    fetchBooksInSeries: vi.fn(),
    fetchGraph: vi.fn(),
}));

import { fetchBooksInSeries, fetchGraph, fetchSeriesList } from '@/features/novel_graph/api';
import { useCharacterGraph } from '@/hooks/novel_graph/useCharacterGraph';
import { createQueryWrapper } from '@/test/queryTestUtils';

describe('useCharacterGraph', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(fetchSeriesList).mockResolvedValue(['series-a']);
        vi.mocked(fetchBooksInSeries).mockResolvedValue([{ id: 1, name: 'book-a' }]);
        vi.mocked(fetchGraph).mockResolvedValue({ nodes: [], edges: [] });
    });

    it('series 選択後に書籍とグラフを Query 経由で取得する', async () => {
        const { result } = renderHook(() => useCharacterGraph(), {
            wrapper: createQueryWrapper(),
        });
        await waitFor(() => expect(result.current.seriesList).toEqual(['series-a']));

        act(() => result.current.setSelectedSeries('series-a'));

        await waitFor(() => expect(result.current.books).toHaveLength(1));
        await waitFor(() => expect(result.current.selectedBookIds).toEqual([1]));
        await waitFor(() => expect(fetchGraph).toHaveBeenCalledWith('series-a', [1]));
        expect(result.current.graphData).toEqual({ nodes: [], edges: [] });
    });
});
