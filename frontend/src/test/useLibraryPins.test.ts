import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: {
        get: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    },
}));

import apiClient from '../config/api_client';
import { useLibraryPins } from '../hooks/useLibraryPins';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPut = apiClient.put as ReturnType<typeof vi.fn>;
const mockedDelete = apiClient.delete as ReturnType<typeof vi.fn>;

const emptyPrefs = {
    read_state_filter: '',
    genre_filter: '',
    series_pins: {},
    author_pins: {},
};

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

describe('useLibraryPins', () => {
    beforeEach(() => {
        localStorage.clear();
        mockedGet.mockReset();
        mockedPut.mockReset();
        mockedDelete.mockReset();
        mockedPut.mockResolvedValue({ message: 'Pinned' });
        mockedDelete.mockResolvedValue({ message: 'Unpinned' });
    });

    describe('初期状態', () => {
        it('API が空のとき seriesPins/authorPins は空オブジェクト', async () => {
            mockedGet.mockResolvedValue(emptyPrefs);
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());
            expect(result.current.seriesPins).toEqual({});
            expect(result.current.authorPins).toEqual({});
        });

        it('API にデータがあれば反映する', async () => {
            mockedGet.mockResolvedValue({
                ...emptyPrefs,
                series_pins: { 'sid-1': 'vol3.pdf' },
                author_pins: { 'Author A': 'bookA.pdf' },
            });
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(result.current.seriesPins).toEqual({ 'sid-1': 'vol3.pdf' }));
            expect(result.current.authorPins).toEqual({ 'Author A': 'bookA.pdf' });
        });

        it('API 未応答中は空オブジェクト', () => {
            mockedGet.mockReturnValue(new Promise(() => {}));
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            expect(result.current.seriesPins).toEqual({});
            expect(result.current.authorPins).toEqual({});
        });
    });

    describe('toggleSeriesPin', () => {
        it('未ピン状態でトグルすると楽観的に追加され PUT を呼ぶ', async () => {
            mockedGet.mockResolvedValue(emptyPrefs);
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol1.pdf');
            });
            await waitFor(() => expect(result.current.seriesPins['sid-1']).toBe('vol1.pdf'));
            expect(mockedPut).toHaveBeenCalledWith('/api/prefs/pins', {
                source: 'doujin',
                pin_type: 'series',
                group_id: 'sid-1',
                book_name: 'vol1.pdf',
            });
        });

        it('同じ書籍を再トグルすると楽観的に解除され DELETE を呼ぶ', async () => {
            mockedGet.mockResolvedValue({ ...emptyPrefs, series_pins: { 'sid-1': 'vol1.pdf' } });
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(result.current.seriesPins['sid-1']).toBe('vol1.pdf'));

            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol1.pdf');
            });
            await waitFor(() => expect(result.current.seriesPins['sid-1']).toBeUndefined());
            expect(mockedDelete).toHaveBeenCalledWith(
                expect.stringContaining('pin_type=series'),
            );
        });

        it('別の書籍をトグルすると代表が切り替わる', async () => {
            mockedGet.mockResolvedValue({ ...emptyPrefs, series_pins: { 'sid-1': 'vol1.pdf' } });
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(result.current.seriesPins['sid-1']).toBe('vol1.pdf'));

            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol3.pdf');
            });
            await waitFor(() => expect(result.current.seriesPins['sid-1']).toBe('vol3.pdf'));
        });

        it('シリーズピンは作者ピンに影響しない', async () => {
            mockedGet.mockResolvedValue(emptyPrefs);
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol1.pdf');
            });
            expect(result.current.authorPins).toEqual({});
        });
    });

    describe('toggleAuthorPin', () => {
        it('未ピン状態でトグルすると楽観的に追加され PUT を呼ぶ', async () => {
            mockedGet.mockResolvedValue(emptyPrefs);
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            act(() => {
                result.current.toggleAuthorPin('Author A\nAuthor B', 'bookA.pdf');
            });
            await waitFor(() =>
                expect(result.current.authorPins['Author A\nAuthor B']).toBe('bookA.pdf'),
            );
            expect(mockedPut).toHaveBeenCalledWith('/api/prefs/pins', {
                source: 'doujin',
                pin_type: 'author',
                group_id: 'Author A\nAuthor B',
                book_name: 'bookA.pdf',
            });
        });

        it('同じ書籍を再トグルすると楽観的に解除され DELETE を呼ぶ', async () => {
            mockedGet.mockResolvedValue({
                ...emptyPrefs,
                author_pins: { 'Author A': 'bookA.pdf' },
            });
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(result.current.authorPins['Author A']).toBe('bookA.pdf'));

            act(() => {
                result.current.toggleAuthorPin('Author A', 'bookA.pdf');
            });
            await waitFor(() => expect(result.current.authorPins['Author A']).toBeUndefined());
            expect(mockedDelete).toHaveBeenCalledWith(
                expect.stringContaining('pin_type=author'),
            );
        });

        it('作者ピンはシリーズピンに影響しない', async () => {
            mockedGet.mockResolvedValue(emptyPrefs);
            const { result } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            act(() => {
                result.current.toggleAuthorPin('Author A', 'bookA.pdf');
            });
            expect(result.current.seriesPins).toEqual({});
        });
    });

    describe('ソース別の独立管理', () => {
        it('source が異なれば別の prefs が取得される', async () => {
            mockedGet
                .mockResolvedValueOnce({ ...emptyPrefs, series_pins: { 'sid-1': 'vol1.pdf' } })
                .mockResolvedValueOnce(emptyPrefs);

            const { result: doujin } = renderHook(() => useLibraryPins('doujin'), {
                wrapper: createWrapper(),
            });
            const { result: comic } = renderHook(() => useLibraryPins('comic'), {
                wrapper: createWrapper(),
            });

            await waitFor(() =>
                expect(doujin.current.seriesPins['sid-1']).toBe('vol1.pdf'),
            );
            await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(2));
            expect(comic.current.seriesPins).toEqual({});
        });
    });
});
