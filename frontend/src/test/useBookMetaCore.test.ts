import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useBookMetaCore } from '../hooks/useBookMetaCore';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;

describe('useBookMetaCore', () => {
    beforeEach(() => {
        mockedGet.mockReset();
    });

    it('マウント時に GET /api/meta?source= が呼ばれる', async () => {
        mockedGet.mockResolvedValue({});
        renderHook(() => useBookMetaCore('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(mockedGet).toHaveBeenCalledWith('/api/meta', { params: { source: 'generated' } });
    });

    it('レスポンスを meta に反映する', async () => {
        mockedGet.mockResolvedValue({
            'a.pdf': { authors: ['作者A'], tags: ['t1'], view_count: 5 },
        });
        const { result } = renderHook(() => useBookMetaCore('generated'));
        await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());
        expect(result.current.getAuthors('', 'a.pdf')).toEqual(['作者A']);
    });

    it('GET 失敗で meta は空 {} にフォールバック', async () => {
        mockedGet.mockRejectedValue(new Error('boom'));
        const { result } = renderHook(() => useBookMetaCore('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(result.current.meta).toEqual({});
    });

    it('GET の戻り値が undefined でも空 {} に正規化', async () => {
        mockedGet.mockResolvedValue(undefined);
        const { result } = renderHook(() => useBookMetaCore('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(result.current.meta).toEqual({});
    });

    describe('makeKey', () => {
        it('path 空文字なら name のみ', async () => {
            mockedGet.mockResolvedValue({});
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());
            expect(result.current.makeKey('', 'a.pdf')).toBe('a.pdf');
        });

        it('path 指定で "{path}/{name}" に結合', async () => {
            mockedGet.mockResolvedValue({});
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());
            expect(result.current.makeKey('sub', 'a.pdf')).toBe('sub/a.pdf');
        });
    });

    describe('getter 群', () => {
        const META = {
            'a.pdf': {
                authors: ['作者A'],
                tags: ['t1', 't2'],
                series_id: 's1',
                series_title: 'シリーズX',
                series_index: 3,
                hidden: true,
                view_count: 7,
                last_viewed_at: 12345,
            },
        };

        it('getAuthors: エントリありで配列、不在で空配列', async () => {
            mockedGet.mockResolvedValue(META);
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());
            expect(result.current.getAuthors('', 'a.pdf')).toEqual(['作者A']);
            expect(result.current.getAuthors('', 'missing.pdf')).toEqual([]);
        });

        it('getTags: エントリありで配列、不在で空配列', async () => {
            mockedGet.mockResolvedValue(META);
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());
            expect(result.current.getTags('', 'a.pdf')).toEqual(['t1', 't2']);
            expect(result.current.getTags('', 'missing.pdf')).toEqual([]);
        });

        it('getSeries: series_id ありで {id, title, index}、無しで null', async () => {
            mockedGet.mockResolvedValue(META);
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());
            expect(result.current.getSeries('', 'a.pdf')).toEqual({
                id: 's1',
                title: 'シリーズX',
                index: 3,
            });
            expect(result.current.getSeries('', 'missing.pdf')).toBeNull();
        });

        it('getSeries: series_index 欠落で 0 にフォールバック', async () => {
            mockedGet.mockResolvedValue({ 'a.pdf': { series_id: 's1', series_title: 'X' } });
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());
            expect(result.current.getSeries('', 'a.pdf')?.index).toBe(0);
        });

        it('isHidden: true / false / 未指定で false', async () => {
            mockedGet.mockResolvedValue({
                'h.pdf': { hidden: true },
                'v.pdf': { hidden: false },
                'n.pdf': {},
            });
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(result.current.meta['h.pdf']).toBeDefined());
            expect(result.current.isHidden('', 'h.pdf')).toBe(true);
            expect(result.current.isHidden('', 'v.pdf')).toBe(false);
            expect(result.current.isHidden('', 'n.pdf')).toBe(false);
            expect(result.current.isHidden('', 'missing.pdf')).toBe(false);
        });

        it('getViewCount: あれば値、無ければ 0', async () => {
            mockedGet.mockResolvedValue(META);
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());
            expect(result.current.getViewCount('', 'a.pdf')).toBe(7);
            expect(result.current.getViewCount('', 'missing.pdf')).toBe(0);
        });

        it('getLastViewedAt: あれば値、無ければ undefined', async () => {
            mockedGet.mockResolvedValue(META);
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());
            expect(result.current.getLastViewedAt('', 'a.pdf')).toBe(12345);
            expect(result.current.getLastViewedAt('', 'missing.pdf')).toBeUndefined();
        });

        it('path 指定でキーが正しく解決される', async () => {
            mockedGet.mockResolvedValue({
                'a.pdf': { authors: ['ルート'] },
                'sub/a.pdf': { authors: ['サブ'] },
            });
            const { result } = renderHook(() => useBookMetaCore('generated'));
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());
            expect(result.current.getAuthors('', 'a.pdf')).toEqual(['ルート']);
            expect(result.current.getAuthors('sub', 'a.pdf')).toEqual(['サブ']);
        });
    });

    it('fetchMeta を直接呼ぶと再フェッチされる', async () => {
        mockedGet.mockResolvedValueOnce({}).mockResolvedValueOnce({ 'a.pdf': { authors: ['X'] } });
        const { result } = renderHook(() => useBookMetaCore('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

        await act(async () => {
            await result.current.fetchMeta();
        });
        expect(mockedGet).toHaveBeenCalledTimes(2);
        await waitFor(() => expect(result.current.meta['a.pdf']?.authors).toEqual(['X']));
    });

    it('source 変化で再フェッチされる', async () => {
        mockedGet.mockResolvedValueOnce({}).mockResolvedValueOnce({});
        const { rerender } = renderHook(({ src }: { src: string }) => useBookMetaCore(src), {
            initialProps: { src: 'generated' },
        });
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

        rerender({ src: 'kindle' });
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(2));
        expect(mockedGet.mock.calls[1][1]).toEqual({ params: { source: 'kindle' } });
    });
});
