import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { useLibrarySettings } from '../hooks/useLibrarySettings';

const KEYS = {
    sort: 'librarySortOrder',
    groupMode: 'library_group_mode',
    showHidden: 'library_show_hidden',
    showUnread: 'library_show_unread_only',
    genreFilter: 'library_genre_filter',
} as const;

describe('useLibrarySettings', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    describe('初期値', () => {
        it('localStorage が空のときはデフォルト値を返す', () => {
            const { result } = renderHook(() => useLibrarySettings());
            expect(result.current.sortOrder).toBe('name_asc');
            expect(result.current.groupMode).toBe('none');
            expect(result.current.showHidden).toBe(false);
            expect(result.current.showUnreadOnly).toBe(false);
            expect(result.current.genreFilter).toBe('');
        });

        it('localStorage に保存済みの値を復元する', () => {
            localStorage.setItem(KEYS.sort, JSON.stringify('created_desc'));
            localStorage.setItem(KEYS.groupMode, JSON.stringify('series'));
            localStorage.setItem(KEYS.showHidden, JSON.stringify(true));
            localStorage.setItem(KEYS.showUnread, JSON.stringify(true));
            localStorage.setItem(KEYS.genreFilter, JSON.stringify('アクション'));

            const { result } = renderHook(() => useLibrarySettings());
            expect(result.current.sortOrder).toBe('created_desc');
            expect(result.current.groupMode).toBe('series');
            expect(result.current.showHidden).toBe(true);
            expect(result.current.showUnreadOnly).toBe(true);
            expect(result.current.genreFilter).toBe('アクション');
        });
    });

    describe('setSortOrder', () => {
        it('state と localStorage を更新する', () => {
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.setSortOrder('name_desc');
            });
            expect(result.current.sortOrder).toBe('name_desc');
            expect(JSON.parse(localStorage.getItem(KEYS.sort)!)).toBe('name_desc');
        });
    });

    describe('setGroupMode', () => {
        it('state と localStorage を更新する', () => {
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.setGroupMode('author');
            });
            expect(result.current.groupMode).toBe('author');
            expect(JSON.parse(localStorage.getItem(KEYS.groupMode)!)).toBe('author');
        });
    });

    describe('toggleShowHidden', () => {
        it('false → true にトグルして localStorage に書き込む', () => {
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.toggleShowHidden();
            });
            expect(result.current.showHidden).toBe(true);
            expect(JSON.parse(localStorage.getItem(KEYS.showHidden)!)).toBe(true);
        });

        it('true → false にトグルする', () => {
            localStorage.setItem(KEYS.showHidden, JSON.stringify(true));
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.toggleShowHidden();
            });
            expect(result.current.showHidden).toBe(false);
            expect(JSON.parse(localStorage.getItem(KEYS.showHidden)!)).toBe(false);
        });

        it('2 回トグルすると元に戻る', () => {
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.toggleShowHidden();
            });
            act(() => {
                result.current.toggleShowHidden();
            });
            expect(result.current.showHidden).toBe(false);
        });
    });

    describe('toggleShowUnreadOnly', () => {
        it('false → true にトグルして localStorage に書き込む', () => {
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.toggleShowUnreadOnly();
            });
            expect(result.current.showUnreadOnly).toBe(true);
            expect(JSON.parse(localStorage.getItem(KEYS.showUnread)!)).toBe(true);
        });

        it('true → false にトグルする', () => {
            localStorage.setItem(KEYS.showUnread, JSON.stringify(true));
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.toggleShowUnreadOnly();
            });
            expect(result.current.showUnreadOnly).toBe(false);
        });
    });

    describe('setGenreFilter', () => {
        it('state と localStorage を更新する', () => {
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.setGenreFilter('アクション');
            });
            expect(result.current.genreFilter).toBe('アクション');
            expect(JSON.parse(localStorage.getItem(KEYS.genreFilter)!)).toBe('アクション');
        });

        it('空文字で解除できる', () => {
            localStorage.setItem(KEYS.genreFilter, JSON.stringify('アクション'));
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.setGenreFilter('');
            });
            expect(result.current.genreFilter).toBe('');
        });
    });
});
