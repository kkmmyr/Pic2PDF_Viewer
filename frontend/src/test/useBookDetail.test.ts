import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../features/novel_db/api', () => ({
    fetchBookDetail: vi.fn(),
}));

import { fetchBookDetail } from '../features/novel_db/api';
import { useBookDetail } from '../hooks/novel_db/useBookDetail';

const mockedFetch = fetchBookDetail as ReturnType<typeof vi.fn>;

describe('useBookDetail', () => {
    beforeEach(() => mockedFetch.mockReset());

    it('bookName があればマウント時に fetch が呼ばれる', async () => {
        mockedFetch.mockResolvedValue({ summary: 'テスト概要' });
        const { result } = renderHook(() => useBookDetail('book.pdf'));

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(mockedFetch).toHaveBeenCalledWith('book.pdf');
    });

    it('bookName が空のときは fetch しない', () => {
        renderHook(() => useBookDetail(''));
        expect(mockedFetch).not.toHaveBeenCalled();
    });

    it('fetch 成功で detail が反映される', async () => {
        const detail = { summary: '概要テキスト', total_chunks: 100 };
        mockedFetch.mockResolvedValue(detail);
        const { result } = renderHook(() => useBookDetail('book.pdf'));

        await waitFor(() => expect(result.current.detail).not.toBeNull());
        expect(result.current.detail?.summary).toBe('概要テキスト');
    });

    it('fetch 失敗で error がセットされ detail は null のまま', async () => {
        mockedFetch.mockResolvedValueOnce({ summary: '初回' });
        const { result } = renderHook(() => useBookDetail('book.pdf'));
        await waitFor(() => expect(result.current.isLoading).toBe(false));

        mockedFetch.mockRejectedValueOnce(new Error('not found'));
        await act(async () => { await result.current.refetch(); });

        expect(result.current.error).toBeTruthy();
        expect(result.current.detail).toBeNull();
    });

    it('refetch() で再フェッチできる', async () => {
        mockedFetch.mockResolvedValueOnce({ summary: '初回' });
        const { result } = renderHook(() => useBookDetail('book.pdf'));

        await waitFor(() => expect(result.current.detail).not.toBeNull());

        mockedFetch.mockResolvedValueOnce({ summary: '更新後' });
        await act(async () => { await result.current.refetch(); });
        await waitFor(() => expect(result.current.detail?.summary).toBe('更新後'));
    });
});
