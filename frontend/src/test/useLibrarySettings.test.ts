import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { useLibrarySettings } from '../hooks/useLibrarySettings';

const KEYS = {
    sort: 'librarySortOrder',
    groupMode: 'library_group_mode',
    showHidden: 'library_show_hidden',
    readStateFilter: 'library_read_state_filter',
    legacyShowUnread: 'library_show_unread_only',
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
            expect(result.current.readStateFilter).toBe('');
            expect(result.current.genreFilter).toBe('');
        });

        it('localStorage に保存済みの値を復元する', () => {
            localStorage.setItem(KEYS.sort, JSON.stringify('created_desc'));
            localStorage.setItem(KEYS.groupMode, JSON.stringify('series'));
            localStorage.setItem(KEYS.showHidden, JSON.stringify(true));
            localStorage.setItem(KEYS.readStateFilter, JSON.stringify('reading'));
            localStorage.setItem(KEYS.genreFilter, JSON.stringify('アクション'));

            const { result } = renderHook(() => useLibrarySettings());
            expect(result.current.sortOrder).toBe('created_desc');
            expect(result.current.groupMode).toBe('series');
            expect(result.current.showHidden).toBe(true);
            expect(result.current.readStateFilter).toBe('reading');
            expect(result.current.genreFilter).toBe('アクション');
        });
    });

    describe('legacy migration (library_show_unread_only)', () => {
        it('旧 true は readStateFilter="unread" に移行され、旧キーは削除される', () => {
            localStorage.setItem(KEYS.legacyShowUnread, JSON.stringify(true));
            const { result } = renderHook(() => useLibrarySettings());
            expect(result.current.readStateFilter).toBe('unread');
            expect(JSON.parse(localStorage.getItem(KEYS.readStateFilter)!)).toBe('unread');
            expect(localStorage.getItem(KEYS.legacyShowUnread)).toBeNull();
        });

        it('旧 false は readStateFilter="" になり、旧キーは削除される', () => {
            localStorage.setItem(KEYS.legacyShowUnread, JSON.stringify(false));
            const { result } = renderHook(() => useLibrarySettings());
            expect(result.current.readStateFilter).toBe('');
            expect(localStorage.getItem(KEYS.legacyShowUnread)).toBeNull();
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

    describe('setReadStateFilter', () => {
        it('値を切り替えて localStorage に書き込む', () => {
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.setReadStateFilter('done');
            });
            expect(result.current.readStateFilter).toBe('done');
            expect(JSON.parse(localStorage.getItem(KEYS.readStateFilter)!)).toBe('done');
        });

        it('空文字でフィルター解除', () => {
            localStorage.setItem(KEYS.readStateFilter, JSON.stringify('reading'));
            const { result } = renderHook(() => useLibrarySettings());
            act(() => {
                result.current.setReadStateFilter('');
            });
            expect(result.current.readStateFilter).toBe('');
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
