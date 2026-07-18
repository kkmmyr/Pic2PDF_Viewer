import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../features/novel_db/api', () => ({
    fetchCharacterDetail: vi.fn(),
}));

import { fetchCharacterDetail } from '@/features/novel_db/api';
import { useCharacterDetail } from '@/hooks/novel_db/useCharacterDetail';
import { createQueryWrapper } from '@/test/queryTestUtils';

const mockedFetch = fetchCharacterDetail as ReturnType<typeof vi.fn>;

describe('useCharacterDetail', () => {
    beforeEach(() => mockedFetch.mockReset());

    it('bookName/charName 両方 null では fetch しない', () => {
        renderHook(() => useCharacterDetail(null, null), { wrapper: createQueryWrapper() });
        expect(mockedFetch).not.toHaveBeenCalled();
    });

    it('bookName のみ null では fetch しない', () => {
        renderHook(() => useCharacterDetail(null, 'キャラA'), { wrapper: createQueryWrapper() });
        expect(mockedFetch).not.toHaveBeenCalled();
    });

    it('charName のみ null では fetch しない', () => {
        renderHook(() => useCharacterDetail('book.pdf', null), { wrapper: createQueryWrapper() });
        expect(mockedFetch).not.toHaveBeenCalled();
    });

    it('両方 set されたら fetch が呼ばれる', async () => {
        const detail = { name: 'キャラA', scenes: [] };
        mockedFetch.mockResolvedValue(detail);
        const { result } = renderHook(() => useCharacterDetail('book.pdf', 'キャラA'), {
            wrapper: createQueryWrapper(),
        });

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(mockedFetch).toHaveBeenCalledWith('book.pdf', 'キャラA');
        expect(result.current.detail?.name).toBe('キャラA');
    });

    it('fetch 失敗で error がセットされる', async () => {
        mockedFetch.mockResolvedValueOnce({ name: 'キャラA', scenes: [] });
        const { result } = renderHook(() => useCharacterDetail('book.pdf', 'キャラA'), {
            wrapper: createQueryWrapper(),
        });
        await waitFor(() => expect(result.current.isLoading).toBe(false));

        mockedFetch.mockRejectedValueOnce(new Error('not found'));
        await act(async () => {
            await result.current.refetch();
        });

        expect(result.current.error).toBeTruthy();
        expect(result.current.detail).toBeNull();
    });

    it('bookName が null に変わると detail が null にリセットされる', async () => {
        mockedFetch.mockResolvedValue({ name: 'キャラA', scenes: [] });
        const { result, rerender } = renderHook(
            ({ book, char }: { book: string | null; char: string | null }) =>
                useCharacterDetail(book, char),
            {
                initialProps: {
                    book: 'book.pdf' as string | null,
                    char: 'キャラA' as string | null,
                },
                wrapper: createQueryWrapper(),
            },
        );

        await waitFor(() => expect(result.current.detail).not.toBeNull());
        rerender({ book: null, char: 'キャラA' });
        await waitFor(() => expect(result.current.detail).toBeNull());
    });
});
