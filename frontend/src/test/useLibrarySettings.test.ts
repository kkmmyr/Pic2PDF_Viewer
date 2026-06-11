import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: {
        get: vi.fn(),
        patch: vi.fn(),
    },
}));

import apiClient from '@/config/api_client';
import { useLibrarySettings } from '@/hooks/library/useLibrarySettings';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPatch = apiClient.patch as ReturnType<typeof vi.fn>;

const defaultPrefs = {
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

describe('useLibrarySettings', () => {
    beforeEach(() => {
        localStorage.clear();
        mockedGet.mockReset();
        mockedPatch.mockReset();
        mockedPatch.mockResolvedValue({ message: 'Updated' });
    });

    // ── localStorage 管理の設定（変更なし） ──

    describe('初期値（localStorage）', () => {
        it('localStorage が空のときはデフォルト値を返す', () => {
            mockedGet.mockResolvedValue(defaultPrefs);
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            expect(result.current.sortOrder).toBe('name_asc');
            expect(result.current.groupMode).toBe('none');
            expect(result.current.showHidden).toBe(false);
        });

        it('localStorage に保存済みの値を復元する', () => {
            localStorage.setItem('librarySortOrder', JSON.stringify('created_desc'));
            localStorage.setItem('library_group_mode', JSON.stringify('series'));
            localStorage.setItem('library_show_hidden', JSON.stringify(true));
            mockedGet.mockResolvedValue(defaultPrefs);

            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            expect(result.current.sortOrder).toBe('created_desc');
            expect(result.current.groupMode).toBe('series');
            expect(result.current.showHidden).toBe(true);
        });
    });

    describe('setSortOrder', () => {
        it('state と localStorage を更新する', () => {
            mockedGet.mockResolvedValue(defaultPrefs);
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            act(() => {
                result.current.setSortOrder('name_desc');
            });
            expect(result.current.sortOrder).toBe('name_desc');
            expect(JSON.parse(localStorage.getItem('librarySortOrder')!)).toBe('name_desc');
        });
    });

    describe('setGroupMode', () => {
        it('state と localStorage を更新する', () => {
            mockedGet.mockResolvedValue(defaultPrefs);
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            act(() => {
                result.current.setGroupMode('author');
            });
            expect(result.current.groupMode).toBe('author');
            expect(JSON.parse(localStorage.getItem('library_group_mode')!)).toBe('author');
        });
    });

    describe('toggleShowHidden', () => {
        it('false → true にトグルして localStorage に書き込む', () => {
            mockedGet.mockResolvedValue(defaultPrefs);
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            act(() => {
                result.current.toggleShowHidden();
            });
            expect(result.current.showHidden).toBe(true);
            expect(JSON.parse(localStorage.getItem('library_show_hidden')!)).toBe(true);
        });

        it('2 回トグルすると元に戻る', () => {
            mockedGet.mockResolvedValue(defaultPrefs);
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            act(() => {
                result.current.toggleShowHidden();
            });
            act(() => {
                result.current.toggleShowHidden();
            });
            expect(result.current.showHidden).toBe(false);
        });
    });

    // ── API 管理の設定（DB 永続化） ──

    describe('readStateFilter（API）', () => {
        it('マウント時に GET /api/prefs?source=doujin を実行する', async () => {
            mockedGet.mockResolvedValue({ ...defaultPrefs, read_state_filter: 'reading' });
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());
            expect(mockedGet).toHaveBeenCalledWith('/api/prefs?source=doujin');
            await waitFor(() => expect(result.current.readStateFilter).toBe('reading'));
        });

        it('API 未応答中はデフォルト空文字', () => {
            mockedGet.mockReturnValue(new Promise(() => {})); // 解決しない
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            expect(result.current.readStateFilter).toBe('');
        });

        it('setReadStateFilter で楽観的に更新し PATCH を呼ぶ', async () => {
            mockedGet.mockResolvedValue(defaultPrefs);
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            act(() => {
                result.current.setReadStateFilter('done');
            });
            await waitFor(() => expect(result.current.readStateFilter).toBe('done'));
            expect(mockedPatch).toHaveBeenCalledWith('/api/prefs/filters', {
                source: 'doujin',
                read_state_filter: 'done',
            });
        });

        it('空文字でフィルター解除', async () => {
            mockedGet.mockResolvedValue({ ...defaultPrefs, read_state_filter: 'reading' });
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(result.current.readStateFilter).toBe('reading'));

            act(() => {
                result.current.setReadStateFilter('');
            });
            await waitFor(() => expect(result.current.readStateFilter).toBe(''));
        });
    });

    describe('genreFilter（API）', () => {
        it('API レスポンスの genre_filter を反映する', async () => {
            mockedGet.mockResolvedValue({ ...defaultPrefs, genre_filter: 'アクション' });
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(result.current.genreFilter).toBe('アクション'));
        });

        it('setGenreFilter で楽観的に更新し PATCH を呼ぶ', async () => {
            mockedGet.mockResolvedValue(defaultPrefs);
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            act(() => {
                result.current.setGenreFilter('ロマンス');
            });
            await waitFor(() => expect(result.current.genreFilter).toBe('ロマンス'));
            expect(mockedPatch).toHaveBeenCalledWith('/api/prefs/filters', {
                source: 'doujin',
                genre_filter: 'ロマンス',
            });
        });

        it('空文字で解除できる', async () => {
            mockedGet.mockResolvedValue({ ...defaultPrefs, genre_filter: 'アクション' });
            const { result } = renderHook(() => useLibrarySettings('doujin'), {
                wrapper: createWrapper(),
            });
            await waitFor(() => expect(result.current.genreFilter).toBe('アクション'));

            act(() => {
                result.current.setGenreFilter('');
            });
            await waitFor(() => expect(result.current.genreFilter).toBe(''));
        });
    });

    describe('source パラメータ', () => {
        it('source が変わると別の prefs を取得する', async () => {
            mockedGet
                .mockResolvedValueOnce({ ...defaultPrefs, read_state_filter: 'unread' })
                .mockResolvedValueOnce({ ...defaultPrefs, read_state_filter: 'done' });

            const { result, rerender } = renderHook(
                ({ src }: { src: 'doujin' | 'comic' }) => useLibrarySettings(src),
                { wrapper: createWrapper(), initialProps: { src: 'doujin' } },
            );
            await waitFor(() => expect(result.current.readStateFilter).toBe('unread'));

            rerender({ src: 'comic' });
            await waitFor(() => expect(result.current.readStateFilter).toBe('done'));
        });
    });
});
